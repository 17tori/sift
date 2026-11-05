"""AliExpress Affiliate (Portals) API via the official IOP gateway.

Docs: https://openservice.aliexpress.com (Affiliate API: aliexpress.affiliate.product.query,
aliexpress.affiliate.productdetail.get). Requires an approved Affiliate app (app_key/secret)
and a tracking_id from portals.aliexpress.com. Links returned are official promotion links.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any

from app.core.config import get_settings
from app.marketplace import http
from app.marketplace.base import (
    IntegrationKind,
    MarketplaceProvider,
    NormalizedProduct,
    ProviderError,
    SearchQuery,
    to_decimal,
)


def sign_iop(params: dict[str, str], secret: str) -> str:
    """IOP 'sync' signature: HMAC-SHA256 over sorted key+value pairs, upper-case hex."""
    msg = "".join(f"{k}{params[k]}" for k in sorted(params))
    return hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest().upper()


class AliExpressProvider(MarketplaceProvider):
    code = "aliexpress"
    name = "AliExpress"
    url = "https://www.aliexpress.com"
    kind = IntegrationKind.AFFILIATE_API
    regions = ["GLOBAL"]
    languages = ("en", "ru")
    supports_image_search = False
    note = "Официальный AliExpress Affiliate API (поиск по ключевым словам, партнёрские ссылки)."

    def configured(self) -> bool:
        s = get_settings()
        return bool(s.aliexpress_app_key and s.aliexpress_app_secret.get_secret_value() and s.aliexpress_tracking_id)

    async def _call(self, method: str, biz: dict[str, Any]) -> dict[str, Any]:
        s = get_settings()
        params = {
            "app_key": s.aliexpress_app_key,
            "method": method,
            "timestamp": str(int(time.time() * 1000)),
            "sign_method": "sha256",
            **{k: str(v) for k, v in biz.items() if v is not None},
        }
        params["sign"] = sign_iop(params, s.aliexpress_app_secret.get_secret_value())
        async with http.client() as c:
            resp = await c.post(s.aliexpress_gateway, data=params)
        if resp.status_code != 200:
            raise ProviderError(f"aliexpress HTTP {resp.status_code}")
        body = resp.json()
        if "error_response" in body:
            err = body["error_response"]
            raise ProviderError(f"aliexpress {err.get('code')}: {err.get('msg')}")
        root = body.get(method.replace(".", "_") + "_response", {})
        result = root.get("resp_result", {})
        if int(result.get("resp_code", 0) or 0) not in (200, 0):
            raise ProviderError(f"aliexpress resp_code {result.get('resp_code')}: {result.get('resp_msg')}")
        return result.get("result", {}) or {}

    async def search(self, query: SearchQuery) -> list[NormalizedProduct]:
        self.ensure_usable()
        s = get_settings()
        keywords = (query.texts.get("en") or query.texts.get("ru") or [None])[0]
        if not keywords:
            return []
        biz: dict[str, Any] = {
            "keywords": keywords,
            "page_no": 1,
            "page_size": min(query.limit, 50),
            "target_currency": s.aliexpress_target_currency,
            "target_language": s.aliexpress_target_language,
            "ship_to_country": s.aliexpress_ship_to_country,
            "tracking_id": s.aliexpress_tracking_id,
            "sort": "LAST_VOLUME_DESC",
        }
        if query.price_min is not None:
            biz["min_sale_price"] = int(query.price_min * 100)  # cents
        if query.price_max is not None:
            biz["max_sale_price"] = int(query.price_max * 100)
        result = await self._call("aliexpress.affiliate.product.query", biz)
        raw_items = (result.get("products") or {}).get("product") or []
        return [p for p in (self.normalize_product(r) for r in raw_items) if p]

    def normalize_product(self, raw: dict[str, Any]) -> NormalizedProduct | None:
        pid = raw.get("product_id")
        url = raw.get("promotion_link") or raw.get("product_detail_url")
        title = raw.get("product_title")
        if not (pid and url and title):
            return None
        return NormalizedProduct(
            source=self.code,
            external_id=str(pid),
            title=str(title)[:500],
            url=url,
            image_url=raw.get("product_main_image_url"),
            price=to_decimal(raw.get("target_sale_price") or raw.get("sale_price")),
            currency=raw.get("target_sale_price_currency") or raw.get("sale_price_currency"),
            condition="new",
            category=raw.get("second_level_category_name") or raw.get("first_level_category_name"),
            seller=raw.get("shop_name") or (str(raw["shop_id"]) if raw.get("shop_id") else None),
            country="CN",
            available=None,  # the affiliate API does not expose stock
            raw={k: raw.get(k) for k in ("product_id", "evaluate_rate", "lastest_volume", "discount")},
        )

    async def get_product(self, external_id: str) -> NormalizedProduct | None:
        self.ensure_usable()
        s = get_settings()
        result = await self._call(
            "aliexpress.affiliate.productdetail.get",
            {
                "product_ids": external_id,
                "target_currency": s.aliexpress_target_currency,
                "target_language": s.aliexpress_target_language,
                "country": s.aliexpress_ship_to_country,
                "tracking_id": s.aliexpress_tracking_id,
            },
        )
        items = (result.get("products") or {}).get("product") or []
        return self.normalize_product(items[0]) if items else None
