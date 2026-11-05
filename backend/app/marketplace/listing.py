"""Which URLs are product listings of which marketplace.

Shared by the web-backed sources (Google Vision web detection, Claude web search). A URL is
accepted only if its host belongs to a known marketplace and its path looks like a single listing,
so category, search and profile pages never reach the results.
"""

from __future__ import annotations

import hashlib
import html
import re
from urllib.parse import urlsplit, urlunsplit

DOMAINS: dict[str, tuple[str, ...]] = {
    "avito": ("avito.ru",),
    "wildberries": ("wildberries.ru", "wildberries.by", "wildberries.kz"),
    "vinted": (
        "vinted.com", "vinted.fr", "vinted.de", "vinted.co.uk", "vinted.pl", "vinted.it",
        "vinted.es", "vinted.nl", "vinted.be", "vinted.lt", "vinted.cz", "vinted.at",
    ),
    "grailed": ("grailed.com",),
    "ebay": ("ebay.com", "ebay.co.uk", "ebay.de", "ebay.fr", "ebay.it", "ebay.es", "ebay.com.au", "ebay.ca"),
    "aliexpress": ("aliexpress.com", "aliexpress.ru", "aliexpress.us"),
    "taobao": ("taobao.com", "tmall.com"),
    "goofish": ("goofish.com",),
}  # fmt: skip

# group(1) is the marketplace's own listing id
LISTING_ID: dict[str, re.Pattern[str]] = {
    "avito": re.compile(r"^[^?]*_(\d{6,})/?(?:\?|$)"),
    "wildberries": re.compile(r"/catalog/(\d+)/detail\.aspx"),
    "vinted": re.compile(r"/items/(\d+)"),
    "grailed": re.compile(r"/listings/(\d+)"),
    "ebay": re.compile(r"/itm/(?:[^/]+/)?(\d{9,})"),
    "aliexpress": re.compile(r"/item/(\d+)\.html"),
    "taobao": re.compile(r"item\.htm\?(?:.*&)?id=(\d+)"),
    "goofish": re.compile(r"item\?(?:.*&)?id=(\d+)"),
}

_TAGS = re.compile(r"<[^>]+>")


def canonical(url: str) -> str:
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    return urlunsplit(("https", host, parts.path.rstrip("/"), parts.query, ""))


def listing_key(code: str, url: str) -> str:
    """Identity of a listing regardless of tracking parameters, locale paths or mirror domains."""
    lid = listing_id(code, url)
    return f"{code}:{lid}" if lid else canonical(url)


def source_for(url: str, codes: list[str] | tuple[str, ...]) -> str | None:
    host = (urlsplit(url).hostname or "").lower()
    for code in codes:
        if any(host == d or host.endswith("." + d) for d in DOMAINS.get(code, ())):
            return code
    return None


def listing_id(code: str, url: str) -> str | None:
    """The listing id when `url` is a single-item page of `code`, else None."""
    parts = urlsplit(url)
    target = parts.path + (f"?{parts.query}" if parts.query else "")
    m = LISTING_ID[code].search(target) if code in LISTING_ID else None
    return m.group(1) if m else None


def external_id(code: str, url: str) -> str:
    return f"web:{listing_id(code, url) or hashlib.sha1(canonical(url).encode()).hexdigest()[:24]}"


def clean_title(t: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAGS.sub("", t or ""))).strip()[:300]
