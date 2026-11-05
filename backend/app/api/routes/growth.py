"""Item screen, collections, item watches, shared finds and gift searches."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, get_session
from app.api.serializers import product_out
from app.core import ratelimit
from app.core.errors import NotFound
from app.db.models import Collection, Favorite, Gift, PriceHistory, Product, SearchResult, SearchSession, Share, User, Watch
from app.schemas.common import (
    CollectionIn,
    CollectionOut,
    FavoriteCollectionIn,
    GiftOut,
    GiftPackOut,
    GiftRedeemOut,
    InvoiceOut,
    ItemOut,
    PricePoint,
    SharedFindOut,
    ShareIn,
    ShareOut,
    WatchesOut,
    WatchOut,
)
from app.services import fx, gifts, offers, shares, subscriptions, watches
from app.services.media import signed_media_url
from app.services.storage import get_storage

router = APIRouter(prefix="/api/v1")


def _cur(user: User) -> str:
    return watches.user_currency(user)


# --------------------------------------------------------------------------------------- item screen
@router.get("/searches/{search_id}/items/{product_id}", response_model=ItemOut)
async def item(
    search_id: uuid.UUID, product_id: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> ItemOut:
    srch = await session.get(SearchSession, search_id)
    if srch is None or srch.user_id != user.id:
        raise NotFound("search_not_found", "Поиск не найден.")
    row = (
        await session.execute(
            select(SearchResult, Product)
            .join(Product, Product.id == SearchResult.product_id)
            .where(SearchResult.search_id == search_id, SearchResult.product_id == product_id)
        )
    ).first()
    if row is None:
        raise NotFound("item_not_found", "Товар не найден.")
    res, product = row
    cur, rates = _cur(user), await fx.rates()
    fav = await session.scalar(select(Favorite).where(Favorite.user_id == user.id, Favorite.product_id == product_id))
    fav_ids = set((await session.scalars(select(Favorite.product_id).where(Favorite.user_id == user.id))).all())
    same = [o for o in await offers.same_item(session, search_id, cur, rates, fav_ids) if o.product_id != product_id]
    # "similar": the best of the rest of this search, not already among the offers
    taken = {product_id, *(o.product_id for o in same)}
    rest = (
        await session.execute(
            select(SearchResult, Product)
            .join(Product, Product.id == SearchResult.product_id)
            .where(
                SearchResult.search_id == search_id,
                SearchResult.is_duplicate.is_(False),
                SearchResult.is_rejected.is_(False),
                SearchResult.product_id.not_in(taken),
            )
            .order_by(SearchResult.rank_score.desc())
            .limit(8)
        )
    ).all()
    history = (
        await session.scalars(select(PriceHistory).where(PriceHistory.product_id == product_id).order_by(PriceHistory.observed_at).limit(60))
    ).all()
    watching = await session.scalar(select(Watch.id).where(Watch.user_id == user.id, Watch.search_id == search_id, Watch.active.is_(True)))
    return ItemOut(
        search_id=search_id,
        product=product_out(product, res.similarity_pct, fav is not None, cur, rates),
        offers=same,
        similar=[product_out(p, r.similarity_pct, p.id in fav_ids, cur, rates) for r, p in rest],
        price_history=[PricePoint(price=h.price, currency=h.currency, at=h.observed_at) for h in history],
        favorite_id=fav.id if fav else None,
        collection_id=fav.collection_id if fav else None,
        watching=watching is not None,
    )


# --------------------------------------------------------------------------------------- collections
async def _collections(session: AsyncSession, user: User) -> list[CollectionOut]:
    rows = (
        await session.execute(
            select(Collection, func.count(Favorite.id))
            .outerjoin(Favorite, Favorite.collection_id == Collection.id)
            .where(Collection.user_id == user.id)
            .group_by(Collection.id)
            .order_by(Collection.created_at)
        )
    ).all()
    out = []
    for c, n in rows:
        cover = await session.scalar(
            select(Product.thumb_key)
            .join(Favorite, Favorite.product_id == Product.id)
            .where(Favorite.collection_id == c.id, Product.thumb_key.is_not(None))
            .order_by(Favorite.created_at.desc())
            .limit(1)
        )
        out.append(CollectionOut(id=c.id, title=c.title, count=int(n), cover_url=signed_media_url(cover) if cover else None))
    return out


@router.get("/collections", response_model=list[CollectionOut])
async def list_collections(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> list[CollectionOut]:
    return await _collections(session, user)


@router.post("/collections", response_model=CollectionOut, status_code=201)
async def create_collection(
    body: CollectionIn, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> CollectionOut:
    n = await session.scalar(select(func.count()).select_from(Collection).where(Collection.user_id == user.id))
    if (n or 0) >= 50:
        from app.core.errors import AppError

        raise AppError("collections_limit", "Не больше 50 коллекций.")
    c = Collection(user_id=user.id, title=body.title.strip())
    session.add(c)
    await session.flush()
    return CollectionOut(id=c.id, title=c.title, count=0, cover_url=None)


async def _own_collection(session: AsyncSession, user: User, cid: int) -> Collection:
    c = await session.get(Collection, cid)
    if c is None or c.user_id != user.id:
        raise NotFound("collection_not_found", "Коллекция не найдена.")
    return c


@router.patch("/collections/{cid}", response_model=CollectionOut)
async def rename_collection(
    cid: int, body: CollectionIn, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> CollectionOut:
    c = await _own_collection(session, user, cid)
    c.title = body.title.strip()
    n = await session.scalar(select(func.count()).select_from(Favorite).where(Favorite.collection_id == cid))
    return CollectionOut(id=c.id, title=c.title, count=int(n or 0), cover_url=None)


@router.delete("/collections/{cid}", status_code=204)
async def delete_collection(cid: int, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> None:
    await session.delete(await _own_collection(session, user, cid))  # favourites stay, collection_id -> NULL


@router.put("/favorites/{favorite_id}/collection", status_code=204)
async def move_favorite(
    favorite_id: int, body: FavoriteCollectionIn, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> None:
    fav = await session.get(Favorite, favorite_id)
    if fav is None or fav.user_id != user.id:
        raise NotFound("favorite_not_found")
    if body.collection_id is not None:
        await _own_collection(session, user, body.collection_id)
    fav.collection_id = body.collection_id


# --------------------------------------------------------------------------------------- watches
def _watch_out(w: Watch, image_key: str | None) -> WatchOut:
    return WatchOut(
        id=w.id,
        search_id=w.search_id,
        title=w.title,
        image_url=signed_media_url(image_key) if image_key else None,
        active=w.active,
        best_price=w.best_price,
        best_currency=w.best_currency,
        runs=w.runs,
        last_run_at=w.last_run_at,
        last_found_at=w.last_found_at,
        last_search_id=w.last_search_id,
    )


@router.get("/watches", response_model=WatchesOut)
async def list_watches(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> WatchesOut:
    rows = (
        await session.execute(
            select(Watch, SearchSession.image_key)
            .join(SearchSession, SearchSession.id == Watch.search_id)
            .where(Watch.user_id == user.id, Watch.active.is_(True))
            .order_by(Watch.created_at.desc())
        )
    ).all()
    ent = await subscriptions.entitlement(session, user)
    return WatchesOut(items=[_watch_out(w, k) for w, k in rows], limit=int(ent.features.get("watch_limit", 0)))


class WatchIn(BaseModel):
    search_id: uuid.UUID


@router.post("/watches", response_model=WatchOut, status_code=201)
async def create_watch(body: WatchIn, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> WatchOut:
    w = await watches.create(session, user, body.search_id)
    key = await session.scalar(select(SearchSession.image_key).where(SearchSession.id == w.search_id))
    return _watch_out(w, key)


@router.delete("/watches/by-search/{search_id}", status_code=204)
async def stop_watch(search_id: uuid.UUID, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> None:
    w = await session.scalar(select(Watch).where(Watch.user_id == user.id, Watch.search_id == search_id))
    if w is not None:
        w.active = False


# --------------------------------------------------------------------------------------- shares
@router.post("/shares", response_model=ShareOut, status_code=201)
async def create_share(body: ShareIn, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> ShareOut:
    await ratelimit.hit(f"share:{user.id}", limit=30, window_seconds=3600)
    share, product = await shares.create(session, user, body.product_id, body.search_id)
    await session.commit()  # the card URL must be fetchable by Telegram before the message is prepared
    prepared = await shares.prepare_message(user, share, product)
    return ShareOut(
        token=share.token,
        link=shares.app_link(f"f_{share.token}"),
        image_url=shares.card_url(share.token),
        text=shares.share_text(product, user),
        prepared_message_id=prepared,
    )


@router.get("/shares/{token}/card.jpg", include_in_schema=False)
async def share_card(token: str, session: AsyncSession = Depends(get_session)) -> Response:
    """Public: Telegram fetches it for the shared message. The token is unguessable."""
    share = await session.get(Share, token)
    if share is None or not share.card_key:
        raise NotFound("share_not_found")
    data = await get_storage().get(share.card_key)
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


@router.get("/shares/{token}", response_model=SharedFindOut)
async def open_share(token: str, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> SharedFindOut:
    share, product, sharer = await shares.open_share(session, token)
    return SharedFindOut(
        token=token,
        sharer_name=sharer.first_name or "Друг",
        product=product_out(product, None, False, _cur(user), await fx.rates()),
        search_id=share.search_id if share.user_id == user.id else None,
    )


# --------------------------------------------------------------------------------------- gifts
@router.get("/gifts/packs", response_model=list[GiftPackOut])
async def gift_packs(session: AsyncSession = Depends(get_session)) -> list[GiftPackOut]:
    return [GiftPackOut(code=p["code"], searches=int(p["searches"]), stars=int(p["stars"])) for p in await gifts.packs(session)]


class GiftInvoiceIn(BaseModel):
    pack: str


@router.post("/gifts/invoice", response_model=InvoiceOut)
async def gift_invoice(body: GiftInvoiceIn, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> InvoiceOut:
    await ratelimit.hit(f"invoice:{user.id}", limit=10, window_seconds=600)
    intent = await gifts.create_invoice(session, user, body.pack)
    assert intent.invoice_link
    return InvoiceOut(intent_id=intent.id, invoice_link=intent.invoice_link, amount_stars=intent.amount_stars, recurring=False)


@router.get("/gifts", response_model=list[GiftOut])
async def my_gifts(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> list[GiftOut]:
    rows = (await session.scalars(select(Gift).where(Gift.buyer_id == user.id).order_by(Gift.created_at.desc()).limit(50))).all()
    return [
        GiftOut(
            code=g.code,
            pack=g.pack,
            searches=g.searches,
            status=g.status,
            link=gifts.gift_link(g.code),
            created_at=g.created_at,
            redeemed_at=g.redeemed_at,
        )
        for g in rows
    ]


@router.post("/gifts/{code}/redeem", response_model=GiftRedeemOut)
async def redeem_gift(code: str, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> GiftRedeemOut:
    await ratelimit.hit(f"gift:{user.id}", limit=20, window_seconds=3600)
    gift, buyer = await gifts.redeem(session, user, code)
    return GiftRedeemOut(searches=gift.searches, from_name=buyer.first_name or "Друг")
