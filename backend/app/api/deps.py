from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import ratelimit
from app.core.config import Settings, get_settings
from app.core.errors import AppError, Forbidden
from app.core.security import InitDataError, validate_init_data
from app.db.models import User
from app.db.session import sessionmaker
from app.services.users import TelegramIdentity, ensure_not_blocked, get_or_create_user


async def get_session() -> AsyncIterator[AsyncSession]:
    async with sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


async def current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> User:
    if not authorization or not authorization.startswith("tma "):
        raise AppError("unauthorized", "Откройте приложение из Telegram.", status_code=401)
    try:
        data = validate_init_data(authorization[4:], settings.bot_token.get_secret_value(), settings.init_data_max_age_seconds)
    except InitDataError as e:
        raise AppError("unauthorized", "Сессия Telegram недействительна. Перезапустите приложение.", status_code=401) from e
    await ratelimit.hit(f"u:{data.user.id}", limit=180, window_seconds=60)
    user = await session.scalar(select(User).where(User.telegram_id == data.user.id))
    stale = user is None or user.last_seen_at < datetime.now(UTC) - timedelta(minutes=5)
    if user is None or stale or user.username != data.user.username:
        u = data.user
        user, _ = await get_or_create_user(
            session,
            TelegramIdentity(u.id, u.username, u.first_name, u.last_name, u.language_code, u.is_premium, u.photo_url),
            start_param=data.start_param,
        )
    ensure_not_blocked(user)
    request.state.user_id = user.id
    return user


async def admin_user(user: User = Depends(current_user), settings: Settings = Depends(get_settings)) -> User:
    if user.telegram_id not in settings.admin_telegram_ids:
        raise Forbidden("admin_only", "Недостаточно прав.")
    return user
