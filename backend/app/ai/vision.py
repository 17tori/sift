from __future__ import annotations

import base64
import logging

import anthropic
import httpx
import orjson

from app.ai import gemini
from app.ai.base import AIUnavailable, ImageAnalysis
from app.ai.prompts import VISION_DEEP_SUFFIX, VISION_SYSTEM
from app.core.config import get_settings

log = logging.getLogger(__name__)


def _strict_schema() -> dict:
    """Pydantic JSON schema tightened for structured outputs (all fields required, no extras)."""
    schema = ImageAnalysis.model_json_schema()

    def tighten(node: object) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"].keys())
            node.pop("default", None)
            node.pop("title", None)
            for v in node.values():
                tighten(v)
        elif isinstance(node, list):
            for v in node:
                tighten(v)

    tighten(schema)
    return schema


ANALYSIS_SCHEMA = _strict_schema()


class AnthropicVision:
    def __init__(self, api_key: str, model: str, effort: str, fallbacks: bool, timeout: float) -> None:
        self.model_id = f"anthropic:{model}"
        self._model = model
        self._effort = effort
        self._fallbacks = fallbacks
        self._client = anthropic.AsyncAnthropic(api_key=api_key or None, timeout=timeout, max_retries=2) if api_key else None

    async def analyze(self, image_jpeg: bytes, *, deep: bool) -> ImageAnalysis:
        if self._client is None:
            raise AIUnavailable("ANTHROPIC_API_KEY is not set")
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.standard_b64encode(image_jpeg).decode()}},
            {"type": "text", "text": "Analyse the main item in this photo."},
        ]
        kwargs: dict = dict(
            model=self._model,
            max_tokens=4000,
            system=VISION_SYSTEM + (VISION_DEEP_SUFFIX if deep else ""),
            messages=[{"role": "user", "content": content}],
            output_config={"effort": "medium" if deep else self._effort, "format": {"type": "json_schema", "schema": ANALYSIS_SCHEMA}},
        )
        try:
            if self._fallbacks:
                resp = await self._client.beta.messages.create(**kwargs, betas=["server-side-fallback-2026-07-01"], fallbacks="default")
            else:
                resp = await self._client.messages.create(**kwargs)
        except anthropic.RateLimitError as e:
            raise AIUnavailable("anthropic rate limited") from e
        except anthropic.APIStatusError as e:
            raise AIUnavailable(f"anthropic HTTP {e.status_code}") from e
        except anthropic.APIConnectionError as e:
            raise AIUnavailable("anthropic connection error") from e
        if resp.stop_reason == "refusal":
            raise AIUnavailable("vision model declined the image")
        if resp.stop_reason == "max_tokens":
            raise AIUnavailable("vision output truncated")
        text = next((b.text for b in resp.content if b.type == "text"), None)
        if not text:
            raise AIUnavailable("empty vision response")
        return ImageAnalysis.model_validate_json(text)


class OpenAICompatibleVision:
    """Any OpenAI-compatible /chat/completions endpoint with JSON-schema output (self-hosted VLMs etc.)."""

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float) -> None:
        self.model_id = f"openai_compat:{model}"
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._key = api_key
        self._model = model
        self._timeout = timeout

    async def analyze(self, image_jpeg: bytes, *, deep: bool) -> ImageAnalysis:
        if not self._model or not self._url.startswith("http"):
            raise AIUnavailable("OPENAI_COMPAT_* not configured")
        body = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": VISION_SYSTEM + (VISION_DEEP_SUFFIX if deep else "")},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(image_jpeg).decode()}},
                        {"type": "text", "text": "Analyse the main item in this photo."},
                    ],
                },
            ],
            "response_format": {"type": "json_schema", "json_schema": {"name": "analysis", "strict": True, "schema": ANALYSIS_SCHEMA}},
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as c:
                r = await c.post(self._url, json=body, headers={"Authorization": f"Bearer {self._key}"})
        except httpx.HTTPError as e:
            raise AIUnavailable(f"vision network error: {e}") from e
        if r.status_code >= 400:
            raise AIUnavailable(f"vision HTTP {r.status_code}")
        try:
            return ImageAnalysis.model_validate(orjson.loads(r.json()["choices"][0]["message"]["content"]))
        except (KeyError, IndexError, orjson.JSONDecodeError, ValueError) as e:
            raise AIUnavailable("invalid vision response") from e


class GeminiVision:
    """Google Gemini API (generateContent) with JSON-schema output. Key: aistudio.google.com/apikey."""

    def __init__(self, model: str, timeout: float) -> None:
        self.model_id = f"gemini:{model}"
        self._timeout = timeout

    def _body(self, image_jpeg: bytes, deep: bool, with_schema: bool) -> dict:
        system = VISION_SYSTEM + (VISION_DEEP_SUFFIX if deep else "")
        if not with_schema:
            system += "\n\nReturn only JSON matching this JSON Schema:\n" + orjson.dumps(ANALYSIS_SCHEMA).decode()
        cfg: dict = {"responseMimeType": "application/json", "temperature": 0.2}
        if with_schema:
            cfg["responseJsonSchema"] = ANALYSIS_SCHEMA
        return {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"inline_data": {"mime_type": "image/jpeg", "data": base64.standard_b64encode(image_jpeg).decode()}},
                        {"text": "Analyse the main item in this photo."},
                    ],
                }
            ],
            "generationConfig": cfg,
        }

    async def analyze(self, image_jpeg: bytes, *, deep: bool) -> ImageAnalysis:
        data = await gemini.generate(lambda with_schema: self._body(image_jpeg, deep, with_schema), http_timeout=self._timeout)
        return parse_gemini(data)


def parse_gemini(data: dict) -> ImageAnalysis:
    if (data.get("promptFeedback") or {}).get("blockReason"):
        raise AIUnavailable(f"gemini blocked the image: {data['promptFeedback']['blockReason']}")
    cands = data.get("candidates") or []
    if not cands:
        raise AIUnavailable("empty gemini response")
    c = cands[0]
    if c.get("finishReason") not in (None, "STOP"):
        raise AIUnavailable(f"gemini finished with {c.get('finishReason')}")
    text = "".join(p.get("text", "") for p in (c.get("content") or {}).get("parts") or [] if not p.get("thought"))
    text = text.strip().removeprefix("```json").removesuffix("```").strip()
    try:
        return ImageAnalysis.model_validate(orjson.loads(text))
    except (orjson.JSONDecodeError, ValueError) as e:
        raise AIUnavailable("invalid gemini response") from e


class DisabledVision:
    model_id = "none"

    async def analyze(self, image_jpeg: bytes, *, deep: bool) -> ImageAnalysis:
        raise AIUnavailable("vision provider disabled")


def build_vision_analyzer():  # type: ignore[no-untyped-def]
    s = get_settings()
    if s.vision_provider == "gemini":
        return GeminiVision(s.gemini_model, s.vision_timeout_seconds)
    if s.vision_provider == "anthropic":
        return AnthropicVision(
            s.anthropic_api_key.get_secret_value(), s.anthropic_model, s.anthropic_effort, s.anthropic_server_fallbacks, s.vision_timeout_seconds
        )
    if s.vision_provider == "openai_compatible":
        return OpenAICompatibleVision(
            s.openai_compat_base_url, s.openai_compat_api_key.get_secret_value(), s.openai_compat_model, s.vision_timeout_seconds
        )
    return DisabledVision()
