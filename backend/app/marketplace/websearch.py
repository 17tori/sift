"""Claude web search as a source for marketplaces that have no public search API.

Claude's server-side web search queries a public search-engine index, restricted with
`allowed_domains` to the marketplaces below. SIFT never requests the marketplace sites itself,
so nothing is scraped and no anti-bot measure is touched.

Integrity rules enforced here:
  * a listing is accepted only if its URL was returned by the search tool in this very response
    (the model cannot invent links), and its host belongs to the marketplace it is filed under;
  * prices are what the indexed page showed and are flagged as such (`raw.via = "web_search"`);
  * there is no image, so no similarity % is ever computed for these items.

One Claude call per search covers every web-backed source at once; providers of the same run share
it through `SearchQuery.shared`.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from decimal import Decimal
from typing import Any

import anthropic

from app.core.config import get_settings
from app.marketplace.base import NormalizedProduct, ProviderError, SearchQuery, to_decimal
from app.marketplace.listing import DOMAINS, canonical, clean_title, external_id, listing_id, source_for

log = logging.getLogger(__name__)

SYSTEM = """You find second-hand and retail listings of a fashion item on specific marketplaces using the web_search tool.

Rules:
- Use web_search. Search in the marketplace's language: Russian for avito.ru and wildberries.ru,
  English or the local language for Vinted and Grailed.
- Only individual listing pages count (one item for sale), never category, search, brand or profile pages.
- Only listings of the same item or a very close alternative (same type, colour family and key details).
- Copy each URL exactly as it appeared in the search results. Never construct or guess a URL.
- Price: only if it is visible in the search result; otherwise null. Never estimate.
- If nothing suitable is found, return an empty list. Returning nothing is better than a wrong match.

Finish with one fenced ```json block and nothing after it:
{"listings": [{"url": "...", "title": "...", "price": 1234 or null, "currency": "RUB" or null, "condition": "new" | "used" | null}]}"""


def _extract_json(text: str) -> list[dict[str, Any]]:
    blocks = re.findall(r"```json\s*(.*?)```", text, flags=re.S)
    for raw in reversed(blocks or [text]):
        try:
            data = json.loads(raw.strip())
        except json.JSONDecodeError:
            continue
        items = data.get("listings") if isinstance(data, dict) else data
        if isinstance(items, list):
            return [i for i in items if isinstance(i, dict)]
    return []


def _describe(q: SearchQuery) -> str:
    lines = []
    for lang in ("ru", "en"):
        if q.texts.get(lang):
            lines.append(f"Search phrases ({lang}): " + "; ".join(q.texts[lang][:4]))
    if q.category:
        lines.append(f"Category: {q.category}")
    if q.gender:
        lines.append(f"Gender: {q.gender}")
    if q.price_min is not None or q.price_max is not None:
        lines.append(f"Price range (RUB): {q.price_min or 0} - {q.price_max or 'any'}")
    if q.condition:
        lines.append(f"Condition: {q.condition}")
    return "\n".join(lines)


def build_products(response_content: list[Any], codes: list[str], per_source: int) -> dict[str, list[NormalizedProduct]]:
    """Turns a Messages API response into products, keeping only URLs the search tool really returned."""
    grounded: dict[str, dict[str, Any]] = {}
    text_parts: list[str] = []
    for block in response_content:
        btype = getattr(block, "type", None)
        if btype == "web_search_tool_result" and isinstance(block.content, list):
            for r in block.content:
                if getattr(r, "type", None) == "web_search_result":
                    grounded[canonical(r.url)] = {"url": r.url, "title": r.title, "page_age": r.page_age}
        elif btype == "text":
            text_parts.append(block.text)

    out: dict[str, list[NormalizedProduct]] = {c: [] for c in codes}
    seen: set[str] = set()
    for item in _extract_json("".join(text_parts)):
        url = str(item.get("url") or "")
        key = canonical(url)
        hit = grounded.get(key)
        if hit is None or key in seen:
            continue  # not returned by the search tool: never trust it
        code = source_for(hit["url"], codes)
        if code is None or listing_id(code, hit["url"]) is None or len(out[code]) >= per_source:
            continue
        seen.add(key)
        price = to_decimal(item.get("price"))
        currency = str(item.get("currency") or "").upper()[:3] or None
        cond = item.get("condition") if item.get("condition") in ("new", "used") else None
        title = clean_title(str(item.get("title") or "")) or clean_title(hit["title"])
        out[code].append(
            NormalizedProduct(
                source=code,
                external_id=external_id(code, hit["url"]),
                title=title,
                url=hit["url"],
                image_url=None,
                price=price if price and price > Decimal("0") and currency else None,
                currency=currency if price else None,
                condition=cond,
                raw={"via": "web_search", "page_age": hit["page_age"]},
            )
        )
    return out


def web_search_ready() -> bool:
    s = get_settings()
    return s.text_search_provider == "claude" and bool(s.anthropic_api_key.get_secret_value())


class WebSearchHub:
    def __init__(self) -> None:
        s = get_settings()
        self._client = anthropic.AsyncAnthropic(
            api_key=s.anthropic_api_key.get_secret_value() or None, timeout=s.web_search_timeout_seconds, max_retries=1
        )

    async def run(self, q: SearchQuery, codes: list[str], hints: list[str] | None = None) -> dict[str, list[NormalizedProduct]]:
        s = get_settings()
        domains = sorted({d for c in codes for d in DOMAINS.get(c, ())})
        content: list[dict[str, Any]] = []
        if q.image_jpeg:
            data = base64.standard_b64encode(q.image_jpeg).decode()
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}})
        hint = f"\nGoogle reverse-image guess: {'; '.join(hints[:3])}" if hints else ""
        ask = f"Find listings of the item in the photo on: {', '.join(domains)}.\n{_describe(q)}{hint}\nMax {q.limit} per marketplace."
        content.append({"type": "text", "text": ask})
        messages: list[dict[str, Any]] = [{"role": "user", "content": content}]
        tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": s.web_search_max_uses, "allowed_domains": domains}]
        collected: list[Any] = []
        try:
            for _ in range(3):  # pause_turn continuations
                resp = await self._client.messages.create(
                    model=s.web_search_model, max_tokens=4000, system=SYSTEM, messages=messages, tools=tools
                )
                collected.extend(resp.content)
                if resp.stop_reason != "pause_turn":
                    break
                messages = [messages[0], {"role": "assistant", "content": resp.content}]
        except anthropic.APIStatusError as e:
            raise ProviderError(f"web search HTTP {e.status_code}") from e
        except anthropic.APIConnectionError as e:
            raise ProviderError("web search connection error") from e
        if resp.stop_reason == "refusal":
            raise ProviderError("web search declined")
        found = build_products(collected, codes, q.limit)
        log.info("web search: %s", {c: len(v) for c, v in found.items()})
        return found


_hub: WebSearchHub | None = None


def hub() -> WebSearchHub:
    global _hub
    if _hub is None:
        _hub = WebSearchHub()
    return _hub
