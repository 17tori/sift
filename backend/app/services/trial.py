"""Free trial: once per Telegram account, never converts to paid automatically."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models import Subscription, User
from app.services import subscriptions
from app.services.app_settings import get_setting


async def trial_config(session: AsyncSession) -> dict:
    return await get_setting(session, "trial")


async def is_available(session: AsyncSession, user: User) -> bool:
    cfg = await trial_config(session)
    if not cfg.get("enabled", True) or user.trial_used:
        return False
    # Already a paying customer -> trial makes no sense.
    paid = await session.scalar(select(Subscription.id).where(Subscription.user_id == user.id, Subscription.source == "payment").limit(1))
    return paid is None


async def activate(session: AsyncSession, user: User, now: datetime | None = None) -> Subscription:
    now = now or datetime.now(UTC)
    locked = await session.scalar(select(User).where(User.id == user.id).with_for_update())
    assert locked is not None
    if not await is_available(session, locked):
        raise AppError("trial_unavailable", "Пробный период уже был использован.")
    cfg = await trial_config(session)
    days = int(cfg.get("days", 3))
    sub = await subscriptions.grant(session, locked.id, cfg.get("plan", "pro"), days, "trial", now=now)
    locked.trial_used = True
    locked.trial_started_at = now
    locked.trial_ends_at = now + timedelta(days=days)
    locked.trial_notified_24h = False
    locked.trial_notified_end = False
    return sub
