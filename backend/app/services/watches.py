"""Item watches (ULTRA): the saved photo is searched again every WATCH_INTERVAL_HOURS.

The user hears about it when the same item (visually verified) appears cheaper than the best price seen so far,
or when a new listing of it appears on any marketplace. Re-runs are hidden searches that do not use the quota.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError, Forbidden, NotFound
from app.db.models import SearchResult, SearchSession, User, Watch
from app.db.session import session_scope
from app.services import fx, notifications, offers, subscriptions
from app.services.shares import format_price

log = logging.getLogger(__name__)
CHEAPER_BY = Decimal("0.97")  # notify when at least 3 % cheaper than the best price seen


def user_currency(user: User) -> str:
    return (user.preferences or {}).get("currency") or ("RUB" if (user.language_code or "").startswith("ru") else "USD")


async def _visible_ids(session: AsyncSession, search_id: uuid.UUID) -> list[int]:
    rows = await session.scalars(
        select(SearchResult.product_id).where(
            SearchResult.search_id == search_id, SearchResult.is_duplicate.is_(False), SearchResult.is_rejected.is_(False)
        )
    )
    return list(rows.all())


async def create(session: AsyncSession, user: User, search_id: uuid.UUID) -> Watch:
    srch = await session.get(SearchSession, search_id)
    if srch is None or srch.user_id != user.id:
        raise NotFound("search_not_found")
    if srch.status != "completed" or not srch.image_key:
        raise AppError("search_not_ready", "Следить можно за завершённым поиском.")
    ent = await subscriptions.entitlement(session, user)
    limit = int(ent.features.get("watch_limit", 0))
    if limit <= 0:
        raise Forbidden("feature_locked", "Отслеживание вещей доступно в ULTRA.", required="watch_limit")
    w = await session.scalar(select(Watch).where(Watch.user_id == user.id, Watch.search_id == search_id))
    active = await session.scalar(select(func.count()).select_from(Watch).where(Watch.user_id == user.id, Watch.active.is_(True)))
    if (w is None or not w.active) and (active or 0) >= limit:
        raise AppError("watch_limit", f"На вашем тарифе можно следить за {limit} вещами.", status_code=402)
    cur = user_currency(user)
    same = await offers.same_item(session, search_id, cur, await fx.rates())
    best = same[0] if same else None
    title = (srch.analysis or {}).get("title_ru") or (srch.analysis or {}).get("title_en")
    if w is None:
        w = Watch(user_id=user.id, search_id=search_id, known_product_ids=[])
        session.add(w)
    w.active = True
    w.title = (title or "Вещь")[:160]
    w.best_price = (best.price_converted or best.price) if best else None
    w.best_currency = (best.converted_currency or best.currency) if best else None
    w.known_product_ids = await _visible_ids(session, search_id)
    w.last_run_at = datetime.now(UTC)
    await session.flush()
    return w


async def _rerun(watch: Watch, origin: SearchSession) -> uuid.UUID:
    from app.search.pipeline import run_search  # heavy import, only in the scheduler

    async with session_scope() as s:
        clone = SearchSession(
            user_id=origin.user_id,
            status="queued",
            stage="uploaded",
            mode=origin.mode,
            image_key=origin.image_key,
            image_hash=origin.image_hash,
            image_width=origin.image_width,
            image_height=origin.image_height,
            options={**(origin.options or {}), "watch_id": watch.id},
            quota_counted=False,
            used_bonus=False,
            priority=0,
            hidden=True,
            providers_status={},
        )
        s.add(clone)
        await s.flush()
        sid = clone.id
    await run_search(sid)
    return sid


async def evaluate(watch_id: int, search_id: uuid.UUID) -> str | None:
    """Compares a re-run with what the user already knows. Returns the notification text, if any."""
    async with session_scope() as s:
        w = await s.get(Watch, watch_id, with_for_update=True)
        srch = await s.get(SearchSession, search_id)
        if w is None or srch is None:
            return None
        user = await s.get(User, w.user_id)
        assert user is not None
        w.runs += 1
        w.last_run_at = datetime.now(UTC)
        w.last_search_id = search_id
        if srch.status != "completed":
            return None
        cur = user_currency(user)
        rates = await fx.rates()
        same = await offers.same_item(s, search_id, cur, rates)
        known = set(w.known_product_ids or [])
        fresh = [o for o in same if o.product_id not in known]
        best = same[0] if same else None
        best_price = (best.price_converted or best.price) if best else None
        best_cur = (best.converted_currency or best.currency) if best else None
        lines: list[str] = []
        if best and best_price is not None and (w.best_price is None or best_cur != w.best_currency or best_price < w.best_price * CHEAPER_BY):
            if w.best_price is not None and best_cur == w.best_currency:
                lines.append(
                    f"Дешевле: <b>{format_price(best_price, best_cur)}</b> на {best.marketplace_name} "
                    f"(было {format_price(w.best_price, w.best_currency)})"
                )
            w.best_price, w.best_currency = best_price, best_cur
        if fresh:
            markets = sorted({o.marketplace_name for o in fresh})
            lines.append(f"Новые предложения: {len(fresh)} на {', '.join(markets)}")
        w.known_product_ids = sorted(known | set(await _visible_ids(s, search_id)))
        if not lines:
            return None
        w.last_found_at = datetime.now(UTC)
        return f"Нашлось по вашей вещи «{w.title}»:\n" + "\n".join(lines)


async def run_due(limit: int = 10) -> int:
    hours = get_settings().watch_interval_hours
    async with session_scope() as s:
        due = (
            await s.execute(
                select(Watch, SearchSession, User)
                .join(SearchSession, SearchSession.id == Watch.search_id)
                .join(User, User.id == Watch.user_id)
                .where(
                    Watch.active.is_(True),
                    User.is_blocked.is_(False),
                    (Watch.last_run_at.is_(None)) | (Watch.last_run_at < datetime.now(UTC) - timedelta(hours=hours)),
                )
                .order_by(Watch.last_run_at.asc().nulls_first())
                .limit(limit)
            )
        ).all()
    done = 0
    for watch, origin, user in due:
        async with session_scope() as s:
            ent = await subscriptions.entitlement(s, user)
            if int(ent.features.get("watch_limit", 0)) <= 0 or not origin.image_key:
                await s.execute(update(Watch).where(Watch.id == watch.id).values(active=False))
                continue
        try:
            sid = await _rerun(watch, origin)
            text = await evaluate(watch.id, sid)
        except Exception:
            log.exception("watch %s failed", watch.id)
            async with session_scope() as s:
                await s.execute(update(Watch).where(Watch.id == watch.id).values(last_run_at=datetime.now(UTC)))
            continue
        done += 1
        if text:
            await notifications.send(user.id, user.telegram_id, text, ("Смотреть", f"search/{sid}"))
    return done


async def watched_image_keys(session: AsyncSession) -> set[str]:
    rows = await session.scalars(select(SearchSession.image_key).join(Watch, Watch.search_id == SearchSession.id).where(Watch.active.is_(True)))
    return set(rows.all())
