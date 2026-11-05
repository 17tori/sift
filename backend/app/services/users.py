from __future__ import annotations

import logging
import secrets
import string
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Forbidden
from app.db.models import User
from app.services import referrals

log = logging.getLogger(__name__)
_ALPHABET = string.ascii_uppercase + string.digits


def new_referral_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(8))


@dataclass(slots=True)
class TelegramIdentity:
    telegram_id: int
    username: str | None
    first_name: str
    last_name: str | None
    language_code: str | None
    is_premium: bool = False
    photo_url: str | None = None


def parse_referral_payload(start_param: str | None) -> str | None:
    if not start_param:
        return None
    if start_param.startswith("ref_"):
        code = start_param[4:].upper()
        if 4 <= len(code) <= 16 and code.isalnum():
            return code
    return None


async def get_or_create_user(
    session: AsyncSession, ident: TelegramIdentity, start_param: str | None = None, from_bot: bool = False
) -> tuple[User, bool]:
    """Registers a Telegram user idempotently. Returns (user, created).

    Concurrency-safe: INSERT ... ON CONFLICT DO NOTHING on the unique telegram_id.
    """
    now = datetime.now(UTC)
    for _ in range(3):
        stmt = (
            insert(User)
            .values(
                telegram_id=ident.telegram_id,
                username=ident.username,
                first_name=ident.first_name[:128],
                last_name=(ident.last_name or None),
                language_code=ident.language_code,
                is_premium=ident.is_premium,
                photo_url=ident.photo_url,
                referral_code=new_referral_code(),
                bot_started=from_bot,
                preferences={},
            )
            .on_conflict_do_nothing(index_elements=[User.telegram_id])
            .returning(User.id)
        )
        try:
            async with session.begin_nested():
                new_id = await session.scalar(stmt)
        except IntegrityError:  # referral_code collision (astronomically rare) -> retry
            continue
        break
    else:  # pragma: no cover
        raise RuntimeError("could not allocate referral code")

    created = new_id is not None
    user = await session.scalar(select(User).where(User.telegram_id == ident.telegram_id).with_for_update())
    assert user is not None
    if not created:
        user.username = ident.username
        user.first_name = ident.first_name[:128]
        user.last_name = ident.last_name
        user.language_code = ident.language_code
        user.is_premium = ident.is_premium
        if ident.photo_url:
            user.photo_url = ident.photo_url
        user.last_seen_at = now
        if from_bot:
            user.bot_started = True
    else:
        code = parse_referral_payload(start_param)
        if code:
            await referrals.attach_referrer(session, user, code)
        log.info("user registered", extra={"ctx": {"user_id": user.id, "tg": user.telegram_id}})
    return user, created


def ensure_not_blocked(user: User) -> None:
    if user.is_blocked:
        raise Forbidden("user_blocked", "Аккаунт заблокирован. Обратитесь в поддержку.")


async def mark_bot_unreachable(session: AsyncSession, user_id: int) -> None:
    await session.execute(update(User).where(User.id == user_id).values(bot_started=False))
