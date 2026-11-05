"""Redis fixed-window rate limiter (per user and per IP)."""

from __future__ import annotations

import time

from app.core.errors import RateLimited
from app.core.redis import get_redis


async def hit(bucket: str, limit: int, window_seconds: int) -> None:
    r = get_redis()
    window = int(time.time() // window_seconds)
    key = f"rl:{bucket}:{window}"
    pipe = r.pipeline()
    pipe.incr(key)
    pipe.expire(key, window_seconds + 1)
    count, _ = await pipe.execute()
    if int(count) > limit:
        raise RateLimited("rate_limited", "Слишком много запросов. Попробуйте чуть позже.", retry_after=window_seconds)
