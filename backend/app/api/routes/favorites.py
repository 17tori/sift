from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, get_session
from app.api.serializers import product_out
from app.core.errors import AppError, Forbidden, NotFound
from app.db.models import Favorite, Product, SearchResult, SearchSession, User
from app.schemas.common import FavoriteIn, FavoriteOut, FavoritePatch
from app.services import fx, subscriptions

router = APIRouter(prefix="/api/v1/favorites")


def _cur(user: User) -> str:
    return (user.preferences or {}).get("currency") or ("RUB" if (user.language_code or "").startswith("ru") else "USD")


@router.get("", response_model=list[FavoriteOut])
async def list_favorites(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> list[FavoriteOut]:
    rows = (
        await session.execute(
            select(Favorite, Product)
            .join(Product, Product.id == Favorite.product_id)
            .where(Favorite.user_id == user.id)
            .order_by(Favorite.created_at.desc())
            .limit(500)
        )
    ).all()
    rates = await fx.rates()
    return [
        FavoriteOut(
            id=f.id,
            created_at=f.created_at,
            price_alert=f.price_alert,
            saved_price=f.saved_price,
            saved_currency=f.saved_currency,
            product=product_out(p, None, True, _cur(user), rates),
        )
        for f, p in rows
    ]


@router.post("", response_model=FavoriteOut, status_code=201)
async def add_favorite(body: FavoriteIn, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> FavoriteOut:
    product = await session.get(Product, body.product_id)
    if product is None:
        raise NotFound("product_not_found")
    # Users may only save products that appeared in their own searches (data isolation).
    owned = await session.scalar(
        select(SearchResult.id)
        .join(SearchSession, SearchSession.id == SearchResult.search_id)
        .where(SearchSession.user_id == user.id, SearchResult.product_id == product.id)
        .limit(1)
    )
    if owned is None:
        raise Forbidden("not_your_result")
    ent = await subscriptions.entitlement(session, user)
    cap = int(ent.features.get("favorites_limit", 20))
    count = await session.scalar(select(func.count()).select_from(Favorite).where(Favorite.user_id == user.id))
    if (count or 0) >= cap:
        raise AppError("favorites_limit", f"Лимит избранного на вашем тарифе: {cap}.", status_code=402)
    await session.execute(
        insert(Favorite)
        .values(
            user_id=user.id,
            product_id=product.id,
            search_id=body.search_id,
            saved_price=product.price,
            saved_currency=product.currency,
            price_alert=False,
        )
        .on_conflict_do_nothing(constraint="uq_favorites_user_product")
    )
    fav = await session.scalar(select(Favorite).where(Favorite.user_id == user.id, Favorite.product_id == product.id))
    assert fav is not None
    return FavoriteOut(
        id=fav.id,
        created_at=fav.created_at,
        price_alert=fav.price_alert,
        saved_price=fav.saved_price,
        saved_currency=fav.saved_currency,
        product=product_out(product, None, True, _cur(user), await fx.rates()),
    )


@router.patch("/{favorite_id}", response_model=FavoriteOut)
async def patch_favorite(
    favorite_id: int, body: FavoritePatch, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> FavoriteOut:
    fav = await session.get(Favorite, favorite_id)
    if fav is None or fav.user_id != user.id:
        raise NotFound("favorite_not_found")
    if body.price_alert:
        ent = await subscriptions.entitlement(session, user)
        if not ent.features.get("price_alerts"):
            raise Forbidden("feature_locked", "Уведомления о снижении цены доступны в ULTRA.", required="price_alerts")
    fav.price_alert = body.price_alert
    product = await session.get(Product, fav.product_id)
    assert product is not None
    return FavoriteOut(
        id=fav.id,
        created_at=fav.created_at,
        price_alert=fav.price_alert,
        saved_price=fav.saved_price,
        saved_currency=fav.saved_currency,
        product=product_out(product, None, True, _cur(user), await fx.rates()),
    )


@router.delete("/by-product/{product_id}", status_code=204)
async def remove_favorite(product_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> None:
    fav = await session.scalar(select(Favorite).where(Favorite.user_id == user.id, Favorite.product_id == product_id))
    if fav is not None:
        await session.delete(fav)
