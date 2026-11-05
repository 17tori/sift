"""Creating a search session: shared by the Mini App API and the bot (photo messages)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError, Forbidden
from app.db.models import SearchSession, User
from app.services import images, subscriptions
from app.services.storage import get_storage

MODES = ("exact", "similar", "cheaper", "discover")


async def create_search(
    session: AsyncSession,
    user: User,
    raw: bytes,
    *,
    mode: str = "similar",
    options: dict[str, Any] | None = None,
    reference_price: Decimal | None = None,
) -> tuple[SearchSession, bool]:
    """Returns (search, is_new). Commits so the worker can see the row; caller enqueues if is_new."""
    s = get_settings()
    if mode not in MODES:
        raise AppError("bad_mode", "Неизвестный режим поиска.")
    norm = images.normalize(raw, max_bytes=s.upload_max_bytes, max_pixels=s.upload_max_pixels, max_side=s.upload_normalized_max_side)
    ent = await subscriptions.entitlement(session, user)
    if mode not in ent.features.get("modes", ["similar"]):
        raise Forbidden("mode_locked", "Этот режим доступен на старших тарифах.", required=mode)
    opts = options or {"marketplaces": [], "price_min": None, "price_max": None, "condition": None}

    recent = await session.scalar(
        select(SearchSession)
        .where(
            SearchSession.user_id == user.id,
            SearchSession.image_hash == norm.dhash,
            SearchSession.mode == mode,
            SearchSession.hidden.is_(False),
            SearchSession.status.in_(("queued", "running", "completed")),
            SearchSession.created_at > datetime.now(UTC) - timedelta(minutes=10),
        )
        .order_by(SearchSession.created_at.desc())
        .limit(1)
    )
    if recent is not None and (recent.options or {}) == opts:
        return recent, False

    ent, used_bonus = await subscriptions.reserve_search(session, user)
    key = await get_storage().put(norm.data, "jpg", "uploads")
    search = SearchSession(
        user_id=user.id,
        status="queued",
        stage="uploaded",
        mode=mode,
        image_key=key,
        image_hash=norm.dhash,
        image_width=norm.width,
        image_height=norm.height,
        options=opts,
        reference_price=reference_price,
        reference_currency=((user.preferences or {}).get("currency") or "RUB") if reference_price else None,
        quota_counted=True,
        used_bonus=used_bonus,
        priority=ent.plan.priority,
        providers_status={},
    )
    session.add(search)
    await session.flush()
    await session.commit()
    return search, True


def enqueue(search: SearchSession) -> None:
    from app.workers.actors import enqueue_search

    enqueue_search(search.id, search.priority)
