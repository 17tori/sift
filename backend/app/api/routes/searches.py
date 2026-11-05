from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Header, Query, UploadFile
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, get_session
from app.api.serializers import product_out, search_out
from app.core import ratelimit
from app.core.config import get_settings
from app.core.errors import AppError, NotFound
from app.core.redis import get_redis
from app.db.models import Favorite, Product, SearchResult, SearchSession, User
from app.marketplace import registry
from app.schemas.common import HistoryItem, HistoryOut, ResultsOut, SearchOut
from app.services import fx, search_service, subscriptions
from app.services.media import signed_media_url

router = APIRouter(prefix="/api/v1")


async def _own_search(session: AsyncSession, user: User, search_id: uuid.UUID) -> SearchSession:
    s = await session.get(SearchSession, search_id)
    if s is None or s.user_id != user.id or s.hidden:
        raise NotFound("search_not_found", "Поиск не найден.")
    return s


def _dec(v: str | None) -> Decimal | None:
    if v in (None, ""):
        return None
    try:
        d = Decimal(v)
    except Exception as e:  # noqa: BLE001
        raise AppError("bad_number", "Некорректное число.") from e
    if d < 0 or d > Decimal("100000000"):
        raise AppError("bad_number", "Некорректное число.")
    return d


@router.post("/searches", response_model=SearchOut, status_code=201)
async def create_search(
    image: UploadFile = File(...),
    mode: str = Form("similar"),
    marketplaces: str = Form(""),
    price_min: str | None = Form(None),
    price_max: str | None = Form(None),
    condition: Literal["new", "used", ""] = Form(""),
    reference_price: str | None = Form(None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> SearchOut:
    settings = get_settings()
    await ratelimit.hit(f"search:{user.id}", limit=12, window_seconds=60)
    r = get_redis()
    idem_key = f"idem:search:{user.id}:{idempotency_key}" if idempotency_key else None
    if idem_key and (existing := await r.get(idem_key)):
        return search_out(await _own_search(session, user, uuid.UUID(existing)))

    pmin, pmax = _dec(price_min), _dec(price_max)
    opts = {
        "marketplaces": [m for m in (x.strip() for x in marketplaces.split(",")) if m and registry.get(m)],
        "price_min": str(pmin) if pmin is not None else None,
        "price_max": str(pmax) if pmax is not None else None,
        "condition": condition or None,
    }
    raw = await image.read(settings.upload_max_bytes + 1)
    search, is_new = await search_service.create_search(session, user, raw, mode=mode, options=opts, reference_price=_dec(reference_price))
    if is_new:
        search_service.enqueue(search)
    if idem_key:
        await r.set(idem_key, str(search.id), ex=3600)
    return search_out(search)


@router.get("/searches/{search_id}", response_model=SearchOut)
async def get_search(search_id: uuid.UUID, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> SearchOut:
    return search_out(await _own_search(session, user, search_id))


@router.post("/searches/{search_id}/retry", response_model=SearchOut)
async def retry_search(search_id: uuid.UUID, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> SearchOut:
    await ratelimit.hit(f"retry:{user.id}", limit=6, window_seconds=60)
    s = await _own_search(session, user, search_id)
    if s.status not in ("failed",):
        raise AppError("not_retryable", "Этот поиск нельзя перезапустить.")
    if not s.image_key:
        raise AppError("image_expired", "Исходное фото уже удалено. Загрузите его снова.")
    if not s.quota_counted:  # it was refunded -> charge again
        ent, used_bonus = await subscriptions.reserve_search(session, user)
        s.quota_counted, s.used_bonus, s.priority = True, used_bonus, ent.plan.priority
    s.status, s.stage, s.error, s.providers_status, s.finished_at = "queued", "uploaded", None, {}, None
    await session.flush()
    await session.commit()
    search_service.enqueue(s)
    return search_out(s)


@router.delete("/searches/{search_id}", status_code=204)
async def delete_search(search_id: uuid.UUID, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> None:
    s = await _own_search(session, user, search_id)
    s.hidden = True


@router.get("/searches/{search_id}/results", response_model=ResultsOut)
async def search_results(
    search_id: uuid.UUID,
    marketplace: str | None = None,
    price_min: str | None = None,
    price_max: str | None = None,
    condition: str | None = None,
    country: str | None = None,
    category: str | None = None,
    color: str | None = None,
    size: str | None = None,
    sort: Literal["relevance", "similarity", "price_asc", "price_desc"] = "relevance",
    offset: int = Query(0, ge=0, le=2000),
    limit: int = Query(24, ge=1, le=60),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> ResultsOut:
    srch = await _own_search(session, user, search_id)
    ent = await subscriptions.entitlement(session, user)
    advanced = bool(ent.features.get("advanced_filters"))
    locked = not advanced and any(v for v in (condition, country, category, color, size))
    conds = [SearchResult.search_id == srch.id, SearchResult.is_duplicate.is_(False)]
    if marketplace:
        conds.append(SearchResult.provider.in_(marketplace.split(",")))
    pmin, pmax = _dec(price_min), _dec(price_max)
    if pmin is not None:
        conds.append(Product.price >= pmin)
    if pmax is not None:
        conds.append(Product.price <= pmax)
    if advanced:
        if condition:
            conds.append(Product.condition == condition)
        if country:
            conds.append(Product.country == country.upper())
        if category:
            conds.append(Product.category.ilike(f"%{category}%"))
        if color:
            conds.append(or_(Product.color.ilike(f"%{color}%"), Product.title.ilike(f"%{color}%")))
        if size:
            conds.append(or_(Product.size.ilike(f"%{size}%"), Product.title.ilike(f"% {size} %")))
    base = select(SearchResult, Product).join(Product, Product.id == SearchResult.product_id).where(and_(*conds))
    order = {
        "relevance": [SearchResult.rank_score.desc(), SearchResult.id],
        "similarity": [SearchResult.cosine.desc().nulls_last(), SearchResult.id],
        "price_asc": [Product.price.asc().nulls_last(), SearchResult.id],
        "price_desc": [Product.price.desc().nulls_last(), SearchResult.id],
    }[sort]
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    rows = (await session.execute(base.order_by(*order).offset(offset).limit(limit))).all()
    pids = [p.id for _, p in rows]
    favs = (
        set((await session.scalars(select(Favorite.product_id).where(Favorite.user_id == user.id, Favorite.product_id.in_(pids)))).all())
        if pids
        else set()
    )
    rates = await fx.rates()
    currency = (user.preferences or {}).get("currency") or ("RUB" if (user.language_code or "").startswith("ru") else "USD")
    items = [product_out(p, r.similarity_pct, p.id in favs, currency, rates) for r, p in rows]
    facet_rows = (
        await session.execute(
            select(SearchResult.provider, func.count())
            .where(SearchResult.search_id == srch.id, SearchResult.is_duplicate.is_(False))
            .group_by(SearchResult.provider)
        )
    ).all()
    cond_rows = (
        await session.execute(
            select(Product.condition, func.count())
            .join(SearchResult, SearchResult.product_id == Product.id)
            .where(SearchResult.search_id == srch.id, SearchResult.is_duplicate.is_(False), Product.condition.is_not(None))
            .group_by(Product.condition)
        )
    ).all()
    country_rows = (
        await session.execute(
            select(Product.country, func.count())
            .join(SearchResult, SearchResult.product_id == Product.id)
            .where(SearchResult.search_id == srch.id, SearchResult.is_duplicate.is_(False), Product.country.is_not(None))
            .group_by(Product.country)
        )
    ).all()
    nxt = offset + limit
    return ResultsOut(
        items=items,
        total=int(total or 0),
        next_offset=nxt if nxt < int(total or 0) else None,
        facets={
            "marketplace": [{"value": k, "count": v} for k, v in facet_rows],
            "condition": [{"value": k, "count": v} for k, v in cond_rows],
            "country": [{"value": k, "count": v} for k, v in country_rows],
        },
        filters_locked=locked,
    )


@router.get("/history", response_model=HistoryOut)
async def history(
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=50),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> HistoryOut:
    ent = await subscriptions.entitlement(session, user)
    days = int(ent.features.get("history_days", 7))
    q = select(SearchSession).where(
        SearchSession.user_id == user.id, SearchSession.hidden.is_(False), SearchSession.created_at > datetime.now(UTC) - timedelta(days=days)
    )
    if cursor:
        try:
            ts = datetime.fromisoformat(base64.urlsafe_b64decode(cursor.encode()).decode())
        except ValueError as e:
            raise AppError("bad_cursor") from e
        q = q.where(SearchSession.created_at < ts)
    rows = (await session.scalars(q.order_by(SearchSession.created_at.desc()).limit(limit + 1))).all()
    more = len(rows) > limit
    rows = rows[:limit]
    items = [
        HistoryItem(
            id=s.id,
            status=s.status,
            mode=s.mode,
            created_at=s.created_at,
            image_url=signed_media_url(s.image_key) if s.image_key else None,
            title=(s.analysis or {}).get("title_ru") or (s.analysis or {}).get("title_en"),
            results_count=s.results_count,
        )
        for s in rows
    ]
    nxt = base64.urlsafe_b64encode(rows[-1].created_at.isoformat().encode()).decode() if more and rows else None
    return HistoryOut(items=items, next_cursor=nxt, limited_days=days if days < 3650 else None)
