"""Search by description through Google (serper.dev), restricted to marketplace domains.

The query comes from the photo analysis (Gemini/Claude) and Google Lens' best-guess label. Two Google
queries per search at most: Russian-language marketplaces with a Russian query, international ones with
an English query. Only single-listing URLs on known marketplaces are kept.

Docs: https://serper.dev
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, NamedTuple

from app.core.config import get_settings
from app.marketplace.base import NormalizedProduct, ProviderError, SearchQuery
from app.marketplace.lens import image_pair, parse_price, serper_post
from app.marketplace.listing import canonical, clean_title, external_id, listing_id, listing_key, source_for

log = logging.getLogger(__name__)

RU_SOURCES = ("avito", "wildberries")
# Domains named in the site: filter (Google caps query length, so only the main ones).
SITE_FILTER: dict[str, tuple[str, ...]] = {
    "avito": ("avito.ru",),
    "wildberries": ("wildberries.ru",),
    "vinted": ("vinted.fr", "vinted.de", "vinted.co.uk"),
    "grailed": ("grailed.com",),
    "ebay": ("ebay.com",),
    "aliexpress": ("aliexpress.com", "aliexpress.ru"),
    "taobao": ("item.taobao.com",),
}


def serp_text_ready() -> bool:
    s = get_settings()
    return s.text_search_provider == "serper" and bool(s.serper_api_key.get_secret_value())


def _query(phrase: str, codes: list[str]) -> str:
    sites = " OR ".join(f"site:{d}" for c in codes for d in SITE_FILTER.get(c, ()))
    return f"{phrase} ({sites})"


def parse_organic(data: dict[str, Any], codes: list[str], per_source: int) -> dict[str, list[NormalizedProduct]]:
    if data.get("message") and "organic" not in data:
        raise ProviderError(f"serper: {str(data['message'])[:200]}")
    out: dict[str, list[NormalizedProduct]] = {c: [] for c in codes}
    seen: set[str] = set()
    for r in data.get("organic") or []:
        url = r.get("link") or ""
        code = source_for(url, codes)
        if code is None or listing_id(code, url) is None or len(out[code]) >= per_source:
            continue
        key = canonical(url)
        if key in seen:
            continue
        seen.add(key)
        attrs = r.get("attributes") or {}
        raw_price = r.get("price") or attrs.get("Price") or attrs.get("Цена")
        price, currency = parse_price(raw_price, r.get("currency"))
        image, alt = image_pair(r)
        out[code].append(
            NormalizedProduct(
                source=code,
                external_id=external_id(code, url),
                title=clean_title(r.get("title")) or code,
                url=url,
                image_url=image,
                price=price,
                currency=currency,
                raw={"via": "web_search", "engine": "google", **({"image_alt": alt} if alt else {})},
            )
        )
    return out


class ImageHit(NamedTuple):
    code: str
    url: str
    image: str
    alt: str | None
    title: str


def parse_images(data: dict[str, Any], codes: list[str]) -> dict[str, ImageHit]:
    """Google Images results -> {listing key: hit}, listing pages on known marketplaces only."""
    out: dict[str, ImageHit] = {}
    for r in data.get("images") or []:
        url = r.get("link") or ""
        code = source_for(url, codes)
        if code is None or listing_id(code, url) is None:
            continue
        image, alt = image_pair(r)
        if image is None:
            continue
        out.setdefault(listing_key(code, url), ImageHit(code, url, image, alt, clean_title(r.get("title")) or code))
    return out


def attach_images(found: dict[str, list[NormalizedProduct]], images: dict[str, ImageHit], per_source: int) -> None:
    """Gives web results without a picture the photo Google Images shows for the same listing, and adds
    image-only listings Google Images found for the same query."""
    have: set[str] = set()
    for items in found.values():
        for p in items:
            key = listing_key(p.source, p.url)
            have.add(key)
            hit = images.get(key)
            if hit and p.image_url is None:
                p.image_url = hit.image
                if hit.alt:
                    p.raw["image_alt"] = hit.alt
    for key, h in images.items():
        if key in have or h.code not in found or len(found[h.code]) >= per_source:
            continue
        found[h.code].append(
            NormalizedProduct(
                source=h.code,
                external_id=external_id(h.code, h.url),
                title=h.title,
                url=h.url,
                image_url=h.image,
                price=None,
                currency=None,
                raw={"via": "web_search", "engine": "google_images", **({"image_alt": h.alt} if h.alt else {})},
            )
        )


async def _google(q: str, lang: str) -> dict[str, Any]:
    s = get_settings()
    return await serper_post("search", {"q": q, "gl": s.serper_country, "hl": lang, "num": 20}, s.provider_timeout_seconds)


async def _images(q: str, lang: str) -> dict[str, Any]:
    s = get_settings()
    if not s.serper_images:
        return {}
    try:
        return await serper_post("images", {"q": q, "gl": s.serper_country, "hl": lang, "num": 20}, s.provider_timeout_seconds)
    except ProviderError as e:  # pictures are a bonus: never fail the text channel over them
        log.warning("serper images failed: %s", e)
        return {}


async def search_text(q: SearchQuery, codes: list[str], hints: list[str]) -> dict[str, list[NormalizedProduct]]:
    ru_codes = [c for c in codes if c in RU_SOURCES]
    intl_codes = [c for c in codes if c not in RU_SOURCES and c in SITE_FILTER]
    ru_phrase = (q.texts.get("ru") or [None])[0]
    en_phrase = (q.texts.get("en") or hints or [None])[0]
    jobs: list[tuple[str, str, list[str]]] = []
    if ru_codes and (ru_phrase or en_phrase):
        jobs.append((_query(ru_phrase or en_phrase, ru_codes), "ru", ru_codes))  # type: ignore[arg-type]
    if intl_codes and en_phrase:
        jobs.append((_query(en_phrase, intl_codes), "en", intl_codes))
    out: dict[str, list[NormalizedProduct]] = {c: [] for c in codes}
    if not jobs:
        return out
    results, pics = await asyncio.gather(
        asyncio.gather(*(_google(query, lang) for query, lang, _ in jobs), return_exceptions=True),
        asyncio.gather(*(_images(query, lang) for query, lang, _ in jobs), return_exceptions=True),
    )
    errors = [r for r in results if isinstance(r, BaseException)]
    if len(errors) == len(results):
        raise ProviderError(str(errors[0]))
    for (_, _, job_codes), res, img in zip(jobs, results, pics, strict=True):
        if isinstance(res, BaseException):
            log.warning("serper google failed: %s", res)
            continue
        found = parse_organic(res, job_codes, q.limit)
        if isinstance(img, dict) and img:
            attach_images(found, parse_images(img, job_codes), q.limit)
        for c, items in found.items():
            out[c].extend(items)
    log.info("serp text: %s", {c: len(v) for c, v in out.items() if v})
    return out
