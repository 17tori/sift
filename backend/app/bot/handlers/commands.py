from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from app.bot import keyboards, texts
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.models import Plan, SearchSession, User
from app.db.session import session_scope
from app.services import payments, referrals, subscriptions, trial

router = Router(name="commands")


@router.message(CommandStart())
async def cmd_start(message: Message, user: User, user_created: bool) -> None:
    started = False
    async with session_scope() as s:
        cfg = await trial.trial_config(s)
        if user_created and cfg.get("auto_activate") and await trial.is_available(s, user):
            await trial.activate(s, user)
            started = True
        available = (not started) and await trial.is_available(s, user)
    await message.answer(texts.welcome(user.first_name, available, int(cfg.get("days", 3)), started), reply_markup=keyboards.start_kb(available))


@router.message(Command("app"))
async def cmd_app(message: Message) -> None:
    await message.answer("Приложение открывается здесь:", reply_markup=keyboards.open_app())


@router.message(Command("help"))
@router.callback_query(F.data == "help")
async def cmd_help(event: Message | CallbackQuery) -> None:
    msg = event.message if isinstance(event, CallbackQuery) else event
    if isinstance(event, CallbackQuery):
        await event.answer()
    if msg is not None:
        await msg.answer(texts.HELP, reply_markup=keyboards.open_app())


@router.message(Command("profile"))
async def cmd_profile(message: Message, user: User) -> None:
    async with session_scope() as s:
        ent = await subscriptions.entitlement(s, user)
        ref = await referrals.stats(s, user.id)
    s_ = get_settings()
    plan = ent.plan.title + (" (пробный)" if ent.is_trial else "")
    until = f"\nДействует до: {ent.subscription.expires_at:%d.%m.%Y %H:%M} UTC" if ent.subscription else ""
    window = "сегодня" if ent.window == "day" else "в этом периоде"
    link = f"https://t.me/{s_.bot_username}?start=ref_{user.referral_code}" if s_.bot_username else user.referral_code
    await message.answer(
        f"<b>Профиль</b>\n\nID: <code>{user.telegram_id}</code>\nС нами с {user.created_at:%d.%m.%Y}\n\n"
        f"Тариф: <b>{escape(plan)}</b>{until}\n"
        f"Поисков {window}: {ent.used} из {ent.limit}"
        + (f" (+{ent.bonus} бонусных)" if ent.bonus else "")
        + f"\n\nПриглашено друзей: {ref['invited']}\nРеферальная ссылка: {link}",
        reply_markup=keyboards.open_app("Открыть профиль", "profile"),
    )


async def _plans_message(user: User) -> tuple[str, InlineKeyboardMarkup]:
    async with session_scope() as s:
        plans = (await s.scalars(select(Plan).where(Plan.is_active.is_(True), Plan.price_stars > 0).order_by(Plan.sort_order))).all()
        ent = await subscriptions.entitlement(s, user)
    lines = [
        "<b>Подписка</b>",
        "",
        f"Сейчас: <b>{escape(ent.plan.title)}</b>" + (f" до {ent.subscription.expires_at:%d.%m.%Y}" if ent.subscription else ""),
    ]
    if ent.subscription and ent.subscription.is_recurring:
        lines.append("Автопродление: " + ("включено" if ent.subscription.auto_renew else "выключено"))
    lines.append("")
    for p in plans:
        per = "в день" if p.limit_window == "day" else "в месяц"
        lines.append(f"<b>{escape(p.title)}</b> · {p.price_stars} ⭐ / {p.period_days} дн. · {p.search_limit} поисков {per}")
    lines += ["", "Оплата в Telegram Stars. Подписку можно отменить в любой момент."]
    auto = ent.subscription.id if ent.subscription and ent.subscription.auto_renew else None
    return "\n".join(lines), keyboards.plans_kb([(p.code, p.title, p.price_stars) for p in plans], auto)


@router.message(Command("subscription"))
@router.callback_query(F.data == "plans")
async def cmd_subscription(event: Message | CallbackQuery, user: User) -> None:
    text, kb = await _plans_message(user)
    if isinstance(event, CallbackQuery):
        await event.answer()
        if event.message:
            await event.message.answer(text, reply_markup=kb)
    else:
        await event.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("buy:"))
async def cb_buy(cb: CallbackQuery, user: User) -> None:
    code = (cb.data or "").split(":", 1)[1]
    try:
        async with session_scope() as s:
            intent = await payments.create_invoice(s, user, code)
    except AppError as e:
        await cb.answer(e.message, show_alert=True)
        return
    await cb.answer()
    if cb.message:
        await cb.message.answer(
            f"Счёт на <b>{intent.amount_stars} ⭐</b>" + (" с ежемесячным автопродлением" if intent.recurring else ""),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=f"Оплатить {intent.amount_stars} ⭐", url=intent.invoice_link)]]
            ),
        )


@router.callback_query(F.data.startswith("renew:off:"))
async def cb_renew_off(cb: CallbackQuery, user: User) -> None:
    sub_id = int((cb.data or "0").rsplit(":", 1)[1])
    try:
        async with session_scope() as s:
            sub = await payments.set_auto_renew(s, user, sub_id, False)
    except AppError as e:
        await cb.answer(e.message, show_alert=True)
        return
    await cb.answer("Автопродление отключено")
    if cb.message:
        await cb.message.answer(f"Автопродление отключено. Доступ сохранится до {sub.expires_at:%d.%m.%Y}.")


@router.callback_query(F.data == "trial:activate")
async def cb_trial(cb: CallbackQuery, user: User) -> None:
    try:
        async with session_scope() as s:
            sub = await trial.activate(s, user)
    except AppError as e:
        await cb.answer(e.message, show_alert=True)
        return
    await cb.answer("PRO активирован")
    if cb.message:
        await cb.message.answer(
            f"🎁 Пробный PRO активен до <b>{sub.expires_at:%d.%m.%Y %H:%M} UTC</b>.\n"
            "За 24 часа до окончания я напомню. Автоматического списания не будет.",
            reply_markup=keyboards.open_app(),
        )


@router.message(Command("history"))
async def cmd_history(message: Message, user: User) -> None:
    async with session_scope() as s:
        rows = (
            await s.scalars(
                select(SearchSession)
                .where(SearchSession.user_id == user.id, SearchSession.hidden.is_(False))
                .order_by(SearchSession.created_at.desc())
                .limit(5)
            )
        ).all()
    if not rows:
        await message.answer("История пока пуста. Пришли фото или открой приложение.", reply_markup=keyboards.open_app())
        return
    lines = ["<b>Последние поиски</b>", ""]
    for r in rows:
        title = (r.analysis or {}).get("title_ru") or (r.analysis or {}).get("title_en") or "Фото"
        lines.append(f"• {r.created_at:%d.%m %H:%M} — {escape(title)} · {texts.STATUS_RU.get(r.status, r.status)} · {r.results_count} шт.")
    await message.answer("\n".join(lines), reply_markup=keyboards.open_app("Вся история", "history"))


@router.message(Command("support"))
async def cmd_support(message: Message) -> None:
    s = get_settings()
    contact = []
    if s.brand_support_username:
        contact.append(f"Telegram: @{escape(s.brand_support_username)}")
    if s.brand_support_email:
        contact.append(f"Почта: {escape(s.brand_support_email)}")
    await message.answer(
        "<b>Поддержка</b>\n\nОпишите проблему в приложении (раздел «Поддержка»), сообщение придёт команде."
        + ("\n\n" + "\n".join(contact) if contact else ""),
        reply_markup=keyboards.open_app("Написать в поддержку", "support"),
    )
