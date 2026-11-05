"""Licensed product feeds (YML / CSV from affiliate networks or direct partnerships).

Products are imported into `products` + `product_embeddings`, and searched with pgvector
(true visual nearest-neighbour search). This is the legal route for marketplaces that do
not offer a public search API but do publish partner feeds (e.g. Wildberries via an
affiliate network that holds a WB offer).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from app.db.models import Product, ProductEmbedding
from app.db.session import session_scope
from app.marketplace.base import (
    IntegrationKind,
    MarketplaceProvider,
    NormalizedProduct,
    ProviderState,
    ProviderUnavailable,
    SearchQuery,
)


class FeedCatalogProvider(MarketplaceProvider):
    kind = IntegrationKind.PARTNER_FEED
    supports_image_search = True

    def __init__(self, enabled: bool) -> None:
        super().__init__(enabled)
        self._has_items: bool | None = None

    def configured(self) -> bool:
        # Refreshed by refresh_state(); optimistic until the first check.
        return self._has_items is not False

    async def prepare(self) -> None:
        if self._has_items is None:
            await self.refresh_state()

    async def refresh_state(self) -> None:
        async with session_scope() as s:
            n = await s.scalar(select(func.count()).select_from(ProductEmbedding).join(Product).where(Product.source == self.code))
        self._has_items = bool(n)

    async def search(self, query: SearchQuery) -> list[NormalizedProduct]:
        self.ensure_usable()
        if query.query_embedding is None or not query.embedding_model:
            raise ProviderUnavailable(ProviderState.NOT_CONFIGURED, "нужен embedding запроса")
        dist = ProductEmbedding.embedding.cosine_distance(query.query_embedding)
        stmt = (
            select(Product)
            .join(ProductEmbedding, ProductEmbedding.product_id == Product.id)
            .where(Product.source == self.code, ProductEmbedding.model == query.embedding_model)
            .order_by(dist)
            .limit(query.limit)
        )
        if query.price_min is not None:
            stmt = stmt.where(Product.price >= query.price_min)
        if query.price_max is not None:
            stmt = stmt.where(Product.price <= query.price_max)
        if query.condition:
            stmt = stmt.where(Product.condition == query.condition)
        async with session_scope() as s:
            await s.execute(select(func.set_config("hnsw.ef_search", "80", True)))
            rows = (await s.scalars(stmt)).all()
        if not rows and self._has_items is None:
            await self.refresh_state()
        return [self._from_row(p) for p in rows]

    @staticmethod
    def _from_row(p: Product) -> NormalizedProduct:
        return NormalizedProduct(
            source=p.source,
            external_id=p.external_id,
            title=p.title,
            url=p.url,
            image_url=p.image_url,
            price=p.price,
            currency=p.currency,
            condition=p.condition,
            brand=p.brand,
            category=p.category,
            size=p.size,
            color=p.color,
            country=p.country,
            seller=p.seller,
            available=p.available,
            raw={},
        )

    def normalize_product(self, raw: dict[str, Any]) -> NormalizedProduct | None:
        from app.cli.feeds import normalize_feed_offer

        return normalize_feed_offer(self.code, raw)

    async def get_product(self, external_id: str) -> NormalizedProduct | None:
        async with session_scope() as s:
            p = await s.scalar(select(Product).where(Product.source == self.code, Product.external_id == external_id))
        return self._from_row(p) if p else None


class WildberriesProvider(FeedCatalogProvider):
    code = "wildberries"
    name = "Wildberries"
    url = "https://www.wildberries.ru"
    regions = ["RU", "BY", "KZ", "AM", "KG", "UZ"]
    languages = ("ru",)
    note = (
        "У Wildberries нет публичного API поиска для сторонних сервисов (Seller API — только "
        "свои товары). Подключение через лицензированный партнёрский фид: импортируйте его "
        "командой `python -m app.cli.feeds import --source wildberries ...`."
    )

    # Until a licensed feed is imported, Wildberries is served through the web sources (see app/marketplace/web.py).
    def _web(self) -> bool:
        from app.marketplace import web

        return self._has_items is False and web.web_enabled_for(self.code)

    def configured(self) -> bool:
        return super().configured() or self._web()

    @property
    def timeout_seconds(self) -> float | None:  # type: ignore[override]
        from app.marketplace import web

        return web.web_timeout() if self._web() else None

    def info(self):  # type: ignore[no-untyped-def]
        i = super().info()
        if self._web():
            from app.marketplace.web import WEB_NOTE

            i.kind, i.note = IntegrationKind.WEB_SEARCH, WEB_NOTE
        return i

    async def search(self, query: SearchQuery) -> list[NormalizedProduct]:
        if self._has_items is None:
            await self.refresh_state()
        if self._web():
            from app.marketplace import web

            return await web.search_for(self.code, query)
        return await super().search(query)
