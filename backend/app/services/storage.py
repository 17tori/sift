"""Blob storage abstraction. Local volume today; an S3 backend can implement the same protocol."""

from __future__ import annotations

import asyncio
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings


class Storage(Protocol):
    async def put(self, data: bytes, ext: str, prefix: str) -> str: ...
    async def get(self, key: str) -> bytes: ...
    async def delete(self, key: str) -> None: ...
    def path(self, key: str) -> Path: ...


class LocalStorage:
    def __init__(self, root: str) -> None:
        self.root = Path(root)

    def path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root.resolve() not in p.parents:
            raise ValueError("invalid key")
        return p

    async def put(self, data: bytes, ext: str, prefix: str) -> str:
        day = datetime.now(UTC).strftime("%Y/%m/%d")
        key = f"{prefix}/{day}/{secrets.token_hex(16)}.{ext}"
        p = self.path(key)

        def _write() -> None:
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".tmp")
            tmp.write_bytes(data)
            os.replace(tmp, p)

        await asyncio.to_thread(_write)
        return key

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self.path(key).read_bytes)

    async def delete(self, key: str) -> None:
        p = self.path(key)
        await asyncio.to_thread(lambda: p.unlink(missing_ok=True))


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        _storage = LocalStorage(get_settings().storage_path)
    return _storage
