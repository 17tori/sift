"""Shared finds: postcard + deep link. Opening the link as a new user attributes the referral to the sharer."""

from __future__ import annotations

import asyncio
import logging
import secrets
from decimal import Decimal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultPhoto
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import Forbidden, NotFound
from app.db.models import Product, SearchResult, SearchSession, Share, User
from app.marketplace import registry
from app.services import postcard
from app.services.remote_images import fetch_one
from app.services.storage import get_storage
from app.services.telegram import get_bot

log = logging.getLogger(__name__)
CURRENCY_SIGN = {"RUB": "₽", "USD": "$", "EUR": "€", "GBP": "£", "CNY": "¥", "KZT": "₸"}


def format_price(price: Decimal | None, currency: str | None) -> str | None:
    if price is None:
        return None
    whole = f"{price:,.0f}" if price == price.to_integral_value() or price >= 1000 else f"{price:,.2f}"
    whole = whole.replace(",", " ")
    sign = CURRENCY_SIGN.get(currency or "", currency or "")
    return f"{sign}{whole}" if sign in ("$", "£", "€") else f"{whole} {sign}".strip()


def app_link(start: str) -> str:
    s = get_settings()
    return f"https://t.me/{s.bot_username}/app?startapp={start}" if s.bot_username else s.webapp_url


def card_url(token: str) -> str:
    return get_settings().public_base_url.rstrip("/") + f"/api/v1/shares/{token}/card.jpg"


def share_text(product: Product, sharer: User) -> str:
    price = format_price(product.price, product.currency)
    tail = f" · {price}" if price else ""
    return f"{sharer.first_name} делится находкой из SIFT: {product.title[:90]}{tail}"


async def create(session: AsyncSession, user: User, product_id: int, search_id=None) -> tuple[Share, Product]:  # type: ignore[no-untyped-def]
    product = await session.get(Product, product_id)
    if product is None:
        raise NotFound("product_not_found")
    owned = await session.scalar(
        select(SearchResult.id)
        .join(SearchSession, SearchSession.id == SearchResult.search_id)
        .where(SearchSession.user_id == user.id, SearchResult.product_id == product_id)
        .limit(1)
    )
    if owned is None:
        raise Forbidden("not_your_result")
    existing = await session.scalar(select(Share).where(Share.user_id == user.id, Share.product_id == product_id))
    if existing is not None and existing.card_key:
        return existing, product
    share = existing or Share(token=secrets.token_urlsafe(9)[:12], user_id=user.id, product_id=product_id, search_id=search_id)
    if existing is None:
        session.add(share)
    photo = await fetch_one(product.image_url, side=1080) if product.image_url else None
    if photo is None and product.thumb_key:
        try:
            photo = await get_storage().get(product.thumb_key)
        except (OSError, ValueError):
            photo = None
    provider = registry.get(product.source)
    data = postcard.CardData(
        title=product.title,
        marketplace=provider.name if provider else product.source,
        price=format_price(product.price, product.currency),
        number=product.id % 10000,
        photo=photo,
        footer=f"t.me/{get_settings().bot_username}" if get_settings().bot_username else "SIFT",
    )
    jpeg = await asyncio.to_thread(postcard.render, data)
    share.card_key = await get_storage().put(jpeg, "jpg", "shares")
    await session.flush()
    return share, product


async def prepare_message(user: User, share: Share, product: Product) -> str | None:
    """Telegram prepared inline message (photo + button) for WebApp.shareMessage(); None if unavailable."""
    try:
        url = card_url(share.token)
        res = await get_bot().save_prepared_inline_message(
            user_id=user.telegram_id,
            result=InlineQueryResultPhoto(
                id=share.token,
                photo_url=url,
                thumbnail_url=url,
                caption=share_text(product, user),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[[InlineKeyboardButton(text="Открыть находку", url=app_link(f"f_{share.token}"))]]
                ),
            ),
            allow_user_chats=True,
            allow_group_chats=True,
            allow_channel_chats=True,
        )
        return res.id
    except Exception as e:  # noqa: BLE001 - sharing falls back to a t.me/share link
        log.warning("prepared message failed: %s", e)
        return None


async def open_share(session: AsyncSession, token: str) -> tuple[Share, Product, User]:
    share = await session.get(Share, token)
    if share is None:
        raise NotFound("share_not_found")
    product = await session.get(Product, share.product_id)
    sharer = await session.get(User, share.user_id)
    if product is None or sharer is None:
        raise NotFound("share_not_found")
    await session.execute(update(Share).where(Share.token == token).values(opens=Share.opens + 1))
    return share, product, sharer


async def referral_code_for(session: AsyncSession, token: str) -> str | None:
    """Start param f_<token>: the sharer's referral code, so a new user opening the find counts as invited."""
    return await session.scalar(select(User.referral_code).join(Share, Share.user_id == User.id).where(Share.token == token))
