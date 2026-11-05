"""Visual verification of found listings by Gemini.

Google Lens and text search return candidates; many are only loosely related. Gemini looks at the user's
photo next to each candidate's photo (our stored copy) and scores how likely it is the same item. The score
is what the card shows as the similarity %, because a model really computed it, and clearly different items
are hidden. Candidates without a photo stay unverified: no %, ranked below verified matches.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from dataclasses import dataclass
from typing import Literal

import orjson

from app.ai import gemini
from app.ai.base import AIUnavailable
from app.core.config import get_settings

log = logging.getLogger(__name__)

VERIFY_SYSTEM = """You verify product search results for a fashion visual search app.
Image 0 is the user's photo of an item. Every following image is a marketplace listing photo, labelled #1, #2, ...
For each listing decide how likely it shows THE SAME product as image 0 (same model/design), not just the same
category. Judge the main item only; ignore background, model, pose, lighting, crop, watermarks and collages.

Score 0-100:
- 90-100: same product (same design, colour, distinctive details: logo, print, hardware, stitching, shape)
- 70-89: very likely the same product or the same model in another photo/angle; minor doubts
- 45-69: similar item: same type and style, but some details differ (colour shade, pattern, cut, details)
- 20-44: same category only, clearly different design
- 0-19: different kind of item, or the photo does not show a product

verdict: "same" (score >= 70), "similar" (45-69), "different" (< 45). Be strict: generic similarity in category
or colour alone is "different". Return one entry for every listing number you were given."""

VERIFY_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "i": {"type": "integer"},
                    "score": {"type": "integer"},
                    "verdict": {"type": "string", "enum": ["same", "similar", "different"]},
                },
                "required": ["i", "score", "verdict"],
            },
        }
    },
    "required": ["items"],
}


@dataclass(slots=True, frozen=True)
class Verdict:
    score: int
    verdict: Literal["same", "similar", "different"]


def verify_ready() -> bool:
    s = get_settings()
    return s.verify_provider == "gemini" and bool(s.gemini_api_key.get_secret_value())


def _img(data: bytes) -> dict:
    return {"inline_data": {"mime_type": "image/jpeg", "data": base64.standard_b64encode(data).decode()}}


def build_body(query_jpeg: bytes, cands: list[bytes], hint: str | None, with_schema: bool = True) -> dict:
    parts: list[dict] = [{"text": "Image 0 (user's photo)" + (f" — {hint}" if hint else "") + ":"}, _img(query_jpeg)]
    for n, data in enumerate(cands, 1):
        parts += [{"text": f"#{n}:"}, _img(data)]
    parts.append({"text": f"Score listings #1..#{len(cands)}."})
    system = VERIFY_SYSTEM
    cfg: dict = {"responseMimeType": "application/json", "temperature": 0.0}
    if with_schema:
        cfg["responseJsonSchema"] = VERIFY_SCHEMA
    else:
        system += "\n\nReturn only JSON matching this JSON Schema:\n" + orjson.dumps(VERIFY_SCHEMA).decode()
    return {"systemInstruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": parts}], "generationConfig": cfg}


def parse_verdicts(data: dict, n: int) -> dict[int, Verdict]:
    """{listing index from 0: verdict}. Entries outside 1..n are ignored; scores are clamped to 0..100."""
    cands = data.get("candidates") or []
    if not cands:
        raise AIUnavailable("empty gemini response")
    c = cands[0]
    if c.get("finishReason") not in (None, "STOP"):
        raise AIUnavailable(f"gemini finished with {c.get('finishReason')}")
    text = "".join(p.get("text", "") for p in (c.get("content") or {}).get("parts") or [] if not p.get("thought"))
    text = text.strip().removeprefix("```json").removesuffix("```").strip()
    try:
        items = orjson.loads(text)["items"]
    except (orjson.JSONDecodeError, KeyError, TypeError) as e:
        raise AIUnavailable("invalid gemini verify response") from e
    out: dict[int, Verdict] = {}
    for it in items:
        try:
            i, score, verdict = int(it["i"]), max(0, min(100, int(it["score"]))), str(it["verdict"])
        except (KeyError, TypeError, ValueError):
            continue
        if 1 <= i <= n and verdict in ("same", "similar", "different"):
            out[i - 1] = Verdict(score, verdict)  # type: ignore[arg-type]
    return out


class GeminiVerifier:
    def __init__(self) -> None:
        s = get_settings()
        self._models = list(dict.fromkeys([s.verify_model, *gemini.models_chain()] if s.verify_model else gemini.models_chain()))
        self._timeout = s.verify_timeout_seconds
        self._batch = max(1, s.verify_batch_size)
        self.model_id = f"gemini:{self._models[0] if self._models else s.gemini_model}"

    async def _batch_verify(self, query: bytes, cands: list[bytes], hint: str | None) -> dict[int, Verdict]:
        data = await gemini.generate(
            lambda with_schema: build_body(query, cands, hint, with_schema), http_timeout=self._timeout, models=self._models
        )
        return parse_verdicts(data, len(cands))

    async def verify(self, query: bytes, cands: list[bytes], hint: str | None = None) -> dict[int, Verdict]:
        """Scores every candidate image against the query photo. Batches run concurrently; a failed batch
        leaves its candidates unscored (raises only when every batch failed)."""
        if not cands:
            return {}
        chunks = [list(range(i, min(i + self._batch, len(cands)))) for i in range(0, len(cands), self._batch)]
        results = await asyncio.gather(*(self._batch_verify(query, [cands[i] for i in ch], hint) for ch in chunks), return_exceptions=True)
        out: dict[int, Verdict] = {}
        errors: list[BaseException] = []
        for ch, res in zip(chunks, results, strict=True):
            if isinstance(res, BaseException):
                errors.append(res)
                log.warning("gemini verify batch failed: %s", res)
                continue
            out.update({ch[k]: v for k, v in res.items()})
        if errors and len(errors) == len(chunks):
            raise errors[0] if isinstance(errors[0], AIUnavailable) else AIUnavailable(str(errors[0]))
        return out
