"""One resilient call to the Gemini API (generateContent).

Popular Gemini models answer 503 "high demand" or 429 at peaks and sometimes stall. Each call:
- limits thinking (GEMINI_THINKING), so image tasks answer in seconds rather than minutes;
- retries 429/500/502/503/504 and timeouts with backoff;
- then moves to the next model of GEMINI_FALLBACK_MODELS.
A 400 that rejects the JSON schema or the thinking setting is retried once without it.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

import httpx

from app.ai.base import AIUnavailable
from app.core.config import get_settings

log = logging.getLogger(__name__)
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
RETRY_STATUS = {429, 500, 502, 503, 504}
BACKOFF = (1.5, 4.0)


def models_chain() -> list[str]:
    s = get_settings()
    chain = [s.gemini_model, *s.gemini_fallback_models]
    return list(dict.fromkeys(m for m in chain if m))


def _with_thinking(body: dict) -> dict:
    level = get_settings().gemini_thinking
    if level == "default":
        return body
    cfg = dict(body.get("generationConfig") or {})
    cfg["thinkingConfig"] = {"thinkingLevel": level}
    return {**body, "generationConfig": cfg}


async def generate(
    build: Callable[[bool], dict], *, http_timeout: float, models: list[str] | None = None, client: httpx.AsyncClient | None = None
) -> dict:
    """`build(with_schema)` returns the request body. Returns the parsed JSON response of the first model
    that answers; raises AIUnavailable with the last error otherwise."""
    s = get_settings()
    key = s.gemini_api_key.get_secret_value()
    if not key:
        raise AIUnavailable("GEMINI_API_KEY is not set")
    own = client is None
    c = client or httpx.AsyncClient(timeout=http_timeout)
    last = "no model configured"
    try:
        for model in models or models_chain():
            with_schema, thinking = True, True
            attempt = 0
            while True:
                body = build(with_schema)
                if thinking:
                    body = _with_thinking(body)
                try:
                    r = await c.post(URL.format(model=model), json=body, headers={"x-goog-api-key": key}, timeout=http_timeout)
                except httpx.HTTPError as e:
                    last = f"gemini {model} network error: {e.__class__.__name__}"
                    status = None
                else:
                    if r.status_code < 400:
                        return r.json()
                    status = r.status_code
                    last = f"gemini {model} HTTP {status}: {r.text[:200]}"
                    text = r.text.lower()
                    if status == 400 and thinking and "thinking" in text:
                        thinking = False  # this model does not accept the thinking setting
                        continue
                    if status == 400 and with_schema and "schema" in text:
                        with_schema = False  # older model versions reject some JSON-schema keywords
                        continue
                    if status not in RETRY_STATUS:
                        if status == 404:
                            break  # model retired: try the next one
                        raise AIUnavailable(last)
                if attempt < len(BACKOFF):
                    await asyncio.sleep(BACKOFF[attempt])
                    attempt += 1
                    continue
                break  # retries spent: next model
            log.warning("%s; trying next model", last)
    finally:
        if own:
            await c.aclose()
    raise AIUnavailable(last)
