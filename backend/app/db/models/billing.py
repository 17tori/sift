from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Plan(Base):
    """Tariff. Prices/limits are edited by admins; the UI reads them from the API."""

    __tablename__ = "plans"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)  # free | pro | ultra
    title: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    price_stars: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    period_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    search_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    limit_window: Mapped[str] = mapped_column(String(8), default="month", nullable=False)  # day | month
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    features: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscriptions"
    __table_args__ = (Index("ix_subscriptions_user_active", "user_id", "status", "expires_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    plan_code: Mapped[str] = mapped_column(ForeignKey("plans.code"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # active|expired|canceled|refunded|revoked
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # payment|trial|admin|referral
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Charge id of the *first* payment: Telegram identifies a Stars subscription by it.
    telegram_charge_id: Mapped[str | None] = mapped_column(String(256), index=True)
    intent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("payment_intents.id", ondelete="SET NULL"))
    expiry_notified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    note: Mapped[str | None] = mapped_column(String(256))


class PaymentIntent(TimestampMixin, Base):
    """Server-side record of an invoice. pre_checkout_query is validated against it."""

    __tablename__ = "payment_intents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_code: Mapped[str] = mapped_column(ForeignKey("plans.code"), nullable=False)
    amount_stars: Mapped[int] = mapped_column(Integer, nullable=False)
    period_days: Mapped[int] = mapped_column(Integer, nullable=False)
    recurring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    payload: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)  # pending|paid|expired
    invoice_link: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Payment(TimestampMixin, Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    intent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("payment_intents.id", ondelete="SET NULL"))
    subscription_id: Mapped[int | None] = mapped_column(ForeignKey("subscriptions.id", ondelete="SET NULL"))
    plan_code: Mapped[str] = mapped_column(ForeignKey("plans.code"), nullable=False)
    amount_stars: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="XTR", nullable=False)
    # Unique: the primary guard against processing the same payment twice.
    telegram_payment_charge_id: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    provider_payment_charge_id: Mapped[str | None] = mapped_column(String(256))
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_first_recurring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    subscription_expiration_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="paid", nullable=False)  # paid|refunded
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
