"""Fetches marketplace thumbnails for visual matching. SSRF-safe and size-bounded."""

from __future__ import annotations

import asyncio
import io
import ipaddress
import logging
import socket
from urllib.parse import urlparse

import httpx
from PIL import Image, UnidentifiedImageError

from app.core.config import get_settings

log = logging.getLogger(__name__)
THUMB_SIDE = 384


async def _public_host(host: str) -> bool:
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return True


def to_thumb_jpeg(data: bytes) -> bytes | None:
    Image.MAX_IMAGE_PIXELS = 30_000_000
    try:
        with Image.open(io.BytesIO(data)) as im:
            im = im.convert("RGB")
            im.thumbnail((THUMB_SIDE, THUMB_SIDE))
            out = io.BytesIO()
            im.save(out, "JPEG", quality=85)
            return out.getvalue()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError):
        return None


async def fetch_thumb(client: httpx.AsyncClient, url: str) -> bytes | None:
    s = get_settings()
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname or not await _public_host(u.hostname):
        return None
    try:
        async with client.stream("GET", url) as r:
            if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image/"):
                return None
            buf = bytearray()
            async for chunk in r.aiter_bytes():
                buf.extend(chunk)
                if len(buf) > s.candidate_image_max_bytes:
                    return None
    except httpx.HTTPError:
        return None
    return await asyncio.to_thread(to_thumb_jpeg, bytes(buf))


async def fetch_many(urls: list[str], concurrency: int = 12) -> dict[str, bytes]:
    sem = asyncio.Semaphore(concurrency)
    out: dict[str, bytes] = {}
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(8.0, connect=4.0), follow_redirects=True, headers={"User-Agent": f"{get_settings().brand_name}/1.0"}
    ) as client:

        async def one(url: str) -> None:
            async with sem:
                data = await fetch_thumb(client, url)
                if data:
                    out[url] = data

        await asyncio.gather(*(one(u) for u in dict.fromkeys(urls)))
    return out
