"""Import licensed partner product feeds (Yandex YML or CSV) and embed their images.

Usage (inside the backend container):
  python -m app.cli.feeds import --source wildberries --url https://partner.example/feed.yml --format yml
  python -m app.cli.feeds import --source wildberries --path /data/feeds/wb.csv --format csv
  python -m app.cli.feeds embed --source wildberries --batch 64

CSV columns: id,title,url,image_url,price,currency,brand,category,size,color,condition,available
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select

from app.ai.embeddings import build_embedding_provider
from app.core.logging import setup_logging
from app.db.models import Product, ProductEmbedding
from app.db.session import session_scope
from app.marketplace.base import NormalizedProduct, to_decimal
from app.services.catalog import store_embeddings, upsert_products
from app.services.remote_images import fetch_many

log = logging.getLogger("feeds")
MAX_FEED_BYTES = 2 * 1024 * 1024 * 1024


def normalize_feed_offer(source: str, raw: dict[str, Any]) -> NormalizedProduct | None:
    ext = str(raw.get("id") or "").strip()
    title = str(raw.get("title") or "").strip()
    url = str(raw.get("url") or "").strip()
    if not (ext and title and url.startswith("http")):
        return None
    avail = raw.get("available")
    return NormalizedProduct(
        source=source,
        external_id=ext[:128],
        title=title[:500],
        url=url,
        image_url=(raw.get("image_url") or None),
        price=to_decimal(raw.get("price")),
        currency=(raw.get("currency") or "RUB").upper()[:8],
        condition=(raw.get("condition") or "new"),
        brand=raw.get("brand") or None,
        category=raw.get("category") or None,
        size=raw.get("size") or None,
        color=raw.get("color") or None,
        country=raw.get("country") or None,
        seller=raw.get("seller") or None,
        available=None if avail in (None, "") else str(avail).lower() in ("true", "1", "yes"),
        raw={},
    )


def iter_yml(path: Path) -> Iterator[dict[str, Any]]:
    categories: dict[str, str] = {}
    for _, el in ET.iterparse(path, events=("end",)):  # noqa: S314 - feed from a contracted partner
        if el.tag == "category" and el.get("id"):
            categories[el.get("id", "")] = (el.text or "").strip()
            el.clear()
        elif el.tag == "offer":
            params = {(p.get("name") or "").lower(): (p.text or "").strip() for p in el.findall("param")}
            yield {
                "id": el.get("id"),
                "available": el.get("available"),
                "title": el.findtext("name") or el.findtext("model") or "",
                "url": el.findtext("url") or "",
                "image_url": el.findtext("picture"),
                "price": el.findtext("price"),
                "currency": el.findtext("currencyId"),
                "brand": el.findtext("vendor"),
                "category": categories.get(el.findtext("categoryId") or ""),
                "size": params.get("размер") or params.get("size"),
                "color": params.get("цвет") or params.get("color"),
            }
            el.clear()


def iter_csv(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as f:
        yield from csv.DictReader(f)


async def _download(url: str) -> Path:
    tmp = Path(tempfile.mkstemp(suffix=".feed")[1])
    async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=15), follow_redirects=True) as c:
        async with c.stream("GET", url) as r:
            r.raise_for_status()
            size = 0
            with tmp.open("wb") as f:  # noqa: ASYNC230 - CLI download
                async for chunk in r.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_FEED_BYTES:
                        raise RuntimeError("feed too large")
                    f.write(chunk)
    return tmp


async def import_feed(source: str, path: Path, fmt: str, batch: int = 500) -> int:
    rows = iter_yml(path) if fmt == "yml" else iter_csv(path)
    total, buf = 0, []
    for raw in rows:
        p = normalize_feed_offer(source, raw)
        if p:
            buf.append(p)
        if len(buf) >= batch:
            async with session_scope() as s:
                await upsert_products(s, buf)
            total += len(buf)
            buf = []
            log.info("imported %s", total)
    if buf:
        async with session_scope() as s:
            await upsert_products(s, buf)
        total += len(buf)
    return total


async def embed_missing(source: str, batch: int = 64, limit: int | None = None) -> int:
    provider = build_embedding_provider()
    done = 0
    while limit is None or done < limit:
        async with session_scope() as s:
            rows = (
                await s.execute(
                    select(Product.id, Product.image_url)
                    .outerjoin(ProductEmbedding, (ProductEmbedding.product_id == Product.id) & (ProductEmbedding.model == provider.model_id))
                    .where(Product.source == source, Product.image_url.is_not(None), ProductEmbedding.id.is_(None))
                    .limit(batch)
                )
            ).all()
        if not rows:
            break
        thumbs = await fetch_many([r.image_url for r in rows])
        todo = [(r.id, r.image_url) for r in rows if r.image_url in thumbs]
        if todo:
            vecs = await provider.embed_images([thumbs[u] for _, u in todo])
            async with session_scope() as s:
                await store_embeddings(s, provider.model_id, [(pid, u, v) for (pid, u), v in zip(todo, vecs, strict=True)])
        failed = [r.id for r in rows if r.image_url not in thumbs]
        if failed:  # unreachable images: drop the image so we do not retry forever
            async with session_scope() as s:
                await s.execute(Product.__table__.update().where(Product.id.in_(failed)).values(image_url=None))
        done += len(rows)
        log.info("embedded %s", done)
    return done


def main() -> None:
    setup_logging("feeds")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    imp = sub.add_parser("import")
    imp.add_argument("--source", required=True)
    imp.add_argument("--format", choices=["yml", "csv"], default="yml")
    g = imp.add_mutually_exclusive_group(required=True)
    g.add_argument("--url")
    g.add_argument("--path")
    emb = sub.add_parser("embed")
    emb.add_argument("--source", required=True)
    emb.add_argument("--batch", type=int, default=64)
    emb.add_argument("--limit", type=int)
    a = ap.parse_args()

    async def run() -> None:
        if a.cmd == "import":
            path = await _download(a.url) if a.url else Path(a.path)
            n = await import_feed(a.source, path, a.format)
            print(f"imported {n} offers into source={a.source}; now run: python -m app.cli.feeds embed --source {a.source}")
        else:
            n = await embed_missing(a.source, a.batch, a.limit)
            print(f"embedded {n} products")

    asyncio.run(run())


if __name__ == "__main__":
    main()
