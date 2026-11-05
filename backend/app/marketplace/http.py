from __future__ import annotations

import httpx

from app.core.config import get_settings


def client(timeout: float | None = None) -> httpx.AsyncClient:
    s = get_settings()
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout or s.provider_timeout_seconds, connect=5.0),
        headers={"User-Agent": f"{s.brand_name}/1.0 (+https://{s.domain})", "Accept": "application/json"},
        follow_redirects=False,
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    )
