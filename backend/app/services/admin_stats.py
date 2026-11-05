from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Date, cast, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Payment, SearchSession, Subscription, User


async def overview(session: AsyncSession) -> dict[str, Any]:
    now = datetime.now(UTC)
    day = now - timedelta(days=1)

    async def count(q: Any) -> int:
        return int(await session.scalar(q) or 0)

    active_subs = (
        select(Subscription.plan_code, Subscription.source, func.count(func.distinct(Subscription.user_id)))
        .where(Subscription.status == "active", Subscription.expires_at > now)
        .group_by(Subscription.plan_code, Subscription.source)
    )
    by_plan: dict[str, int] = {}
    trials = 0
    for plan, source, n in (await session.execute(active_subs)).all():
        if source == "trial":
            trials += n
        else:
            by_plan[plan] = by_plan.get(plan, 0) + n
    return {
        "users_total": await count(select(func.count()).select_from(User)),
        "users_active_24h": await count(select(func.count()).select_from(User).where(User.last_seen_at > day)),
        "users_active_7d": await count(select(func.count()).select_from(User).where(User.last_seen_at > now - timedelta(days=7))),
        "users_blocked": await count(select(func.count()).select_from(User).where(User.is_blocked.is_(True))),
        "pro_active": by_plan.get("pro", 0),
        "ultra_active": by_plan.get("ultra", 0),
        "trials_active": trials,
        "searches_24h": await count(select(func.count()).select_from(SearchSession).where(SearchSession.created_at > day)),
        "searches_failed_24h": await count(
            select(func.count()).select_from(SearchSession).where(SearchSession.created_at > day, SearchSession.status == "failed")
        ),
        "revenue_stars_total": await count(select(func.coalesce(func.sum(Payment.amount_stars), 0)).where(Payment.status == "paid")),
        "revenue_stars_30d": await count(
            select(func.coalesce(func.sum(Payment.amount_stars), 0)).where(
                Payment.status == "paid", Payment.created_at > now - timedelta(days=30)
            )
        ),
        "refunds_total": await count(select(func.count()).select_from(Payment).where(Payment.status == "refunded")),
    }


async def timeseries(session: AsyncSession, days: int) -> list[dict[str, Any]]:
    start = (datetime.now(UTC) - timedelta(days=days - 1)).date()
    series = {
        (start + timedelta(days=i)).isoformat(): {
            "date": (start + timedelta(days=i)).isoformat(),
            "users": 0,
            "searches": 0,
            "revenue": 0,
            "active": 0,
        }
        for i in range(days)
    }

    async def fill(col: Any, field: str, value: Any, where: Any) -> None:
        d = cast(func.timezone("UTC", col), Date)
        rows = (await session.execute(select(d, value).where(col >= start, where).group_by(d))).all()
        for day, v in rows:
            key = day.isoformat()
            if key in series:
                series[key][field] = int(v or 0)

    await fill(User.created_at, "users", func.count(), text("true"))
    await fill(SearchSession.created_at, "searches", func.count(), text("true"))
    await fill(SearchSession.created_at, "active", func.count(func.distinct(SearchSession.user_id)), text("true"))
    await fill(Payment.created_at, "revenue", func.sum(Payment.amount_stars), Payment.status == "paid")
    return list(series.values())
