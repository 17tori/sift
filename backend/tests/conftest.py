from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://sift:sift@localhost:5432/sift_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("BROKER_URL", "redis://localhost:6379/14")
os.environ.setdefault("BOT_TOKEN", "123456:TEST-TOKEN")
os.environ.setdefault("BOT_USERNAME", "sift_test_bot")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ADMIN_TELEGRAM_IDS", "999")
os.environ.setdefault("LOG_JSON", "false")
os.environ.setdefault("STORAGE_PATH", str(Path(__file__).parent / ".storage"))

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy import text  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _db_available() -> bool:
    import socket

    try:
        socket.create_connection(("localhost", 5432), timeout=1).close()
        return True
    except OSError:
        return False


@pytest.fixture(scope="session", autouse=True)
def migrated() -> None:
    if not _db_available():
        return
    subprocess.run([sys.executable, "-m", "alembic", "downgrade", "base"], cwd=ROOT, check=True, capture_output=True)
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, check=True, capture_output=True)


@pytest_asyncio.fixture
async def db():
    if not _db_available():
        pytest.skip("postgres not available")
    from app.core.redis import close_redis, get_redis
    from app.db.session import dispose_engine, session_scope

    async with session_scope() as s:
        await s.execute(
            text(
                "TRUNCATE users, subscriptions, payment_intents, payments, search_sessions, search_results, products, "
                "product_embeddings, price_history, favorites, referrals, referral_rewards, admin_logs, marketplace_status "
                "RESTART IDENTITY CASCADE"
            )
        )
    await get_redis().flushdb()
    yield
    await dispose_engine()
    await close_redis()
