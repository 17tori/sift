from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery, TelegramObject

from app.db.session import session_scope
from app.services.users import TelegramIdentity, get_or_create_user


class UserMiddleware(BaseMiddleware):
    """Registers the sender, loads the user and rejects blocked accounts.

    pre_checkout_query is passed through untouched (it must be answered within 10 s and
    is validated against the payment intent instead).
    """

    async def __call__(
        self, handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]], event: TelegramObject, data: dict[str, Any]
    ) -> Any:
        if isinstance(event, PreCheckoutQuery):
            return await handler(event, data)
        tg = getattr(event, "from_user", None)
        if tg is None or tg.is_bot:
            return None
        start_param = None
        if isinstance(event, Message) and event.text and event.text.startswith("/start "):
            start_param = event.text.split(maxsplit=1)[1].strip()
        async with session_scope() as s:
            user, created = await get_or_create_user(
                s,
                TelegramIdentity(tg.id, tg.username, tg.first_name or "", tg.last_name, tg.language_code, bool(tg.is_premium)),
                start_param=start_param,
                from_bot=True,
            )
        if user.is_blocked:
            if isinstance(event, Message):
                await event.answer("Аккаунт заблокирован. Если это ошибка, напишите в поддержку.")
            elif isinstance(event, CallbackQuery):
                await event.answer("Аккаунт заблокирован.", show_alert=True)
            return None
        data["user"] = user
        data["user_created"] = created
        return await handler(event, data)
