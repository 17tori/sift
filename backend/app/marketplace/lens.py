"""Search by photo: Google Lens via serper.dev (default) or Google Cloud Vision Web Detection.

The photo is sent to `images:annotate` with the WEB_DETECTION feature. Google answers with pages that
contain the same or a visually similar image. SIFT keeps only pages that are single listings on a known
marketplace and uses the matched image as the product photo, so the similarity % is computed by our
own embedding model like for any other source.

Docs: https://serper.dev , https://cloud.google.com/vision/docs/detecting-web
"""

from __future__ import annotations

import base64
import logging
import re
from decimal import Decimal
from typing import Any

import httpx

from app.core.config import get_settings
from app.marketplace.base import NormalizedProduct, ProviderError, SearchQuery, to_decimal
from app.marketplace.listing import canonical, clean_title, external_id, listing_id, source_for

log = logging.getLogger(__name__)
ENDPOINT = "https://vision.googleapis.com/v1/images:annotate"


SERPER_BASE = "https://google.serper.dev"
CURRENCY_SYMBOLS = {
    "$": "USD", "US$": "USD", "USD": "USD", "€": "EUR", "EUR": "EUR", "£": "GBP", "GBP": "GBP",
    "₽": "RUB", "руб": "RUB", "руб.": "RUB", "RUB": "RUB", "₸": "KZT", "KZT": "KZT", "zł": "PLN", "PLN": "PLN",
    "¥": "CNY", "CNY": "CNY", "Br": "BYN", "BYN": "BYN",
}  # fmt: skip
_PRICE = re.compile(r"(\d[\d\s\u00a0.,]*)")


def parse_price(value: Any, currency: Any = None) -> tuple[Decimal | None, str | None]:
    """Price from a number or a display string such as "$25.99", "2 500 ₽", "€25,00". Unknown currency -> no price."""
    if value is None or value == "":
        return None, None
    if isinstance(value, dict):
        return parse_price(value.get("extracted_value") or value.get("value"), value.get("currency") or currency)
    text = str(value)
    cur = CURRENCY_SYMBOLS.get(str(currency or "").strip())
    if cur is None:
        cur = next((code for sym, code in sorted(CURRENCY_SYMBOLS.items(), key=lambda kv: -len(kv[0])) if sym in text), None)
    if cur is None:
        return None, None
    if isinstance(value, int | float):
        return to_decimal(value), cur
    m = _PRICE.search(text)
    if not m:
        return None, None
    num = m.group(1).replace("\u00a0", "").replace(" ", "").rstrip(".,")
    if "," in num and "." in num:
        num = num.replace(",", "") if num.rfind(".") > num.rfind(",") else num.replace(".", "").replace(",", ".")
    elif "," in num:
        head, _, tail = num.rpartition(",")
        num = f"{head.replace(',', '')}.{tail}" if len(tail) == 2 else num.replace(",", "")
    elif num.count(".") > 1 or (num.count(".") == 1 and len(num.rpartition(".")[2]) == 3):
        num = num.replace(".", "")
    d = to_decimal(num)
    return (d, cur) if d is not None and d > 0 else (None, None)


def lens_ready() -> bool:
    s = get_settings()
    if s.lens_provider == "google_vision":
        return bool(s.google_vision_api_key.get_secret_value())
    if s.lens_provider == "serper":
        return bool(s.serper_api_key.get_secret_value())
    return False


def parse_web_detection(data: dict[str, Any], codes: list[str], per_source: int) -> tuple[dict[str, list[NormalizedProduct]], list[str]]:
    """Returns products per marketplace and Google's best-guess labels (useful as text queries)."""
    resp = (data.get("responses") or [{}])[0]
    if "error" in resp:
        raise ProviderError(f"vision: {resp['error'].get('message', 'error')}")
    web = resp.get("webDetection") or {}
    labels = [lab["label"] for lab in web.get("bestGuessLabels") or [] if lab.get("label")]
    out: dict[str, list[NormalizedProduct]] = {c: [] for c in codes}
    seen: set[str] = set()
    # full matches first: the same photo is the strongest signal
    pages = sorted(web.get("pagesWithMatchingImages") or [], key=lambda p: 0 if p.get("fullMatchingImages") else 1)
    for page in pages:
        url = page.get("url") or ""
        code = source_for(url, codes)
        if code is None or listing_id(code, url) is None or len(out[code]) >= per_source:
            continue
        key = canonical(url)
        if key in seen:
            continue
        seen.add(key)
        imgs = (page.get("fullMatchingImages") or []) + (page.get("partialMatchingImages") or [])
        image = next((i["url"] for i in imgs if str(i.get("url", "")).startswith("https://")), None)
        out[code].append(
            NormalizedProduct(
                source=code,
                external_id=external_id(code, url),
                title=clean_title(page.get("pageTitle")) or (labels[0] if labels else code),
                url=url,
                image_url=image,
                price=None,
                currency=None,
                raw={"via": "google_lens", "match": "full" if page.get("fullMatchingImages") else "partial"},
            )
        )
    return out, labels


def image_pair(m: dict[str, Any]) -> tuple[str | None, str | None]:
    """(full image, Google thumbnail). Only https URLs; the thumbnail is the fallback when the
    marketplace CDN refuses our fetch."""
    full = next((u for u in (m.get("imageUrl"), m.get("image")) if str(u or "").startswith("https://")), None)
    thumb = m.get("thumbnailUrl") or m.get("thumbnail")
    thumb = thumb if str(thumb or "").startswith("https://") else None
    return (full or thumb), (thumb if full and thumb != full else None)


def parse_serper_lens(data: dict[str, Any], codes: list[str], per_source: int) -> tuple[dict[str, list[NormalizedProduct]], list[str]]:
    if data.get("message") and not data.get("organic"):
        raise ProviderError(f"serper: {str(data['message'])[:200]}")
    out: dict[str, list[NormalizedProduct]] = {c: [] for c in codes}
    seen: set[str] = set()
    for m in (data.get("organic") or []) + (data.get("visualMatches") or []) + (data.get("products") or []):
        url = m.get("link") or m.get("url") or ""
        code = source_for(url, codes)
        if code is None or listing_id(code, url) is None or len(out[code]) >= per_source:
            continue
        key = canonical(url)
        if key in seen:
            continue
        seen.add(key)
        price, currency = parse_price(m.get("price"), m.get("currency"))
        image, alt = image_pair(m)
        out[code].append(
            NormalizedProduct(
                source=code,
                external_id=external_id(code, url),
                title=clean_title(m.get("title")) or code,
                url=url,
                image_url=image,
                price=price,
                currency=currency,
                available=False if m.get("inStock") is False or m.get("in_stock") is False else None,
                raw={"via": "google_lens", "lens": "serper", **({"image_alt": alt} if alt else {})},
            )
        )
    return out, []


async def serper_post(path: str, body: dict[str, Any], http_timeout: float) -> dict[str, Any]:
    s = get_settings()
    try:
        async with httpx.AsyncClient(timeout=http_timeout) as c:
            r = await c.post(f"{SERPER_BASE}/{path}", json=body, headers={"X-API-KEY": s.serper_api_key.get_secret_value()})
    except httpx.HTTPError as e:
        raise ProviderError(f"serper network error: {e.__class__.__name__}") from e
    if r.status_code != 200:
        raise ProviderError(f"serper HTTP {r.status_code}: {r.text[:200]}")
    return r.json()


async def _serper_lens(q: SearchQuery, codes: list[str], per_source: int) -> tuple[dict[str, list[NormalizedProduct]], list[str]]:
    s = get_settings()
    if not q.image_public_url:
        raise ProviderError("serper lens needs a public photo URL (PUBLIC_BASE_URL)")
    data = await serper_post("lens", {"url": q.image_public_url, "gl": s.serper_country, "hl": s.serper_language}, s.web_search_timeout_seconds)
    return parse_serper_lens(data, codes, per_source)


async def search_by_photo(q: SearchQuery, codes: list[str], per_source: int) -> tuple[dict[str, list[NormalizedProduct]], list[str]]:
    s = get_settings()
    if s.lens_provider == "serper":
        found, labels = await _serper_lens(q, codes, per_source)
        log.info("lens(serper): %s", {c: len(v) for c, v in found.items() if v})
        return found, labels
    if not q.image_jpeg:
        return {c: [] for c in codes}, []
    image_jpeg = q.image_jpeg
    body = {
        "requests": [
            {
                "image": {"content": base64.standard_b64encode(image_jpeg).decode()},
                "features": [{"type": "WEB_DETECTION", "maxResults": 100}],
                "imageContext": {"webDetectionParams": {"includeGeoResults": True}},
            }
        ]
    }
    try:
        async with httpx.AsyncClient(timeout=s.provider_timeout_seconds) as c:
            r = await c.post(ENDPOINT, params={"key": s.google_vision_api_key.get_secret_value()}, json=body)
    except httpx.HTTPError as e:
        raise ProviderError(f"vision network error: {e.__class__.__name__}") from e
    if r.status_code != 200:
        raise ProviderError(f"vision HTTP {r.status_code}: {r.text[:200]}")
    found, labels = parse_web_detection(r.json(), codes, per_source)
    log.info("lens: %s labels=%s", {c: len(v) for c, v in found.items() if v}, labels[:3])
    return found, labels
