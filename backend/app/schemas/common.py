from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PlanOut(ORM):
    code: str
    title: str
    description: str
    price_stars: int
    period_days: int
    search_limit: int
    limit_window: str
    priority: int
    sort_order: int
    is_active: bool
    features: dict[str, Any]


class SubscriptionOut(ORM):
    id: int
    plan_code: str
    status: str
    source: str
    started_at: datetime
    expires_at: datetime
    is_recurring: bool
    auto_renew: bool
    canceled_at: datetime | None


class QuotaOut(BaseModel):
    used: int
    limit: int
    window: str
    resets_at: datetime
    bonus: int
    remaining: int


class TrialOut(BaseModel):
    available: bool
    active: bool
    used: bool
    ends_at: datetime | None
    days: int


class ReferralOut(BaseModel):
    code: str
    link: str
    invited: int
    purchased: int
    earned_searches: int
    reward_registration: int
    reward_first_purchase: int
    invitee_bonus: int


class MeOut(BaseModel):
    id: int
    telegram_id: int
    username: str | None
    first_name: str
    photo_url: str | None
    language_code: str | None
    created_at: datetime
    is_admin: bool
    plan: PlanOut
    subscription: SubscriptionOut | None
    quota: QuotaOut
    trial: TrialOut
    preferences: dict[str, Any]
    total_searches: int
    favorites_count: int


class PreferencesIn(BaseModel):
    theme: Literal["system", "light", "dark"] | None = None
    currency: Literal["RUB", "USD", "EUR", "CNY", "GBP", "KZT"] | None = None
    country: str | None = Field(default=None, max_length=8)
    default_mode: Literal["exact", "similar", "cheaper", "discover"] | None = None
    language: Literal["ru", "en"] | None = None
    view: Literal["grid", "list"] | None = None


class MarketplaceOut(BaseModel):
    code: str
    name: str
    url: str
    kind: str
    state: str
    note: str
    supports_image_search: bool
    regions: list[str]


class ConfigOut(BaseModel):
    brand: dict[str, str]
    bot_username: str
    marketplaces: list[MarketplaceOut]
    upload: dict[str, Any]
    modes: list[str]
    categories: list[str]


class InvoiceIn(BaseModel):
    plan_code: str


class InvoiceOut(BaseModel):
    intent_id: uuid.UUID
    invoice_link: str
    amount_stars: int
    recurring: bool


class IntentOut(BaseModel):
    intent_id: uuid.UUID
    status: str
    plan_code: str


class PaymentOut(ORM):
    id: int
    plan_code: str
    amount_stars: int
    currency: str
    status: str
    is_recurring: bool
    created_at: datetime
    refunded_at: datetime | None


class AutoRenewIn(BaseModel):
    enabled: bool


class SearchOut(BaseModel):
    id: uuid.UUID
    status: str
    stage: str
    mode: str
    created_at: datetime
    finished_at: datetime | None
    image_url: str | None
    analysis: dict[str, Any] | None
    providers: dict[str, Any]
    results_count: int
    error: str | None
    reference_price: Decimal | None
    reference_currency: str | None
    has_similarity: bool


class ProductOut(BaseModel):
    product_id: int
    marketplace: str
    marketplace_name: str
    title: str
    url: str
    image_url: str | None
    image_fallback_url: str | None = None  # remote photo, when image_url is our stored copy
    price: Decimal | None
    currency: str | None
    price_converted: Decimal | None
    converted_currency: str | None
    similarity: int | None  # calibrated %, present only if computed by the embedding model
    available: bool | None
    condition: str | None
    brand: str | None
    category: str | None
    size: str | None
    color: str | None
    country: str | None
    seller: str | None
    is_favorite: bool
    via: str | None = None  # google_lens | web_search: found through a web source, not the marketplace API


class ResultsOut(BaseModel):
    items: list[ProductOut]
    total: int
    next_offset: int | None
    facets: dict[str, list[dict[str, Any]]]
    filters_locked: bool


class FavoriteIn(BaseModel):
    product_id: int
    search_id: uuid.UUID | None = None


class FavoritePatch(BaseModel):
    price_alert: bool


class FavoriteOut(BaseModel):
    id: int
    created_at: datetime
    price_alert: bool
    saved_price: Decimal | None
    saved_currency: str | None
    product: ProductOut


class SupportIn(BaseModel):
    message: str = Field(min_length=3, max_length=2000)


class HistoryItem(BaseModel):
    id: uuid.UUID
    status: str
    mode: str
    created_at: datetime
    image_url: str | None
    title: str | None
    results_count: int


class HistoryOut(BaseModel):
    items: list[HistoryItem]
    next_cursor: str | None
    limited_days: int | None
