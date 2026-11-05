from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Referral(TimestampMixin, Base):
    __tablename__ = "referrals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    referrer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    referred_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    first_purchase_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReferralReward(TimestampMixin, Base):
    __tablename__ = "referral_rewards"
    __table_args__ = (UniqueConstraint("referral_id", "event", name="uq_referral_rewards_referral_event"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    referral_id: Mapped[int] = mapped_column(ForeignKey("referrals.id", ondelete="CASCADE"), nullable=False)
    beneficiary_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    event: Mapped[str] = mapped_column(String(24), nullable=False)  # registration | first_purchase
    reward_type: Mapped[str] = mapped_column(String(16), nullable=False)  # searches | pro_days
    amount: Mapped[int] = mapped_column(Integer, nullable=False)


class MarketplaceStatus(Base):
    __tablename__ = "marketplace_status"

    code: Mapped[str] = mapped_column(String(24), primary_key=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class AdminLog(TimestampMixin, Base):
    __tablename__ = "admin_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    admin_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target: Mapped[str | None] = mapped_column(String(128))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
