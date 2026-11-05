"""eBay Browse API (official). Text search + search_by_image.

Docs: https://developer.ebay.com/api-docs/buy/browse/overview.html
Auth: OAuth client-credentials, scope https://api.ebay.com/oauth/api_scope.
Production access to the Buy APIs requires an approved eBay developer keyset; the
search_by_image method is marked experimental by eBay and may be limited per keyset.
"""

from __future__ import annotations

import base64
import logging
import time
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.redis import get_redis
from app.marketplace import http
from app.marketplace.base import (
    IntegrationKind,
    MarketplaceProvider,
    NormalizedProduct,
    ProviderError,
    SearchQuery,
    to_decimal,
)

log = logging.getLogger(__name__)
TOKEN_KEY = "ebay:app_token"
_COND_NEW = {"1000", "1500", "1750"}
_COND_REFURB = {"2000", "2010", "2020", "2030", "2500"}


class EbayProvider(MarketplaceProvider):
    code = "ebay"
    name = "eBay"
    url = "https://www.ebay.com"
    kind = IntegrationKind.OFFICIAL_API
    regions = ["US", "EU", "UK", "AU"]
    languages = ("en",)
    supports_image_search = True
    note = "Официальный eBay Browse API: текстовый поиск и поиск по изображению."

    def configured(self) -> bool:
        s = get_settings()
        return bool(s.ebay_client_id and s.ebay_client_secret.get_secret_value())

    async def _token(self, client: httpx.AsyncClient) -> str:
        r = get_redis()
        cached = await r.get(TOKEN_KEY)
        if cached:
            return cached
        s = get_settings()
        basic = base64.b64encode(f"{s.ebay_client_id}:{s.ebay_client_secret.get_secret_value()}".encode()).decode()
        resp = await client.post(
            f"{s.ebay_api_base}/identity/v1/oauth2/token",
            headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"},
        )
        if resp.status_code != 200:
            raise ProviderError(f"ebay oauth HTTP {resp.status_code}: {resp.text[:200]}")
        body = resp.json()
        token = body["access_token"]
        await r.set(TOKEN_KEY, token, ex=max(int(body.get("expires_in", 7200)) - 120, 60))
        return token

    def _headers(self, token: str) -> dict[str, str]:
        s = get_settings()
        h = {"Authorization": f"Bearer {token}", "X-EBAY-C-MARKETPLACE-ID": s.ebay_marketplace_id}
        if s.ebay_affiliate_campaign_id:
            h["X-EBAY-C-ENDUSERCTX"] = f"affiliateCampaignId={s.ebay_affiliate_campaign_id}"
        return h

    def _filter(self, q: SearchQuery) -> str | None:
        parts = []
        if q.price_min is not None or q.price_max is not None:
            lo = "" if q.price_min is None else str(q.price_min)
            hi = "" if q.price_max is None else str(q.price_max)
            parts.append(f"price:[{lo}..{hi}]")
            parts.append("priceCurrency:USD")
        if q.condition == "new":
            parts.append("conditionIds:{1000}")
        elif q.condition == "used":
            parts.append("conditionIds:{3000}")
        return ",".join(parts) or None

    async def search(self, query: SearchQuery) -> list[NormalizedProduct]:
        self.ensure_usable()
        s = get_settings()
        params: dict[str, Any] = {"limit": min(query.limit, 50)}
        if s.ebay_category_ids:
            params["category_ids"] = s.ebay_category_ids
        flt = self._filter(query)
        if flt:
            params["filter"] = flt
        items: list[dict[str, Any]] = []
        async with http.client() as c:
            token = await self._token(c)
            headers = self._headers(token)
            if s.ebay_image_search and query.image_jpeg:
                resp = await c.post(
                    f"{s.ebay_api_base}/buy/browse/v1/item_summary/search_by_image",
                    params=params,
                    headers={**headers, "Content-Type": "application/json"},
                    json={"image": base64.b64encode(query.image_jpeg).decode()},
                )
                if resp.status_code == 200:
                    items.extend(resp.json().get("itemSummaries", []))
                elif resp.status_code in (401, 403):
                    log.warning("ebay search_by_image not permitted for this keyset: %s", resp.status_code)
                elif resp.status_code >= 500:
                    raise ProviderError(f"ebay image search HTTP {resp.status_code}")
            text = (query.texts.get("en") or [None])[0]
            if text and len(items) < query.limit:
                resp = await c.get(
                    f"{s.ebay_api_base}/buy/browse/v1/item_summary/search",
                    params={**params, "q": text},
                    headers=headers,
                )
                if resp.status_code == 401:
                    await get_redis().delete(TOKEN_KEY)
                if resp.status_code != 200:
                    if not items:
                        raise ProviderError(f"ebay search HTTP {resp.status_code}: {resp.text[:200]}")
                else:
                    items.extend(resp.json().get("itemSummaries", []))
        out: list[NormalizedProduct] = []
        seen: set[str] = set()
        for raw in items:
            p = self.normalize_product(raw)
            if p and p.external_id not in seen:
                seen.add(p.external_id)
                out.append(p)
        return out[: query.limit]

    def normalize_product(self, raw: dict[str, Any]) -> NormalizedProduct | None:
        item_id = raw.get("itemId")
        title = raw.get("title")
        url = raw.get("itemAffiliateWebUrl") or raw.get("itemWebUrl")
        if not (item_id and title and url):
            return None
        price = raw.get("price") or {}
        image = (raw.get("image") or {}).get("imageUrl") or next(
            (t.get("imageUrl") for t in raw.get("thumbnailImages", []) if t.get("imageUrl")), None
        )
        cond_id = str(raw.get("conditionId", ""))
        condition = "new" if cond_id in _COND_NEW else "refurbished" if cond_id in _COND_REFURB else ("used" if cond_id else None)
        availability = None
        avail = raw.get("estimatedAvailabilities") or []
        if avail:
            st = avail[0].get("estimatedAvailabilityStatus")
            availability = st in ("IN_STOCK", "LIMITED_STOCK") if st else None
        return NormalizedProduct(
            source=self.code,
            external_id=str(item_id),
            title=str(title)[:500],
            url=url,
            image_url=image,
            price=to_decimal(price.get("value")),
            currency=price.get("currency"),
            condition=condition,
            brand=raw.get("brand"),
            category=(raw.get("categories") or [{}])[0].get("categoryName") if raw.get("categories") else None,
            size=raw.get("size"),
            color=raw.get("color"),
            country=(raw.get("itemLocation") or {}).get("country"),
            seller=(raw.get("seller") or {}).get("username"),
            available=availability,
            raw={k: raw.get(k) for k in ("itemId", "conditionId", "buyingOptions", "itemEndDate")},
        )

    async def get_product(self, external_id: str) -> NormalizedProduct | None:
        self.ensure_usable()
        s = get_settings()
        async with http.client() as c:
            token = await self._token(c)
            resp = await c.get(f"{s.ebay_api_base}/buy/browse/v1/item/{external_id}", headers=self._headers(token))
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise ProviderError(f"ebay item HTTP {resp.status_code}")
        return self.normalize_product(resp.json())

    async def health_check(self) -> None:
        self.ensure_usable()
        started = time.monotonic()
        async with http.client(10) as c:
            await self._token(c)
        log.debug("ebay health ok in %.0f ms", (time.monotonic() - started) * 1000)
