from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import get_settings
from app.db.base import Base, TimestampMixin

EMBED_DIM = get_settings().embedding_dim


class SearchSession(TimestampMixin, Base):
    __tablename__ = "search_sessions"
    __table_args__ = (
        Index("ix_search_sessions_user_created", "user_id", "created_at"),
        Index("ix_search_sessions_created", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="queued", nullable=False)
    stage: Mapped[str] = mapped_column(String(24), default="uploaded", nullable=False)
    mode: Mapped[str] = mapped_column(String(12), default="similar", nullable=False)  # exact|similar|cheaper|discover
    image_key: Mapped[str] = mapped_column(String(256), nullable=False)
    image_hash: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    image_width: Mapped[int] = mapped_column(Integer, nullable=False)
    image_height: Mapped[int] = mapped_column(Integer, nullable=False)
    analysis: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    query_embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIM))
    embedding_model: Mapped[str | None] = mapped_column(String(64))
    providers_status: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    options: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    reference_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    reference_currency: Mapped[str | None] = mapped_column(String(8))
    error: Mapped[str | None] = mapped_column(Text)
    results_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quota_counted: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    used_bonus: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_products_source_external"),
        Index("ix_products_source_last_seen", "source", "last_seen_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    image_url: Mapped[str | None] = mapped_column(Text)
    # Our own copy of the listing photo (storage key) and the remote URL it was fetched from.
    thumb_key: Mapped[str | None] = mapped_column(Text)
    thumb_src: Mapped[str | None] = mapped_column(Text)
    price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(8))
    condition: Mapped[str | None] = mapped_column(String(24))  # new | used | refurbished
    brand: Mapped[str | None] = mapped_column(String(128))
    category: Mapped[str | None] = mapped_column(String(128))
    size: Mapped[str | None] = mapped_column(String(64))
    color: Mapped[str | None] = mapped_column(String(64))
    country: Mapped[str | None] = mapped_column(String(8))
    seller: Mapped[str | None] = mapped_column(String(128))
    available: Mapped[bool | None] = mapped_column(Boolean)
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_price_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProductEmbedding(TimestampMixin, Base):
    __tablename__ = "product_embeddings"
    __table_args__ = (
        UniqueConstraint("product_id", "model", name="uq_product_embeddings_product_model"),
        Index(
            "ix_product_embeddings_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBED_DIM), nullable=False)


class PriceHistory(Base):
    __tablename__ = "price_history"
    __table_args__ = (Index("ix_price_history_product_time", "product_id", "observed_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SearchResult(TimestampMixin, Base):
    __tablename__ = "search_results"
    __table_args__ = (
        UniqueConstraint("search_id", "product_id", name="uq_search_results_search_product"),
        Index("ix_search_results_search_rank", "search_id", "rank_score"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    search_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("search_sessions.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(24), nullable=False)
    cosine: Mapped[float | None] = mapped_column(Float)  # raw model cosine similarity
    similarity_pct: Mapped[int | None] = mapped_column(Integer)  # calibrated, only when cosine exists
    text_rank: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # provider's own order
    rank_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Visual verification judged it a different item: hidden from results.
    is_rejected: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)


class Favorite(TimestampMixin, Base):
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("user_id", "product_id", name="uq_favorites_user_product"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    search_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("search_sessions.id", ondelete="SET NULL"))
    saved_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    saved_currency: Mapped[str | None] = mapped_column(String(8))
    price_alert: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_notified_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    collection_id: Mapped[int | None] = mapped_column(ForeignKey("collections.id", ondelete="SET NULL"), index=True)
