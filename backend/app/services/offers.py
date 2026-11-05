"""Price comparison for one item: listings that visual verification judged to be the same product."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.serializers import product_out
from app.core.config import get_settings
from app.db.models import Product, SearchResult
from app.schemas.common import PriceRange, ProductOut
from app.services import fx


def _comparable(p: Product, currency: str, rates: dict[str, Decimal]) -> Decimal | None:
    if p.price is None:
        return None
    if p.currency == currency:
        return p.price
    return fx.convert(p.price, p.currency, currency, rates) if rates else None


async def same_item(
    session: AsyncSession, search_id: uuid.UUID, currency: str, rates: dict[str, Decimal], favs: set[int] | None = None
) -> list[ProductOut]:
    """Visible listings of the search scored as the same item, with a price, cheapest first."""
    thr = get_settings().same_item_threshold
    rows = (
        await session.execute(
            select(SearchResult, Product)
            .join(Product, Product.id == SearchResult.product_id)
            .where(
                SearchResult.search_id == search_id,
                SearchResult.is_duplicate.is_(False),
                SearchResult.is_rejected.is_(False),
                SearchResult.similarity_pct >= thr,
                Product.price.is_not(None),
            )
        )
    ).all()
    priced = [(r, p, _comparable(p, currency, rates)) for r, p in rows]
    priced = [t for t in priced if t[2] is not None]
    priced.sort(key=lambda t: (t[2], -(t[0].similarity_pct or 0)))
    return [product_out(p, r.similarity_pct, p.id in (favs or set()), currency, rates) for r, p, _ in priced]


def price_range(offers: list[ProductOut], currency: str) -> PriceRange | None:
    """Shown only when the same item is offered on at least two marketplaces."""
    markets = {o.marketplace for o in offers}
    if len(offers) < 2 or len(markets) < 2:
        return None
    lo, hi = offers[0], offers[-1]
    return PriceRange(count=len(offers), marketplaces=len(markets), currency=currency, min=lo, max=hi)
