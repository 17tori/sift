"""Collections, item watches, shared finds and gift searches."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Collection(TimestampMixin, Base):
    __tablename__ = "collections"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(64), nullable=False)


class Watch(TimestampMixin, Base):
    """ULTRA: a saved photo search re-run daily; the user hears about cheaper offers and new listings."""

    __tablename__ = "watches"
    __table_args__ = (UniqueConstraint("user_id", "search_id", name="uq_watches_user_search"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    search_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("search_sessions.id", ondelete="CASCADE"), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    title: Mapped[str | None] = mapped_column(String(160))
    best_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))  # in best_currency
    best_currency: Mapped[str | None] = mapped_column(String(8))
    known_product_ids: Mapped[list[int]] = mapped_column(JSONB, default=list, nullable=False)
    runs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_found_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_search_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("search_sessions.id", ondelete="SET NULL"))


class Share(TimestampMixin, Base):
    """A find shared by a user: postcard image + deep link that also attributes the referral."""

    __tablename__ = "shares"

    token: Mapped[str] = mapped_column(String(16), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    search_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("search_sessions.id", ondelete="SET NULL"))
    card_key: Mapped[str | None] = mapped_column(String(256))  # rendered postcard in storage
    opens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Gift(TimestampMixin, Base):
    """Searches bought with Stars for someone else; redeemed once through a link."""

    __tablename__ = "gifts"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    pack: Mapped[str] = mapped_column(String(16), nullable=False)
    searches: Mapped[int] = mapped_column(Integer, nullable=False)
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id", ondelete="SET NULL"), unique=True)
    redeemed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(12), default="active", nullable=False)  # active|redeemed|refunded
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
