from __future__ import annotations

from decimal import Decimal

from app.db.models import Product, SearchSession
from app.marketplace import registry
from app.schemas.common import MarketplaceOut, ProductOut, SearchOut
from app.services import fx
from app.services.media import signed_media_url


def marketplace_out(code: str) -> MarketplaceOut | None:
    p = registry.get(code)
    if p is None:
        return None
    i = p.info()
    return MarketplaceOut(
        code=i.code,
        name=i.name,
        url=i.url,
        kind=i.kind.value,
        state=i.state.value,
        note=i.note,
        supports_image_search=i.supports_image_search,
        regions=i.regions,
    )


def product_out(p: Product, similarity: int | None, is_fav: bool, currency: str, rates: dict[str, Decimal]) -> ProductOut:
    provider = registry.get(p.source)
    conv = fx.convert(p.price, p.currency, currency, rates) if rates and p.currency != currency else None
    return ProductOut(
        product_id=p.id,
        marketplace=p.source,
        marketplace_name=provider.name if provider else p.source,
        title=p.title,
        url=p.url,
        image_url=signed_media_url(p.thumb_key) if p.thumb_key else p.image_url,
        image_fallback_url=p.image_url if p.thumb_key else None,
        price=p.price,
        currency=p.currency,
        price_converted=conv,
        converted_currency=currency if conv is not None else None,
        similarity=similarity,
        available=p.available,
        condition=p.condition,
        brand=p.brand,
        category=p.category,
        size=p.size,
        color=p.color,
        country=p.country,
        seller=p.seller,
        is_favorite=is_fav,
        via=(p.raw or {}).get("via"),
    )


_ANALYSIS_PUBLIC = (
    "is_product",
    "category",
    "subcategory",
    "title_en",
    "title_ru",
    "gender",
    "colors",
    "material",
    "pattern",
    "silhouette",
    "style",
    "features",
    "brand",
    "palette",
    "vision_error",
)


def search_out(s: SearchSession) -> SearchOut:
    analysis = {k: v for k, v in (s.analysis or {}).items() if k in _ANALYSIS_PUBLIC} if s.analysis else None
    return SearchOut(
        id=s.id,
        status=s.status,
        stage=s.stage,
        mode=s.mode,
        created_at=s.created_at,
        finished_at=s.finished_at,
        image_url=signed_media_url(s.image_key) if s.image_key else None,
        analysis=analysis,
        providers=s.providers_status or {},
        results_count=s.results_count,
        error=s.error,
        reference_price=s.reference_price,
        reference_currency=s.reference_currency,
        has_similarity=s.embedding_model is not None or bool((s.analysis or {}).get("similarity_model")),
    )
