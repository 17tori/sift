"""Short-lived signed URLs so <img> tags in the Mini App can load private uploads."""

from __future__ import annotations

import time
from urllib.parse import quote

from app.core.config import get_settings
from app.core.security import hmac_sign, hmac_verify


def signed_media_url(key: str) -> str:
    s = get_settings()
    exp = int(time.time()) + s.media_url_ttl_seconds
    exp -= exp % 300  # stable URLs for 5 minutes -> browser cache friendly
    sig = hmac_sign(s.secret_key.get_secret_value(), f"{key}:{exp}")
    return f"/api/v1/media/{quote(key)}?exp={exp}&sig={sig}"


def verify_media(key: str, exp: int, sig: str) -> bool:
    if exp < time.time():
        return False
    return hmac_verify(get_settings().secret_key.get_secret_value(), f"{key}:{exp}", sig)
