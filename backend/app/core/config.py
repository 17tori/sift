"""Central configuration. Every tunable value comes from environment variables.

Business values that admins change at runtime (plan prices, limits, trial length,
referral rewards) live in the database (`plans`, `app_settings`) and are only
*seeded* from here.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- environment -------------------------------------------------------
    environment: Literal["production", "staging", "development", "test"] = "production"
    log_level: str = "INFO"
    log_json: bool = True

    # --- branding (white-label) -------------------------------------------
    brand_name: str = "SIFT"
    brand_tagline: str = "Find beyond the image."
    brand_tagline_ru: str = "Одна фотография. Все маркетплейсы."
    brand_support_username: str = ""  # Telegram @username of support, without @
    brand_support_email: str = ""
    brand_accent: str = "#526BFF"

    # --- public URLs --------------------------------------------------------
    domain: str = "localhost"
    public_base_url: str = "https://localhost"  # where nginx serves the Mini App + API
    webapp_url: str = "https://localhost/"  # Mini App URL registered in BotFather

    # --- security -----------------------------------------------------------
    secret_key: SecretStr = SecretStr("change-me")  # HMAC for signed media URLs etc.
    init_data_max_age_seconds: int = 86400
    admin_telegram_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # --- telegram -----------------------------------------------------------
    bot_token: SecretStr = SecretStr("")
    bot_username: str = ""
    bot_mode: Literal["polling", "webhook"] = "polling"
    bot_webhook_secret: SecretStr = SecretStr("")
    bot_webhook_path: str = "/tg/webhook"
    telegram_api_base: str = "https://api.telegram.org"

    # --- database / cache ---------------------------------------------------
    database_url: str = "postgresql+asyncpg://sift:sift@postgres:5432/sift"
    db_pool_size: int = 5
    db_max_overflow: int = 5
    redis_url: str = "redis://redis:6379/0"
    broker_url: str = "redis://redis:6379/1"

    # --- storage ------------------------------------------------------------
    storage_backend: Literal["local"] = "local"
    storage_path: str = "/data/uploads"
    media_url_ttl_seconds: int = 3600
    upload_max_bytes: int = 10 * 1024 * 1024
    upload_max_pixels: int = 40_000_000
    upload_normalized_max_side: int = 1280
    upload_retention_days: int = 90

    # --- AI -----------------------------------------------------------------
    embedding_provider: Literal["jina", "voyage", "none"] = "none"
    embedding_dim: int = 1024  # must match the pgvector column (set in migration 0001)
    jina_api_key: SecretStr = SecretStr("")
    jina_model: str = "jina-clip-v2"
    voyage_api_key: SecretStr = SecretStr("")
    voyage_model: str = "voyage-multimodal-3"
    embedding_batch_size: int = 32
    embedding_timeout_seconds: float = 30.0

    vision_provider: Literal["gemini", "anthropic", "openai_compatible", "none"] = "gemini"
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "gemini-3.8-flash"
    anthropic_api_key: SecretStr = SecretStr("")
    anthropic_model: str = "claude-opus-5-5"
    anthropic_effort: Literal["low", "medium", "high"] = "low"
    anthropic_server_fallbacks: bool = True
    openai_compat_base_url: str = ""
    openai_compat_api_key: SecretStr = SecretStr("")
    openai_compat_model: str = ""
    vision_timeout_seconds: float = 60.0

    # Cosine-similarity -> displayed percentage calibration. Must be calibrated on a
    # labelled set for the chosen embedding model (see docs/AI.md). Below `low` the
    # score is 0 %, above `high` 100 %, linear in between.
    similarity_calibration_low: float = 0.55
    similarity_calibration_high: float = 0.93
    duplicate_cosine_threshold: float = 0.985

    # --- search -------------------------------------------------------------
    provider_timeout_seconds: float = 20.0
    search_total_timeout_seconds: float = 90.0
    search_results_per_provider: int = 40
    candidate_image_max_bytes: int = 5 * 1024 * 1024

    # --- marketplaces -------------------------------------------------------
    # Comma separated provider codes that are switched on. Providers without a legal
    # search integration stay listed with their real status but never return results.
    # Web sources for marketplaces without an API or keys: Google Vision web detection (by photo)
    # and Claude web search (by description). Neither requests the marketplace sites.
    # serper: Google Lens via serper.dev (best product matches; a third-party Google results API, see
    # docs/MARKETPLACES.md). google_vision: official Cloud Vision web detection.
    lens_provider: Literal["serper", "google_vision", "none"] = "serper"
    google_vision_api_key: SecretStr = SecretStr("")
    serper_api_key: SecretStr = SecretStr("")
    serper_country: str = "ru"
    serper_language: str = "ru"
    serper_images: bool = True  # Google Images query alongside text search: photos for listings without one
    # Search by description: serper (Google search via serper.dev) | claude (Claude web search) | none
    text_search_provider: Literal["serper", "claude", "none"] = "serper"
    web_search_marketplaces: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["avito", "wildberries", "vinted", "grailed", "ebay", "aliexpress", "taobao"]
    )
    web_search_model: str = "claude-sonnet-5-5"
    web_search_max_uses: int = 5
    web_search_timeout_seconds: float = 70.0

    marketplaces_enabled: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["ebay", "aliexpress", "taobao", "wildberries", "avito", "vinted", "grailed"]
    )
    ebay_client_id: str = ""
    ebay_client_secret: SecretStr = SecretStr("")
    ebay_marketplace_id: str = "EBAY_US"
    ebay_affiliate_campaign_id: str = ""
    ebay_category_ids: str = "11450"  # Clothing, Shoes & Accessories
    ebay_api_base: str = "https://api.ebay.com"
    ebay_image_search: bool = True

    aliexpress_app_key: str = ""
    aliexpress_app_secret: SecretStr = SecretStr("")
    aliexpress_tracking_id: str = ""
    aliexpress_target_currency: str = "USD"
    aliexpress_target_language: str = "EN"
    aliexpress_ship_to_country: str = "US"
    aliexpress_gateway: str = "https://api-sg.aliexpress.com/sync"

    taobao_app_key: str = ""
    taobao_app_secret: SecretStr = SecretStr("")
    taobao_adzone_id: str = ""
    taobao_gateway: str = "https://eco.taobao.com/router/rest"

    goofish_enabled: bool = False

    # --- payments -----------------------------------------------------------
    payments_recurring: bool = True  # Telegram Stars subscriptions (30-day period)
    payment_intent_ttl_minutes: int = 60

    # --- seeds (copied into DB on first migration; edit in admin afterwards) -
    trial_days: int = 3
    trial_auto_activate: bool = False

    @field_validator("admin_telegram_ids", "cors_origins", "marketplaces_enabled", "web_search_marketplaces", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                return json.loads(v)
            return [p.strip() for p in v.split(",") if p.strip()]
        if isinstance(v, int):
            return [v]
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
