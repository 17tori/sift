"""Periodic jobs (single process): subscription expiry, trial reminders, marketplace and AI
health, FX rates, price-drop alerts, upload retention."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.redis import get_redis
from app.db.models import Favorite, MarketplaceStatus, Product, SearchSession, Subscription, User
from app.db.session import session_scope
from app.marketplace import registry
from app.marketplace.base import ProviderState
from app.marketplace.providers.feed import FeedCatalogProvider
from app.services import fx, notifications, subscriptions
from app.services.catalog import upsert_products
from app.services.storage import get_storage

log = logging.getLogger("scheduler")


async def expire_subscriptions() -> None:
    async with session_scope() as s:
        n = await subscriptions.expire_due(s)
    if n:
        log.info("expired %s subscriptions", n)


async def subscription_reminders() -> None:
    """Non-recurring paid plans: remind 24h before expiry (recurring ones renew by themselves)."""
    now = datetime.now(UTC)
    async with session_scope() as s:
        rows = (
            await s.execute(
                select(Subscription, User)
                .join(User, User.id == Subscription.user_id)
                .where(
                    Subscription.status == "active",
                    Subscription.source == "payment",
                    Subscription.auto_renew.is_(False),
                    Subscription.expiry_notified.is_(False),
                    Subscription.expires_at <= now + timedelta(hours=24),
                    Subscription.expires_at > now,
                )
                .limit(200)
            )
        ).all()
        for sub, _ in rows:
            sub.expiry_notified = True
    for sub, user in rows:
        await notifications.send(
            user.id,
            user.telegram_id,
            f"Подписка <b>{sub.plan_code.upper()}</b> закончится через 24 часа. Продлите её, чтобы не потерять доступ.",
            ("Продлить", "subscription"),
        )


async def trial_notifications() -> None:
    s_ = get_settings()
    now = datetime.now(UTC)
    async with session_scope() as s:
        soon = (
            await s.scalars(
                select(User)
                .where(
                    User.trial_ends_at.is_not(None),
                    User.trial_notified_24h.is_(False),
                    User.trial_ends_at <= now + timedelta(hours=24),
                    User.trial_ends_at > now,
                )
                .limit(200)
            )
        ).all()
        for u in soon:
            u.trial_notified_24h = True
        ended = (
            await s.scalars(
                select(User)
                .where(
                    User.trial_ends_at.is_not(None),
                    User.trial_notified_end.is_(False),
                    User.trial_ends_at <= now,
                )
                .limit(200)
            )
        ).all()
        for u in ended:
            u.trial_notified_end = True
            u.trial_notified_24h = True
    for u in soon:
        await notifications.send(
            u.id,
            u.telegram_id,
            f"Пробный период {s_.brand_name} PRO закончится через 24 часа. Автоматического списания не будет.",
            ("Тарифы", "subscription"),
        )
    for u in ended:
        await notifications.send(
            u.id,
            u.telegram_id,
            f"Пробный период {s_.brand_name} PRO закончился. Вы на тарифе Free. Оформите PRO, чтобы вернуть расширенные возможности.",
            ("Оформить PRO", "subscription"),
        )


async def marketplace_health() -> None:
    for p in registry.providers().values():
        if isinstance(p, FeedCatalogProvider):
            await p.refresh_state()
        state = p.state()
        started = time.monotonic()
        err: str | None = None
        if state is ProviderState.ACTIVE:
            try:
                await asyncio.wait_for(p.health_check(), timeout=15)
            except Exception as e:  # noqa: BLE001
                err = str(e)[:500]
        latency = int((time.monotonic() - started) * 1000)
        now = datetime.now(UTC)
        final = ProviderState.DOWN.value if err else state.value
        async with session_scope() as s:
            stmt = insert(MarketplaceStatus).values(
                code=p.code,
                status=final,
                last_check_at=now,
                last_ok_at=None if err else now,
                last_error=err,
                latency_ms=latency,
                consecutive_failures=1 if err else 0,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[MarketplaceStatus.code],
                set_={
                    "status": final,
                    "last_check_at": now,
                    "latency_ms": latency,
                    "last_error": err,
                    "last_ok_at": MarketplaceStatus.last_ok_at if err else now,
                    "consecutive_failures": (MarketplaceStatus.consecutive_failures + 1) if err else 0,
                },
            )
            await s.execute(stmt)


async def refresh_fx() -> None:
    n = await fx.refresh()
    log.info("fx rates refreshed: %s currencies", n)


async def price_alerts() -> None:
    """ULTRA price-drop alerts for favourites whose source supports get_product()."""
    async with session_scope() as s:
        rows = (
            await s.execute(
                select(Favorite, Product, User)
                .join(Product, Product.id == Favorite.product_id)
                .join(User, User.id == Favorite.user_id)
                .where(Favorite.price_alert.is_(True), User.is_blocked.is_(False))
                .where((Product.last_price_check_at.is_(None)) | (Product.last_price_check_at < datetime.now(UTC) - timedelta(hours=6)))
                .limit(100)
            )
        ).all()
    for fav, product, user in rows:
        provider = registry.get(product.source)
        if provider is None or provider.state() is not ProviderState.ACTIVE:
            continue
        try:
            fresh = await provider.get_product(product.external_id)
        except Exception as e:  # noqa: BLE001
            log.warning("price check %s/%s failed: %s", product.source, product.external_id, e)
            continue
        async with session_scope() as s:
            await s.execute(update(Product).where(Product.id == product.id).values(last_price_check_at=datetime.now(UTC)))
            if fresh is None:
                continue
            await upsert_products(s, [fresh])
            base = fav.last_notified_price or fav.saved_price
            if fresh.price is not None and base is not None and fresh.currency == fav.saved_currency and fresh.price < base * Decimal("0.97"):
                await s.execute(update(Favorite).where(Favorite.id == fav.id).values(last_notified_price=fresh.price))
                notify = True
            else:
                notify = False
        if notify:
            await notifications.send(
                user.id,
                user.telegram_id,
                f"Цена снизилась: <b>{fresh.title[:80]}</b>\n{base} → <b>{fresh.price} {fresh.currency}</b>",
                ("Открыть избранное", "saved"),
            )


async def stale_searches() -> None:
    """Searches stuck in queued/running for >10 minutes (worker crash) are failed and refunded."""
    cutoff = datetime.now(UTC) - timedelta(minutes=10)
    async with session_scope() as s:
        rows = (
            await s.scalars(
                select(SearchSession)
                .where(SearchSession.status.in_(("queued", "running")), SearchSession.created_at < cutoff)
                .with_for_update(skip_locked=True)
                .limit(100)
            )
        ).all()
        for srch in rows:
            srch.status = "failed"
            srch.error = "timeout"
            srch.stage = "done"
            await subscriptions.refund_search(s, srch)


async def upload_retention() -> None:
    days = get_settings().upload_retention_days
    cutoff = datetime.now(UTC) - timedelta(days=days)
    async with session_scope() as s:
        rows = (
            await s.execute(
                select(SearchSession.id, SearchSession.image_key)
                .where(SearchSession.created_at < cutoff, SearchSession.image_key != "")
                .limit(500)
            )
        ).all()
        for sid, key in rows:
            await get_storage().delete(key)
            await s.execute(update(SearchSession).where(SearchSession.id == sid).values(image_key=""))

    # Stored listing photos: dropped for listings nobody has seen or saved for the same period.
    async with session_scope() as s:
        saved = select(Favorite.product_id)
        prods = (
            await s.execute(
                select(Product.id, Product.thumb_key)
                .where(Product.thumb_key.is_not(None), Product.last_seen_at < cutoff, Product.id.not_in(saved))
                .limit(2000)
            )
        ).all()
        for pid, key in prods:
            await get_storage().delete(key)
            await s.execute(update(Product).where(Product.id == pid).values(thumb_key=None, thumb_src=None))


JOBS: list[tuple[str, int, Callable[[], Awaitable[None]]]] = [
    ("expire_subscriptions", 60, expire_subscriptions),
    ("subscription_reminders", 600, subscription_reminders),
    ("trial_notifications", 300, trial_notifications),
    ("marketplace_health", 600, marketplace_health),
    ("refresh_fx", 6 * 3600, refresh_fx),
    ("price_alerts", 1800, price_alerts),
    ("stale_searches", 120, stale_searches),
    ("upload_retention", 24 * 3600, upload_retention),
]


async def _loop(name: str, every: int, fn: Callable[[], Awaitable[None]]) -> None:
    r = get_redis()
    while True:
        # Redis lock so a second scheduler replica would not double-run a job.
        if await r.set(f"sched:lock:{name}", "1", nx=True, ex=max(every - 5, 30)):
            try:
                await fn()
            except Exception:
                log.exception("job %s failed", name)
        await asyncio.sleep(every)


async def main() -> None:
    setup_logging("scheduler")
    log.info("scheduler started with %d jobs", len(JOBS))
    await asyncio.gather(*(_loop(n, e, f) for n, e, f in JOBS))


if __name__ == "__main__":
    asyncio.run(main())
