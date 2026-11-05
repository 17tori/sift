"""Unified marketplace integration contract.

Every source implements `MarketplaceProvider`. A provider either has a legal, working
integration (official API / affiliate API / licensed feed) or declares precisely why it
cannot return results. Nothing here ever fabricates listings.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any


class IntegrationKind(StrEnum):
    OFFICIAL_API = "official_api"
    AFFILIATE_API = "affiliate_api"
    PARTNER_FEED = "partner_feed"
    WEB_SEARCH = "web_search"  # public search-engine index via Claude web search; the site itself is never scraped
    NONE = "none"


class ProviderState(StrEnum):
    ACTIVE = "active"  # implemented and configured
    NOT_CONFIGURED = "not_configured"  # implemented, credentials / feed missing
    NO_LEGAL_API = "no_legal_api"  # no official way to search third-party listings
    DISABLED = "disabled"  # switched off in configuration
    DOWN = "down"  # implemented + configured, but health checks fail


class ProviderUnavailable(Exception):
    def __init__(self, state: ProviderState, reason: str) -> None:
        super().__init__(reason)
        self.state = state
        self.reason = reason


class ProviderError(Exception):
    """Transient failure of a working integration (HTTP 5xx, timeout, quota)."""


@dataclass(slots=True)
class NormalizedProduct:
    source: str
    external_id: str
    title: str
    url: str
    image_url: str | None
    price: Decimal | None
    currency: str | None
    condition: str | None = None  # new | used | refurbished
    brand: str | None = None
    category: str | None = None
    size: str | None = None
    color: str | None = None
    country: str | None = None
    seller: str | None = None
    available: bool | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SearchQuery:
    texts: dict[str, list[str]]  # language -> queries
    image_jpeg: bytes | None
    query_embedding: list[float] | None
    embedding_model: str | None
    category: str | None
    gender: str | None
    price_min: Decimal | None = None
    price_max: Decimal | None = None
    condition: str | None = None
    limit: int = 40
    image_public_url: str | None = None  # signed absolute URL of the query photo (for services that fetch by URL)
    # Per-run scratch space shared by providers of one search (e.g. a single web-search call for several sources).
    shared: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProviderInfo:
    code: str
    name: str
    url: str
    kind: IntegrationKind
    state: ProviderState
    note: str
    supports_image_search: bool
    regions: list[str]


def to_decimal(v: Any) -> Decimal | None:
    if v is None or v == "":
        return None
    try:
        d = Decimal(str(v).replace(",", ".").replace(" ", ""))
    except (InvalidOperation, ValueError):
        return None
    return d.quantize(Decimal("0.01")) if d >= 0 else None


class MarketplaceProvider(abc.ABC):
    code: str
    name: str
    url: str
    kind: IntegrationKind
    regions: list[str] = []
    languages: tuple[str, ...] = ("en",)
    supports_image_search: bool = False
    note: str = ""
    timeout_seconds: float | None = None  # overrides PROVIDER_TIMEOUT_SECONDS

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    # --- state -------------------------------------------------------------
    @abc.abstractmethod
    def configured(self) -> bool: ...

    def state(self) -> ProviderState:
        if self.kind is IntegrationKind.NONE:
            return ProviderState.NO_LEGAL_API
        if not self.enabled:
            return ProviderState.DISABLED
        if not self.configured():
            return ProviderState.NOT_CONFIGURED
        return ProviderState.ACTIVE

    def info(self) -> ProviderInfo:
        return ProviderInfo(self.code, self.name, self.url, self.kind, self.state(), self.note, self.supports_image_search, list(self.regions))

    def ensure_usable(self) -> None:
        st = self.state()
        if st is not ProviderState.ACTIVE:
            raise ProviderUnavailable(st, self.note or st.value)

    async def prepare(self) -> None:
        """Refresh any lazily known state before a search run (no-op by default)."""
        return None

    # --- contract ----------------------------------------------------------
    @abc.abstractmethod
    async def search(self, query: SearchQuery) -> list[NormalizedProduct]: ...

    @abc.abstractmethod
    async def get_product(self, external_id: str) -> NormalizedProduct | None: ...

    @abc.abstractmethod
    def normalize_product(self, raw: dict[str, Any]) -> NormalizedProduct | None: ...

    async def check_availability(self, external_id: str) -> bool | None:
        """True/False when the source reports stock, None when it does not expose it."""
        p = await self.get_product(external_id)
        return None if p is None else p.available

    async def health_check(self) -> None:
        """Raise ProviderError when the integration is not reachable."""
        self.ensure_usable()


class NoLegalApiProvider(MarketplaceProvider):
    """A source with no sanctioned way to search third-party listings. Never returns data."""

    kind = IntegrationKind.NONE

    def configured(self) -> bool:
        return False

    async def search(self, query: SearchQuery) -> list[NormalizedProduct]:
        raise ProviderUnavailable(ProviderState.NO_LEGAL_API, self.note)

    async def get_product(self, external_id: str) -> NormalizedProduct | None:
        raise ProviderUnavailable(ProviderState.NO_LEGAL_API, self.note)

    def normalize_product(self, raw: dict[str, Any]) -> NormalizedProduct | None:
        return None
