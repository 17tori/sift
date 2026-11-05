from __future__ import annotations

import base64
import logging
import math

import httpx

from app.ai.base import AIUnavailable
from app.core.config import get_settings

log = logging.getLogger(__name__)


def _l2(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


class JinaClipEmbeddings:
    """Jina CLIP v2 (https://api.jina.ai/v1/embeddings). Images and texts share one space."""

    url = "https://api.jina.ai/v1/embeddings"

    def __init__(self, api_key: str, model: str, dim: int, timeout: float, batch: int) -> None:
        self.api_key = api_key
        self.model_id = f"jina:{model}:{dim}"
        self._model = model
        self.dim = dim
        self._timeout = timeout
        self._batch = batch

    async def _call(self, inputs: list[dict[str, str]]) -> list[list[float]]:
        if not self.api_key:
            raise AIUnavailable("JINA_API_KEY is not set")
        out: list[list[float]] = []
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for i in range(0, len(inputs), self._batch):
                chunk = inputs[i : i + self._batch]
                body = {"model": self._model, "dimensions": self.dim, "normalized": True, "embedding_type": "float", "input": chunk}
                try:
                    r = await client.post(self.url, json=body, headers={"Authorization": f"Bearer {self.api_key}"})
                except httpx.HTTPError as e:
                    raise AIUnavailable(f"jina network error: {e}") from e
                if r.status_code >= 400:
                    raise AIUnavailable(f"jina HTTP {r.status_code}: {r.text[:300]}")
                data = sorted(r.json()["data"], key=lambda d: d["index"])
                out.extend(_l2(d["embedding"]) for d in data)
        return out

    async def embed_images(self, images: list[bytes]) -> list[list[float]]:
        return await self._call([{"image": base64.b64encode(b).decode()} for b in images])

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return await self._call([{"text": t} for t in texts])


class VoyageMultimodalEmbeddings:
    """Voyage multimodal-3 (https://api.voyageai.com/v1/multimodalembeddings), 1024 dims."""

    url = "https://api.voyageai.com/v1/multimodalembeddings"

    def __init__(self, api_key: str, model: str, timeout: float, batch: int) -> None:
        self.api_key = api_key
        self.model_id = f"voyage:{model}"
        self._model = model
        self.dim = 1024
        self._timeout = timeout
        self._batch = batch

    async def _call(self, inputs: list[dict]) -> list[list[float]]:
        if not self.api_key:
            raise AIUnavailable("VOYAGE_API_KEY is not set")
        out: list[list[float]] = []
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for i in range(0, len(inputs), self._batch):
                body = {"model": self._model, "inputs": inputs[i : i + self._batch]}
                try:
                    r = await client.post(self.url, json=body, headers={"Authorization": f"Bearer {self.api_key}"})
                except httpx.HTTPError as e:
                    raise AIUnavailable(f"voyage network error: {e}") from e
                if r.status_code >= 400:
                    raise AIUnavailable(f"voyage HTTP {r.status_code}: {r.text[:300]}")
                out.extend(_l2(d["embedding"]) for d in r.json()["data"])
        return out

    async def embed_images(self, images: list[bytes]) -> list[list[float]]:
        return await self._call(
            [{"content": [{"type": "image_base64", "image_base64": "data:image/jpeg;base64," + base64.b64encode(b).decode()}]} for b in images]
        )

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return await self._call([{"content": [{"type": "text", "text": t}]} for t in texts])


class DisabledEmbeddings:
    model_id = "none"
    dim = 0

    async def embed_images(self, images: list[bytes]) -> list[list[float]]:
        raise AIUnavailable("embedding provider disabled")

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise AIUnavailable("embedding provider disabled")


def build_embedding_provider():  # type: ignore[no-untyped-def]
    s = get_settings()
    if s.embedding_provider == "jina":
        return JinaClipEmbeddings(
            s.jina_api_key.get_secret_value(), s.jina_model, s.embedding_dim, s.embedding_timeout_seconds, s.embedding_batch_size
        )
    if s.embedding_provider == "voyage":
        if s.embedding_dim != 1024:
            raise RuntimeError("voyage-multimodal-3 produces 1024-dim vectors; set EMBEDDING_DIM=1024")
        return VoyageMultimodalEmbeddings(
            s.voyage_api_key.get_secret_value(), s.voyage_model, s.embedding_timeout_seconds, s.embedding_batch_size
        )
    return DisabledEmbeddings()
