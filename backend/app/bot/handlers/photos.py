"""Photo sent straight to the bot -> same search pipeline as the Mini App."""

from __future__ import annotations

import io

from aiogram import Bot, F, Router
from aiogram.types import Message

from app.bot import keyboards
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.models import User
from app.db.session import session_scope
from app.services import search_service

router = Router(name="photos")


@router.message(F.photo | (F.document & F.document.mime_type.in_({"image/jpeg", "image/png", "image/webp"})))
async def on_photo(message: Message, bot: Bot, user: User) -> None:
    s = get_settings()
    if message.photo:
        file_id, size = message.photo[-1].file_id, message.photo[-1].file_size or 0
    else:
        assert message.document is not None
        file_id, size = message.document.file_id, message.document.file_size or 0
    if size > s.upload_max_bytes:
        await message.answer("Файл слишком большой. Максимум 10 МБ.")
        return
    buf = io.BytesIO()
    await bot.download(file_id, destination=buf)
    try:
        async with session_scope() as session:
            search, is_new = await search_service.create_search(session, user, buf.getvalue())
    except AppError as e:
        await message.answer(e.message, reply_markup=keyboards.open_app("Тарифы", "subscription") if e.code == "quota_exceeded" else None)
        return
    if is_new:
        search_service.enqueue(search)
    await message.answer(
        "Фото получено. Анализирую вещь и ищу похожие предложения на маркетплейсах.",
        reply_markup=keyboards.open_app("Смотреть результаты", f"search/{search.id}"),
    )
