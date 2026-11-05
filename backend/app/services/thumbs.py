"""Our own copies of listing photos.

Cards show the photo the search found for each listing. Marketplace CDNs often refuse hotlinking from a
Mini App (referrer checks, expiring URLs), so the worker fetches each found image once (SSRF-safe,
size-bounded, 384px JPEG), keeps it in storage and the API hands out signed URLs to it. The remote URL
stays as the fallback. A listing whose photo URL changes gets a fresh copy.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from sqlalchemy import select, text

from app.db.models import Product
from app.db.session import session_scope
from app.marketplace.base import NormalizedProduct
from app.services.remote_images import fetch_many
from app.services.storage import get_storage

log = logging.getLogger(__name__)
PREFIX = "thumbs"


async def thumb_state(product_ids: Sequence[int]) -> dict[int, tuple[str | None, str | None]]:
    if not product_ids:
        return {}
    async with session_scope() as s:
        rows = await s.execute(select(Product.id, Product.thumb_key, Product.thumb_src).where(Product.id.in_(list(product_ids))))
        return {r.id: (r.thumb_key, r.thumb_src) for r in rows.all()}


async def _save(pid: int, key: str | None, src: str) -> None:
    async with session_scope() as s:
        old = (
            await s.execute(
                text(
                    "UPDATE products p SET thumb_key = COALESCE(:k, o.thumb_key), thumb_src = :src "
                    "FROM (SELECT id, thumb_key FROM products WHERE id = :id FOR UPDATE) o "
                    "WHERE p.id = o.id RETURNING o.thumb_key"
                ),
                {"k": key, "src": src, "id": pid},
            )
        ).scalar_one_or_none()
    if key and old and old != key:
        await get_storage().delete(old)


async def ensure_thumbs(items: Sequence[tuple[int, NormalizedProduct]]) -> dict[int, bytes]:
    """Fetches and stores photos for listings that have none yet (or whose photo URL changed).
    Returns {product_id: jpeg} for what was fetched now, so embeddings can reuse the bytes."""
    with_img = [(pid, p) for pid, p in items if p.image_url]
    if not with_img:
        return {}
    state = await thumb_state([pid for pid, _ in with_img])
    need = {pid: p for pid, p in with_img if state.get(pid, (None, None))[1] != p.image_url}
    if not need:
        return {}
    got = await fetch_many([p.image_url for p in need.values() if p.image_url])
    out: dict[int, bytes] = {pid: got[p.image_url] for pid, p in need.items() if p.image_url in got}
    alts = {pid: str(p.raw.get("image_alt")) for pid, p in need.items() if pid not in out and p.raw.get("image_alt")}
    if alts:
        got_alt = await fetch_many(list(alts.values()))
        out.update({pid: got_alt[u] for pid, u in alts.items() if u in got_alt})
    storage = get_storage()
    for pid, p in need.items():
        key = await storage.put(out[pid], "jpg", PREFIX) if pid in out else None
        # A failed fetch is remembered too (src set, key kept): the card falls back to the remote URL
        # and we do not hammer a CDN that refused us until the listing's photo URL changes.
        await _save(pid, key, p.image_url or "")
    log.info("thumbs: %d fetched of %d needed", len(out), len(need))
    return out


async def read_thumbs(keys: dict[int, str]) -> dict[int, bytes]:
    storage = get_storage()
    out: dict[int, bytes] = {}
    for pid, key in keys.items():
        try:
            out[pid] = await storage.get(key)
        except (OSError, ValueError):
            continue
    return out
