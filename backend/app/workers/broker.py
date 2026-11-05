"""Dramatiq broker (Redis) with asyncio support. Import this before defining actors."""

from __future__ import annotations

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.middleware.asyncio import AsyncIO

from app.core.config import get_settings

broker = RedisBroker(url=get_settings().broker_url)
broker.add_middleware(AsyncIO())
dramatiq.set_broker(broker)

QUEUE_PRIORITY = "search_priority"
QUEUE_DEFAULT = "search"
QUEUE_MAINTENANCE = "maintenance"
