from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    last_name: Mapped[str | None] = mapped_column(String(128))
    language_code: Mapped[str | None] = mapped_column(String(16))
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    photo_url: Mapped[str | None] = mapped_column(String(512))

    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    bot_started: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    blocked_reason: Mapped[str | None] = mapped_column(String(256))

    referral_code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    referred_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    bonus_searches: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    trial_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    trial_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trial_notified_24h: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    trial_notified_end: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    preferences: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
