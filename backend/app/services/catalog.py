"""Product upserts and embedding cache shared by the search pipeline and feed imports."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PriceHistory, Product, ProductEmbedding
from app.marketplace.base import NormalizedProduct

_FIELDS = (
    "title",
    "url",
    "image_url",
    "price",
    "currency",
    "condition",
    "brand",
    "category",
    "size",
    "color",
    "country",
    "seller",
    "available",
    "raw",
)


async def upsert_products(session: AsyncSession, items: Sequence[NormalizedProduct]) -> dict[tuple[str, str], int]:
    """Returns {(source, external_id): product_id}. Records price changes in price_history."""
    if not items:
        return {}
    uniq = {(p.source, p.external_id): p for p in items}
    keys = list(uniq.keys())
    before = {
        (r.source, r.external_id): (r.price, r.currency)
        for r in (
            await session.execute(
                select(Product.source, Product.external_id, Product.price, Product.currency).where(
                    tuple_(Product.source, Product.external_id).in_(keys)
                )
            )
        ).all()
    }
    now = datetime.now(UTC)
    rows = [
        {"source": p.source, "external_id": p.external_id, **{f: getattr(p, f) for f in _FIELDS}, "last_seen_at": now} for p in uniq.values()
    ]
    stmt = insert(Product).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_products_source_external",
        set_={f: stmt.excluded[f] for f in (*_FIELDS, "last_seen_at")},
    ).returning(Product.id, Product.source, Product.external_id)
    ids = {(r.source, r.external_id): r.id for r in (await session.execute(stmt)).all()}
    history = []
    for key, p in uniq.items():
        if p.price is None or not p.currency:
            continue
        prev = before.get(key)
        if prev is None or prev[0] != p.price or prev[1] != p.currency:
            history.append({"product_id": ids[key], "price": p.price, "currency": p.currency})
    if history:
        await session.execute(insert(PriceHistory).values(history))
    return ids


async def cached_embeddings(session: AsyncSession, product_ids: Sequence[int], model: str) -> dict[int, list[float]]:
    if not product_ids:
        return {}
    rows = await session.execute(
        select(ProductEmbedding.product_id, ProductEmbedding.embedding, ProductEmbedding.image_url).where(
            ProductEmbedding.product_id.in_(list(product_ids)), ProductEmbedding.model == model
        )
    )
    return {r.product_id: list(r.embedding) for r in rows.all()}


async def store_embeddings(session: AsyncSession, model: str, rows: list[tuple[int, str, list[float]]]) -> None:
    if not rows:
        return
    stmt = insert(ProductEmbedding).values([{"product_id": pid, "model": model, "image_url": url, "embedding": emb} for pid, url, emb in rows])
    stmt = stmt.on_conflict_do_update(
        constraint="uq_product_embeddings_product_model",
        set_={"embedding": stmt.excluded.embedding, "image_url": stmt.excluded.image_url},
    )
    await session.execute(stmt)
