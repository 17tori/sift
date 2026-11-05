"""Gift searches: bought with Telegram Stars, redeemed once by whoever opens the link (not the buyer)."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from aiogram.types import LabeledPrice
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError, NotFound
from app.db.models import Gift, Payment, PaymentIntent, User
from app.services.app_settings import get_setting
from app.services.telegram import get_bot

GIFT_PLAN = "free"  # payment_intents.plan_code is required; gift intents carry kind="gift" instead


async def packs(session: AsyncSession) -> list[dict]:
    cfg = await get_setting(session, "gifts")
    if not cfg.get("enabled", True):
        return []
    return [p for p in cfg.get("packs", []) if int(p.get("searches", 0)) > 0 and int(p.get("stars", 0)) > 0]


async def _pack(session: AsyncSession, code: str) -> dict:
    for p in await packs(session):
        if p["code"] == code:
            return p
    raise AppError("gift_pack_unknown", "Такого подарка нет.")


async def create_invoice(session: AsyncSession, user: User, pack_code: str) -> PaymentIntent:
    from app.services.payments import make_payload

    s = get_settings()
    pack = await _pack(session, pack_code)
    intent_id = uuid.uuid4()
    intent = PaymentIntent(
        id=intent_id,
        user_id=user.id,
        plan_code=GIFT_PLAN,
        kind="gift",
        gift_pack=pack["code"],
        amount_stars=int(pack["stars"]),
        period_days=0,
        recurring=False,
        payload=make_payload(intent_id),
        status="pending",
        expires_at=datetime.now(UTC) + timedelta(minutes=s.payment_intent_ttl_minutes),
    )
    session.add(intent)
    await session.flush()
    n = int(pack["searches"])
    intent.invoice_link = await get_bot().create_invoice_link(
        title=f"{s.brand_name}: {n} поисков в подарок"[:32],
        description=f"{n} поисков по фото для друга. После оплаты придёт ссылка, которую можно переслать.",
        payload=intent.payload,
        currency="XTR",
        prices=[LabeledPrice(label=f"Подарок · {n} поисков", amount=int(pack["stars"]))],
    )
    return intent


async def on_paid(session: AsyncSession, intent: PaymentIntent, payment: Payment) -> Gift:
    """Idempotent per payment (gifts.payment_id is unique)."""
    existing = await session.scalar(select(Gift).where(Gift.payment_id == payment.id))
    if existing is not None:
        return existing
    cfg_pack = next((p for p in await packs(session) if p["code"] == intent.gift_pack), None)
    searches = int(cfg_pack["searches"]) if cfg_pack else max(1, intent.amount_stars // 10)
    gift = Gift(
        code=secrets.token_urlsafe(9)[:12],
        buyer_id=intent.user_id,
        pack=intent.gift_pack or "custom",
        searches=searches,
        payment_id=payment.id,
        status="active",
    )
    session.add(gift)
    intent.status = "paid"
    await session.flush()
    return gift


def gift_link(code: str) -> str:
    from app.services.shares import app_link

    return app_link(f"g_{code}")


async def redeem(session: AsyncSession, user: User, code: str) -> tuple[Gift, User]:
    gift = await session.get(Gift, code, with_for_update=True)
    if gift is None:
        raise NotFound("gift_not_found", "Подарок не найден.")
    buyer = await session.get(User, gift.buyer_id)
    assert buyer is not None
    if gift.status == "redeemed":
        if gift.redeemed_by_id == user.id:
            return gift, buyer
        raise AppError("gift_used", "Этот подарок уже активирован.")
    if gift.status != "active":
        raise AppError("gift_unavailable", "Подарок недоступен.")
    if gift.buyer_id == user.id:
        raise AppError("gift_own", "Это ваш подарок: перешлите ссылку другу.")
    gift.status = "redeemed"
    gift.redeemed_by_id = user.id
    gift.redeemed_at = datetime.now(UTC)
    await session.execute(update(User).where(User.id == user.id).values(bonus_searches=User.bonus_searches + gift.searches))
    return gift, buyer


async def on_refund(session: AsyncSession, payment: Payment) -> None:
    await session.execute(update(Gift).where(Gift.payment_id == payment.id, Gift.status == "active").values(status="refunded"))


async def buyer_referral_code(session: AsyncSession, code: str) -> str | None:
    return await session.scalar(select(User.referral_code).join(Gift, Gift.buyer_id == User.id).where(Gift.code == code))
