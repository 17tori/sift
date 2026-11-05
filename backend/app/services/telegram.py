"""Shared aiogram Bot instance for sending messages / Bot API calls from any process."""

from __future__ import annotations

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.core.config import get_settings

_bot: Bot | None = None


def get_bot() -> Bot:
    global _bot
    if _bot is None:
        s = get_settings()
        token = s.bot_token.get_secret_value()
        if not token:
            raise RuntimeError("BOT_TOKEN is not configured")
        _bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    return _bot


async def close_bot() -> None:
    global _bot
    if _bot is not None:
        await _bot.session.close()
    _bot = None
