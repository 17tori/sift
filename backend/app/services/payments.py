"""Telegram Stars (XTR) payments.

Flow:
  1. Mini App -> POST /payments/invoice -> server creates PaymentIntent + invoice link.
  2. Mini App opens the link with WebApp.openInvoice().
  3. Bot receives pre_checkout_query -> validate_pre_checkout() against the intent.
  4. Bot receives successful_payment -> process_successful_payment(): idempotent by
     telegram_payment_charge_id (UNIQUE), grants/extends the subscription.
  5. Recurring renewals arrive as successful_payment with is_recurring=True and the same
     invoice payload; they extend the same subscription.
  6. Refunds: refundStarPayment (admin) and `refunded_payment` service messages.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from aiogram.types import LabeledPrice
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError, NotFound
from app.db.models import Gift, Payment, PaymentIntent, Plan, Subscription, User
from app.services import gifts, referrals, subscriptions
from app.services.telegram import get_bot

log = logging.getLogger(__name__)
STARS_SUBSCRIPTION_PERIOD = 2592000  # the only period Telegram supports for Stars subscriptions (30 days)
PAYLOAD_PREFIX = "sub:"


def make_payload(intent_id: uuid.UUID) -> str:
    return f"{PAYLOAD_PREFIX}{intent_id.hex}"


def parse_payload(payload: str) -> uuid.UUID | None:
    if not payload.startswith(PAYLOAD_PREFIX):
        return None
    try:
        return uuid.UUID(hex=payload[len(PAYLOAD_PREFIX) :])
    except ValueError:
        return None


async def create_invoice(session: AsyncSession, user: User, plan_code: str) -> PaymentIntent:
    s = get_settings()
    plan = await session.get(Plan, plan_code)
    if plan is None or not plan.is_active or plan.price_stars <= 0:
        raise AppError("plan_not_purchasable", "Этот тариф нельзя купить.")
    now = datetime.now(UTC)
    recurring = s.payments_recurring and plan.period_days == 30
    reusable = await session.scalar(
        select(PaymentIntent).where(
            PaymentIntent.user_id == user.id,
            PaymentIntent.plan_code == plan.code,
            PaymentIntent.amount_stars == plan.price_stars,
            PaymentIntent.recurring == recurring,
            PaymentIntent.status == "pending",
            PaymentIntent.expires_at > now + timedelta(minutes=5),
            PaymentIntent.invoice_link.is_not(None),
        )
    )
    if reusable is not None:
        return reusable

    intent_id = uuid.uuid4()
    intent = PaymentIntent(
        id=intent_id,
        user_id=user.id,
        plan_code=plan.code,
        amount_stars=plan.price_stars,
        period_days=plan.period_days,
        recurring=recurring,
        payload=make_payload(intent_id),
        status="pending",
        expires_at=now + timedelta(minutes=s.payment_intent_ttl_minutes),
    )
    session.add(intent)
    await session.flush()
    title = f"{s.brand_name} {plan.title}"
    description = (plan.description or f"Подписка {plan.title}")[:255]
    link = await get_bot().create_invoice_link(
        title=title[:32],
        description=description,
        payload=intent.payload,
        currency="XTR",
        prices=[LabeledPrice(label=f"{plan.title} · {plan.period_days} дн.", amount=plan.price_stars)],
        subscription_period=STARS_SUBSCRIPTION_PERIOD if recurring else None,
    )
    intent.invoice_link = link
    return intent


@dataclass(slots=True)
class PreCheckoutVerdict:
    ok: bool
    error: str | None = None


async def validate_pre_checkout(
    session: AsyncSession, telegram_user_id: int, payload: str, currency: str, total_amount: int
) -> PreCheckoutVerdict:
    intent_id = parse_payload(payload)
    if intent_id is None:
        return PreCheckoutVerdict(False, "Неизвестный счёт.")
    intent = await session.get(PaymentIntent, intent_id)
    if intent is None:
        return PreCheckoutVerdict(False, "Счёт не найден.")
    user = await session.get(User, intent.user_id)
    if user is None or user.telegram_id != telegram_user_id:
        return PreCheckoutVerdict(False, "Счёт выставлен другому пользователю.")
    if user.is_blocked:
        return PreCheckoutVerdict(False, "Аккаунт заблокирован.")
    if currency != "XTR" or total_amount != intent.amount_stars:
        return PreCheckoutVerdict(False, "Сумма счёта изменилась. Откройте оплату заново.")
    if intent.status != "pending":
        return PreCheckoutVerdict(False, "Этот счёт уже оплачен.")
    if intent.expires_at <= datetime.now(UTC):
        return PreCheckoutVerdict(False, "Срок действия счёта истёк. Откройте оплату заново.")
    plan = await session.get(Plan, intent.plan_code)
    if plan is None or not plan.is_active:
        return PreCheckoutVerdict(False, "Тариф недоступен.")
    return PreCheckoutVerdict(True)


@dataclass(slots=True)
class PaymentOutcome:
    duplicate: bool
    payment: Payment | None
    subscription: Subscription | None
    renewal: bool = False
    gift: Gift | None = None


async def process_successful_payment(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    payload: str,
    currency: str,
    total_amount: int,
    telegram_payment_charge_id: str,
    provider_payment_charge_id: str | None,
    is_recurring: bool,
    is_first_recurring: bool,
    subscription_expiration_date: int | None,
    raw: dict,
) -> PaymentOutcome:
    intent_id = parse_payload(payload)
    intent = await session.get(PaymentIntent, intent_id, with_for_update=True) if intent_id else None
    user = await session.scalar(select(User).where(User.telegram_id == telegram_user_id))
    if user is None:
        raise NotFound("user_not_found")
    plan_code = intent.plan_code if intent else "pro"
    exp = datetime.fromtimestamp(subscription_expiration_date, UTC) if subscription_expiration_date else None

    # 1) idempotency: one row per Telegram charge id
    res = await session.execute(
        insert(Payment)
        .values(
            user_id=user.id,
            intent_id=intent.id if intent else None,
            plan_code=plan_code,
            amount_stars=total_amount,
            currency=currency,
            telegram_payment_charge_id=telegram_payment_charge_id,
            provider_payment_charge_id=provider_payment_charge_id,
            is_recurring=is_recurring,
            is_first_recurring=is_first_recurring,
            subscription_expiration_date=exp,
            status="paid",
            raw=raw,
        )
        .on_conflict_do_nothing(index_elements=[Payment.telegram_payment_charge_id])
        .returning(Payment.id)
    )
    payment_id = res.scalar_one_or_none()
    if payment_id is None:
        log.info("duplicate successful_payment ignored", extra={"ctx": {"charge": telegram_payment_charge_id}})
        return PaymentOutcome(duplicate=True, payment=None, subscription=None)
    payment = await session.get(Payment, payment_id)
    assert payment is not None

    if intent is None or currency != "XTR":
        # Money arrived but we cannot map it: keep the record, alert admins via error log.
        log.error("unmapped Stars payment", extra={"ctx": {"charge": telegram_payment_charge_id, "payload": payload}})
        return PaymentOutcome(duplicate=False, payment=payment, subscription=None)

    if intent.kind == "gift":
        gift = await gifts.on_paid(session, intent, payment)
        return PaymentOutcome(duplicate=False, payment=payment, subscription=None, gift=gift)

    renewal = is_recurring and not is_first_recurring and intent.status == "paid"
    is_first_purchase = await session.scalar(select(Payment.id).where(Payment.user_id == user.id, Payment.id != payment_id).limit(1)) is None
    if renewal:
        sub = await session.scalar(
            select(Subscription).where(Subscription.intent_id == intent.id).order_by(Subscription.id.desc()).with_for_update().limit(1)
        )
        if sub is None:
            sub = await subscriptions.grant(
                session,
                user.id,
                plan_code,
                intent.period_days,
                "payment",
                recurring=True,
                charge_id=telegram_payment_charge_id,
                intent_id=intent.id,
            )
        else:
            base = max(sub.expires_at, datetime.now(UTC))
            sub.expires_at = exp or (base + timedelta(days=intent.period_days))
            sub.status = "active"
            sub.expiry_notified = False
    else:
        sub = await subscriptions.grant(
            session,
            user.id,
            plan_code,
            intent.period_days,
            "payment",
            recurring=is_recurring,
            charge_id=telegram_payment_charge_id,
            intent_id=intent.id,
        )
        if exp is not None and sub.intent_id == intent.id:
            sub.expires_at = exp
        intent.status = "paid"
    payment.subscription_id = sub.id
    if is_first_purchase:
        await referrals.on_first_purchase(session, user.id)
    return PaymentOutcome(duplicate=False, payment=payment, subscription=sub, renewal=renewal)


async def mark_refunded(session: AsyncSession, telegram_payment_charge_id: str) -> Payment | None:
    payment = await session.scalar(select(Payment).where(Payment.telegram_payment_charge_id == telegram_payment_charge_id).with_for_update())
    if payment is None or payment.status == "refunded":
        return payment
    payment.status = "refunded"
    payment.refunded_at = datetime.now(UTC)
    await gifts.on_refund(session, payment)
    if payment.subscription_id:
        sub = await session.get(Subscription, payment.subscription_id, with_for_update=True)
        if sub is not None and sub.status == "active":
            sub.status = "refunded"
            sub.auto_renew = False
            sub.expires_at = datetime.now(UTC)
    return payment


async def refund(session: AsyncSession, payment_id: int) -> Payment:
    payment = await session.get(Payment, payment_id)
    if payment is None:
        raise NotFound("payment_not_found")
    if payment.status == "refunded":
        return payment
    user = await session.get(User, payment.user_id)
    assert user is not None
    await get_bot().refund_star_payment(user_id=user.telegram_id, telegram_payment_charge_id=payment.telegram_payment_charge_id)
    refunded = await mark_refunded(session, payment.telegram_payment_charge_id)
    assert refunded is not None
    return refunded


async def set_auto_renew(session: AsyncSession, user: User, subscription_id: int, enabled: bool) -> Subscription:
    sub = await session.get(Subscription, subscription_id, with_for_update=True)
    if sub is None or sub.user_id != user.id:
        raise NotFound("subscription_not_found")
    if not sub.is_recurring or not sub.telegram_charge_id:
        raise AppError("not_recurring", "Эта подписка не продлевается автоматически.")
    await get_bot().edit_user_star_subscription(
        user_id=user.telegram_id, telegram_payment_charge_id=sub.telegram_charge_id, is_canceled=not enabled
    )
    sub.auto_renew = enabled
    sub.canceled_at = None if enabled else datetime.now(UTC)
    return sub
