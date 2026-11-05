"""Web-backed sources for marketplaces without a usable API (or before their keys arrive).

Two legal channels, run in parallel once per search and shared by every web-backed marketplace:
  1. Google Cloud Vision Web Detection: pages with the same / a similar photo (by image).
  2. Search by description: Google via serper.dev (default) or Claude web search, guided by the
     photo analysis and Lens' best-guess label.
Neither requests the marketplace sites. Results are deduplicated by URL; photo matches come first.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core.config import get_settings
from app.marketplace import lens, serptext, websearch
from app.marketplace.base import (
    IntegrationKind,
    MarketplaceProvider,
    NormalizedProduct,
    ProviderError,
    ProviderState,
    ProviderUnavailable,
    SearchQuery,
)
from app.marketplace.listing import DOMAINS, listing_key

log = logging.getLogger(__name__)

WEB_NOTE = (
    "Через Google Lens (поиск по фото) и поиск Google по описанию: сам сайт площадки "
    "не запрашивается. Цена — со страницы на момент индексации или на сайте площадки."
)


def text_ready() -> bool:
    return serptext.serp_text_ready() or websearch.web_search_ready()


def web_ready() -> bool:
    return lens.lens_ready() or text_ready()


def web_enabled_for(code: str) -> bool:
    return web_ready() and code in DOMAINS and code in get_settings().web_search_marketplaces


async def _run(q: SearchQuery, codes: list[str]) -> dict[str, list[NormalizedProduct]]:
    merged: dict[str, list[NormalizedProduct]] = {c: [] for c in codes}
    errors: list[str] = []
    hints: list[str] = []
    lens_task = asyncio.create_task(lens.search_by_photo(q, codes, q.limit)) if lens.lens_ready() else None

    if lens_task is not None:
        try:
            found, hints = await lens_task
            for c, items in found.items():
                merged[c].extend(items)
        except ProviderError as e:
            errors.append(str(e))
            log.warning("lens failed: %s", e)

    if text_ready():
        try:
            if serptext.serp_text_ready():
                found = await serptext.search_text(q, codes, hints)
            else:
                found = await websearch.hub().run(q, codes, hints)
            for c, items in found.items():
                have = {listing_key(c, p.url): p for p in merged[c]}
                for p in items:
                    prev = have.get(listing_key(c, p.url))
                    if prev is None:
                        merged[c].append(p)
                        continue
                    # Same listing from both channels: keep the Lens hit, fill what it lacks.
                    if prev.image_url is None and p.image_url:
                        prev.image_url = p.image_url
                        if p.raw.get("image_alt"):
                            prev.raw["image_alt"] = p.raw["image_alt"]
                    if prev.price is None and p.price is not None:
                        prev.price, prev.currency = p.price, p.currency
        except ProviderError as e:
            errors.append(str(e))
            log.warning("text web search failed: %s", e)

    if errors and not any(merged.values()) and len(errors) == sum([lens_task is not None, text_ready()]):
        raise ProviderError("; ".join(errors))
    return {c: v[: q.limit] for c, v in merged.items()}


async def search_for(code: str, q: SearchQuery) -> list[NormalizedProduct]:
    """All web-backed marketplaces of one search share a single run."""
    if not web_ready():
        raise ProviderUnavailable(ProviderState.NOT_CONFIGURED, "web sources are not configured")
    task: asyncio.Task[dict[str, list[NormalizedProduct]]] | None = q.shared.get("web_task")
    if task is None:
        codes = list(dict.fromkeys([*q.shared.get("web_codes", []), code]))
        task = asyncio.ensure_future(_run(q, codes))
        q.shared["web_task"] = task
    return list((await asyncio.shield(task)).get(code, []))


def web_timeout() -> float:
    return get_settings().web_search_timeout_seconds


class WebFallbackProvider(MarketplaceProvider):
    """Wraps a marketplace that has no legal API or no keys yet and serves it through the web sources."""

    kind = IntegrationKind.WEB_SEARCH

    def __init__(self, inner: MarketplaceProvider) -> None:
        super().__init__(inner.enabled)
        self.inner = inner
        self.code, self.name, self.url = inner.code, inner.name, inner.url
        self.regions, self.languages = inner.regions, inner.languages
        self.supports_image_search = lens.lens_ready()
        self.note = WEB_NOTE
        self.timeout_seconds = web_timeout()

    def configured(self) -> bool:
        return True

    async def search(self, query: SearchQuery) -> list[NormalizedProduct]:
        self.ensure_usable()
        return await search_for(self.code, query)

    async def get_product(self, external_id: str) -> NormalizedProduct | None:
        return None  # no live product endpoint; price alerts skip these items

    def normalize_product(self, raw: dict[str, Any]) -> NormalizedProduct | None:
        return None
