"""Outbound bot messages. Handles users who blocked the bot gracefully."""

from __future__ import annotations

import logging

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.core.config import get_settings
from app.db.session import session_scope
from app.services.telegram import get_bot
from app.services.users import mark_bot_unreachable

log = logging.getLogger(__name__)


def app_button(text: str, path: str = "") -> InlineKeyboardMarkup:
    url = get_settings().webapp_url.rstrip("/") + "/" + path.lstrip("/")
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, web_app=WebAppInfo(url=url))]])


async def send(user_id: int, telegram_id: int, text: str, button: tuple[str, str] | None = None) -> bool:
    try:
        await get_bot().send_message(telegram_id, text, reply_markup=app_button(*button) if button else None, disable_web_page_preview=True)
        return True
    except TelegramForbiddenError:
        async with session_scope() as s:
            await mark_bot_unreachable(s, user_id)
        return False
    except TelegramRetryAfter as e:
        log.warning("telegram flood control, retry after %s", e.retry_after)
        return False
    except TelegramBadRequest as e:
        log.warning("telegram bad request for %s: %s", telegram_id, e)
        return False
