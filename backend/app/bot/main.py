"""Telegram bot entrypoint (polling or webhook)."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, MenuButtonWebApp

from app.bot.handlers import commands, payments, photos
from app.bot.keyboards import webapp
from app.bot.middlewares import UserMiddleware
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.services.telegram import get_bot

log = logging.getLogger("bot")

COMMANDS = [
    BotCommand(command="start", description="Начать"),
    BotCommand(command="app", description="Открыть приложение"),
    BotCommand(command="profile", description="Профиль"),
    BotCommand(command="subscription", description="Подписка"),
    BotCommand(command="history", description="История поисков"),
    BotCommand(command="help", description="Помощь"),
    BotCommand(command="support", description="Поддержка"),
]


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    mw = UserMiddleware()
    dp.message.outer_middleware(mw)
    dp.callback_query.outer_middleware(mw)
    dp.include_routers(payments.router, commands.router, photos.router)
    return dp


async def setup_bot(bot: Bot) -> None:
    s = get_settings()
    await bot.set_my_commands(COMMANDS)
    await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text=s.brand_name, web_app=webapp()))


async def run_polling() -> None:
    bot = get_bot()
    dp = build_dispatcher()
    try:
        await setup_bot(bot)
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


def run_webhook() -> None:
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
    from aiohttp import web

    s = get_settings()
    bot = get_bot()
    dp = build_dispatcher()
    secret = s.bot_webhook_secret.get_secret_value()

    async def on_startup(_: web.Application) -> None:
        await setup_bot(bot)
        await bot.set_webhook(
            f"{s.public_base_url.rstrip('/')}{s.bot_webhook_path}",
            secret_token=secret,
            allowed_updates=dp.resolve_used_update_types(),
            drop_pending_updates=False,
        )

    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=secret).register(app, path=s.bot_webhook_path)
    setup_application(app, dp, bot=bot)
    app.on_startup.append(on_startup)
    web.run_app(app, host="0.0.0.0", port=8081)  # noqa: S104 - internal docker network only


def main() -> None:
    setup_logging("bot")
    if get_settings().bot_mode == "webhook":
        run_webhook()
    else:
        asyncio.run(run_polling())


if __name__ == "__main__":
    main()
