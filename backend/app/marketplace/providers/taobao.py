"""Taobao via Taobao Union (淘宝联盟 / Alimama) on the Taobao Open Platform (TOP).

Method: taobao.tbk.dg.material.optional.upgrade (keyword material search for affiliates).
Requires a TOP app with Taobao Union permissions and an adzone_id (推广位). Registration
normally needs a Chinese legal entity or an approved overseas partner. The response field
mapping below follows the published schema; verify it with live credentials before launch
(docs/MARKETPLACES.md -> Taobao).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
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

CN_TZ = timezone(timedelta(hours=8))


def sign_top_md5(params: dict[str, str], secret: str) -> str:
    msg = secret + "".join(f"{k}{params[k]}" for k in sorted(params)) + secret
    return hashlib.md5(msg.encode()).hexdigest().upper()  # noqa: S324 - mandated by TOP


def _https(url: str | None) -> str | None:
    if not url:
        return None
    return "https:" + url if url.startswith("//") else url


class TaobaoProvider(MarketplaceProvider):
    code = "taobao"
    name = "Taobao"
    url = "https://www.taobao.com"
    kind = IntegrationKind.AFFILIATE_API
    regions = ["CN"]
    languages = ("zh",)
    note = "Официальный Taobao Union (TOP) API: поиск товаров для партнёров, партнёрские ссылки."

    def configured(self) -> bool:
        s = get_settings()
        return bool(s.taobao_app_key and s.taobao_app_secret.get_secret_value() and s.taobao_adzone_id)

    async def _call(self, method: str, biz: dict[str, Any]) -> dict[str, Any]:
        s = get_settings()
        params = {
            "method": method,
            "app_key": s.taobao_app_key,
            "timestamp": datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M:%S"),
            "format": "json",
            "v": "2.0",
            "sign_method": "md5",
            **{k: str(v) for k, v in biz.items() if v is not None},
        }
        params["sign"] = sign_top_md5(params, s.taobao_app_secret.get_secret_value())
        async with http.client() as c:
            resp = await c.post(s.taobao_gateway, data=params)
        if resp.status_code != 200:
            raise ProviderError(f"taobao HTTP {resp.status_code}")
        body = resp.json()
        if "error_response" in body:
            e = body["error_response"]
            raise ProviderError(f"taobao {e.get('code')}/{e.get('sub_code')}: {e.get('sub_msg') or e.get('msg')}")
        return body.get(method.replace("taobao.", "").replace(".", "_") + "_response", {})

    async def search(self, query: SearchQuery) -> list[NormalizedProduct]:
        self.ensure_usable()
        q = (query.texts.get("zh") or query.texts.get("en") or [None])[0]
        if not q:
            return []
        s = get_settings()
        biz: dict[str, Any] = {"q": q, "adzone_id": s.taobao_adzone_id, "page_size": min(query.limit, 50), "page_no": 1}
        if query.price_min is not None:
            biz["start_price"] = int(query.price_min)
        if query.price_max is not None:
            biz["end_price"] = int(query.price_max)
        data = await self._call("taobao.tbk.dg.material.optional.upgrade", biz)
        rows = ((data.get("result_list") or {}).get("map_data")) or []
        return [p for p in (self.normalize_product(r) for r in rows) if p]

    def normalize_product(self, raw: dict[str, Any]) -> NormalizedProduct | None:
        basic = raw.get("item_basic_info") or {}
        price_info = raw.get("price_promotion_info") or {}
        publish = raw.get("publish_info") or {}
        item_id = raw.get("item_id")
        title = basic.get("title") or basic.get("short_title")
        url = _https(publish.get("click_url") or publish.get("coupon_share_url"))
        if not (item_id and title and url):
            return None
        return NormalizedProduct(
            source=self.code,
            external_id=str(item_id),
            title=str(title)[:500],
            url=url,
            image_url=_https(basic.get("pict_url") or basic.get("white_image")),
            price=to_decimal(price_info.get("final_promotion_price") or price_info.get("zk_final_price") or price_info.get("reserve_price")),
            currency="CNY",
            condition="new",
            seller=basic.get("shop_title") or basic.get("nick"),
            category=basic.get("category_name") or basic.get("level_one_category_name"),
            country="CN",
            available=None,
            raw={"item_id": item_id, "provcity": basic.get("provcity"), "volume": basic.get("volume")},
        )

    async def get_product(self, external_id: str) -> NormalizedProduct | None:
        # Detailed item lookups (taobao.tbk.item.info.upgrade) need extra permissions; not exposed.
        return None
