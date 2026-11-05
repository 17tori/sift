"""Structured logging. ERROR records are mirrored to Redis so the admin panel can show them."""

from __future__ import annotations

import logging
import sys
import time
import traceback

import orjson

from app.core.config import get_settings

ERRORS_KEY = "sift:errors"
ERRORS_MAX = 1000


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": round(record.created, 3),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "ctx", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return orjson.dumps(payload, default=str).decode()


class RedisErrorSink(logging.Handler):
    """Pushes ERROR+ records to a capped Redis list. Never raises."""

    def __init__(self, redis_url: str, service: str) -> None:
        super().__init__(level=logging.ERROR)
        import redis as sync_redis

        self._r = sync_redis.Redis.from_url(redis_url, socket_timeout=0.5, socket_connect_timeout=0.5)
        self._service = service

    def emit(self, record: logging.LogRecord) -> None:
        try:
            item = {
                "ts": record.created,
                "service": self._service,
                "logger": record.name,
                "msg": record.getMessage()[:2000],
                "exc": "".join(traceback.format_exception(*record.exc_info))[-4000:] if record.exc_info else None,
            }
            pipe = self._r.pipeline()
            pipe.lpush(ERRORS_KEY, orjson.dumps(item))
            pipe.ltrim(ERRORS_KEY, 0, ERRORS_MAX - 1)
            pipe.execute()
        except Exception:  # noqa: BLE001 - logging must never break the app
            pass


def setup_logging(service: str) -> None:
    s = get_settings()
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(s.log_level.upper())
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(JsonFormatter() if s.log_json else logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(h)
    if s.environment != "test":
        root.addHandler(RedisErrorSink(s.redis_url, service))
    for noisy in ("httpx", "httpcore", "aiogram.event", "dramatiq.worker"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    logging.Formatter.converter = time.gmtime
