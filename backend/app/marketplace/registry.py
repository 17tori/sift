from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.marketplace import web
from app.marketplace.base import MarketplaceProvider, ProviderState
from app.marketplace.providers.aliexpress import AliExpressProvider
from app.marketplace.providers.ebay import EbayProvider
from app.marketplace.providers.feed import FeedCatalogProvider, WildberriesProvider
from app.marketplace.providers.taobao import TaobaoProvider
from app.marketplace.providers.unavailable import (
    AvitoProvider,
    GoofishProvider,
    GrailedProvider,
    VintedProvider,
)

ALL_PROVIDERS: tuple[type[MarketplaceProvider], ...] = (
    WildberriesProvider,
    AvitoProvider,
    GoofishProvider,
    VintedProvider,
    GrailedProvider,
    AliExpressProvider,
    TaobaoProvider,
    EbayProvider,
)


@lru_cache
def providers() -> dict[str, MarketplaceProvider]:
    s = get_settings()
    enabled = set(s.marketplaces_enabled)
    if s.goofish_enabled:
        enabled.add("goofish")
    else:
        enabled.discard("goofish")
    out: dict[str, MarketplaceProvider] = {}
    for cls in ALL_PROVIDERS:
        p = cls(enabled=cls.code in enabled)
        # No legal API, or official keys not entered yet -> serve through the web sources when configured.
        if p.state() in (ProviderState.NO_LEGAL_API, ProviderState.NOT_CONFIGURED) and p.enabled and web.web_enabled_for(p.code):
            if not isinstance(p, FeedCatalogProvider):
                p = web.WebFallbackProvider(p)
        out[cls.code] = p
    return out


def visible_providers() -> list[MarketplaceProvider]:
    """What the Mini App lists: everything except sources switched off in config."""
    return [p for p in providers().values() if p.enabled]


def get(code: str) -> MarketplaceProvider | None:
    return providers().get(code)
