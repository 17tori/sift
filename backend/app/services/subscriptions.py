"""Subscription lifecycle and entitlement resolution.

A user's effective plan is the highest-priority subscription with status=active and
expires_at in the future; otherwise the FREE plan. Nothing is considered active
before Telegram confirms a successful payment.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound, QuotaExceeded
from app.db.models import Plan, SearchSession, Subscription, User

log = logging.getLogger(__name__)
FREE = "free"


@dataclass(slots=True)
class Entitlement:
    plan: Plan
    subscription: Subscription | None
    used: int
    limit: int
    window: str
    window_resets_at: datetime
    bonus: int

    @property
    def remaining(self) -> int:
        return max(self.limit - self.used, 0) + self.bonus

    @property
    def features(self) -> dict[str, Any]:
        return self.plan.features or {}

    @property
    def is_trial(self) -> bool:
        return self.subscription is not None and self.subscription.source == "trial"


async def get_plan(session: AsyncSession, code: str) -> Plan:
    plan = await session.get(Plan, code)
    if plan is None:
        raise NotFound("plan_not_found")
    return plan


async def active_subscription(session: AsyncSession, user_id: int, now: datetime | None = None) -> Subscription | None:
    now = now or datetime.now(UTC)
    q = (
        select(Subscription)
        .join(Plan, Plan.code == Subscription.plan_code)
        .where(Subscription.user_id == user_id, Subscription.status == "active", Subscription.expires_at > now)
        .order_by(Plan.priority.desc(), Subscription.expires_at.desc())
        .limit(1)
    )
    return await session.scalar(q)


def _window_start(window: str, anchor: datetime | None, now: datetime) -> tuple[datetime, datetime]:
    if window == "day":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1)
    # monthly windows are anchored to the subscription start (billing cycle), else calendar month
    if anchor is not None:
        cycles = int((now - anchor) / timedelta(days=30))
        start = anchor + timedelta(days=30 * cycles)
        return start, start + timedelta(days=30)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    nxt = (start + timedelta(days=32)).replace(day=1)
    return start, nxt


async def entitlement(session: AsyncSession, user: User, now: datetime | None = None) -> Entitlement:
    now = now or datetime.now(UTC)
    sub = await active_subscription(session, user.id, now)
    plan = await get_plan(session, sub.plan_code if sub else FREE)
    start, end = _window_start(plan.limit_window, sub.started_at if sub else None, now)
    used = await session.scalar(
        select(func.count())
        .select_from(SearchSession)
        .where(
            SearchSession.user_id == user.id,
            SearchSession.quota_counted.is_(True),
            SearchSession.used_bonus.is_(False),
            SearchSession.created_at >= start,
        )
    )
    return Entitlement(plan, sub, int(used or 0), plan.search_limit, plan.limit_window, end, user.bonus_searches)


async def reserve_search(session: AsyncSession, user: User) -> tuple[Entitlement, bool]:
    """Serialises quota checks per user (advisory xact lock). Returns (entitlement, used_bonus)."""
    await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": 7_000_000_000 + user.id})
    ent = await entitlement(session, user)
    if ent.used < ent.limit:
        return ent, False
    res = await session.execute(
        update(User)
        .where(User.id == user.id, User.bonus_searches > 0)
        .values(bonus_searches=User.bonus_searches - 1)
        .returning(User.bonus_searches)
    )
    if res.scalar_one_or_none() is not None:
        return ent, True
    raise QuotaExceeded(
        "quota_exceeded",
        "Лимит поисков исчерпан.",
        plan=ent.plan.code,
        resets_at=ent.window_resets_at.isoformat(),
    )


async def refund_search(session: AsyncSession, search: SearchSession) -> None:
    """Gives the search back when it failed for reasons on our side."""
    if not search.quota_counted:
        return
    search.quota_counted = False
    if search.used_bonus:
        await session.execute(update(User).where(User.id == search.user_id).values(bonus_searches=User.bonus_searches + 1))


async def grant(
    session: AsyncSession,
    user_id: int,
    plan_code: str,
    days: int,
    source: str,
    *,
    recurring: bool = False,
    charge_id: str | None = None,
    intent_id: Any = None,
    note: str | None = None,
    now: datetime | None = None,
) -> Subscription:
    """Activates or extends a plan. Paid time stacks onto an existing active sub of the same plan."""
    now = now or datetime.now(UTC)
    existing = await session.scalar(
        select(Subscription)
        .where(
            Subscription.user_id == user_id,
            Subscription.plan_code == plan_code,
            Subscription.status == "active",
            Subscription.expires_at > now,
            Subscription.source != "trial",
        )
        .order_by(Subscription.expires_at.desc())
        .with_for_update()
        .limit(1)
    )
    if existing is not None and source in ("payment", "admin", "referral"):
        existing.expires_at = existing.expires_at + timedelta(days=days)
        if recurring:
            existing.is_recurring = True
            existing.auto_renew = True
            existing.telegram_charge_id = existing.telegram_charge_id or charge_id
        existing.expiry_notified = False
        return existing
    sub = Subscription(
        user_id=user_id,
        plan_code=plan_code,
        status="active",
        source=source,
        started_at=now,
        expires_at=now + timedelta(days=days),
        is_recurring=recurring,
        auto_renew=recurring,
        telegram_charge_id=charge_id,
        intent_id=intent_id,
        note=note,
    )
    session.add(sub)
    await session.flush()
    # A paid plan supersedes a running trial.
    if source == "payment":
        await session.execute(
            update(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.source == "trial",
                Subscription.status == "active",
            )
            .values(status="expired", expires_at=now)
        )
    return sub


async def expire_due(session: AsyncSession, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    res = await session.execute(
        update(Subscription).where(and_(Subscription.status == "active", Subscription.expires_at <= now)).values(status="expired")
    )
    return res.rowcount or 0
