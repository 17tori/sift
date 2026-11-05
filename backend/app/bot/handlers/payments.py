from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import Message, PreCheckoutQuery

from app.bot import keyboards
from app.db.session import session_scope
from app.services import gifts, payments

router = Router(name="payments")
log = logging.getLogger(__name__)


@router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery) -> None:
    try:
        async with session_scope() as s:
            verdict = await payments.validate_pre_checkout(s, query.from_user.id, query.invoice_payload, query.currency, query.total_amount)
    except Exception:
        log.exception("pre_checkout validation crashed")
        await query.answer(ok=False, error_message="Не удалось проверить счёт. Попробуйте ещё раз.")
        return
    if verdict.ok:
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message=verdict.error or "Оплата недоступна.")


@router.message(F.successful_payment)
async def on_successful_payment(message: Message) -> None:
    sp = message.successful_payment
    assert sp is not None and message.from_user is not None
    async with session_scope() as s:
        outcome = await payments.process_successful_payment(
            s,
            telegram_user_id=message.from_user.id,
            payload=sp.invoice_payload,
            currency=sp.currency,
            total_amount=sp.total_amount,
            telegram_payment_charge_id=sp.telegram_payment_charge_id,
            provider_payment_charge_id=sp.provider_payment_charge_id,
            is_recurring=bool(sp.is_recurring),
            is_first_recurring=bool(sp.is_first_recurring),
            subscription_expiration_date=sp.subscription_expiration_date,
            raw=sp.model_dump(mode="json", exclude_none=True),
        )
        sub = outcome.subscription
        plan_code, expires = (sub.plan_code, sub.expires_at) if sub else (None, None)
        gift = outcome.gift
        gift_code, gift_n = (gift.code, gift.searches) if gift else (None, 0)
    if outcome.duplicate:
        return
    if gift_code:
        link = gifts.gift_link(gift_code)
        await message.answer(
            f"🎁 Подарок готов: <b>{gift_n} поисков</b>.\nПерешлите ссылку другу, она сработает один раз:\n{link}",
            reply_markup=keyboards.share_link("Отправить другу", link, f"Дарю тебе {gift_n} поисков по фото в SIFT"),
        )
        return
    if sub is None:
        await message.answer("Оплата получена, но не удалось сопоставить её с тарифом. Мы уже разбираемся и свяжемся с вами.")
        return
    verb = "продлена" if outcome.renewal else "активирована"
    await message.answer(
        f"✓ Подписка <b>{plan_code.upper()}</b> {verb} до <b>{expires:%d.%m.%Y}</b>. Спасибо!",
        reply_markup=keyboards.open_app("Открыть приложение"),
    )


@router.message(F.refunded_payment)
async def on_refunded(message: Message) -> None:
    rp = message.refunded_payment
    assert rp is not None
    async with session_scope() as s:
        await payments.mark_refunded(s, rp.telegram_payment_charge_id)
    await message.answer(f"Возврат {rp.total_amount} ⭐ выполнен. Подписка отключена.")
