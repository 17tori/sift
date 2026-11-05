"""Background actors. Run with:
dramatiq app.workers.actors --processes 1 --threads 4 --queues search_priority search maintenance
"""

from __future__ import annotations

import logging
import uuid

import dramatiq

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.redis import get_redis
from app.workers.broker import QUEUE_DEFAULT, QUEUE_MAINTENANCE, QUEUE_PRIORITY

setup_logging("worker")
log = logging.getLogger(__name__)
FREE_SLOTS_KEY = "sift:free_search_slots"
FREE_CONCURRENCY = 2  # free searches never take more than this many worker threads


async def _run(search_id: str) -> None:
    from app.search.pipeline import run_search

    await run_search(uuid.UUID(search_id))


@dramatiq.actor(queue_name=QUEUE_PRIORITY, max_retries=0, time_limit=180_000)
async def run_search_priority(search_id: str) -> None:
    await _run(search_id)


@dramatiq.actor(queue_name=QUEUE_DEFAULT, max_retries=0, time_limit=180_000)
async def run_search_default(search_id: str) -> None:
    r = get_redis()
    in_flight = await r.incr(FREE_SLOTS_KEY)
    await r.expire(FREE_SLOTS_KEY, 300)
    try:
        if in_flight > FREE_CONCURRENCY:
            # Leave capacity for paid users: re-queue with a short delay instead of blocking.
            run_search_default.send_with_options(args=(search_id,), delay=1500)
            return
        await _run(search_id)
    finally:
        await r.decr(FREE_SLOTS_KEY)


def enqueue_search(search_id: uuid.UUID, priority: int) -> None:
    if priority > 0:
        run_search_priority.send(str(search_id))
    else:
        run_search_default.send(str(search_id))


@dramatiq.actor(queue_name=QUEUE_MAINTENANCE, max_retries=3, time_limit=600_000)
async def embed_feed_products(source: str, limit: int = 2000) -> None:
    from app.cli.feeds import embed_missing

    n = await embed_missing(source, batch=get_settings().embedding_batch_size, limit=limit)
    log.info("embedded %s products for %s", n, source)
