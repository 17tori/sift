from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.core.config import get_settings


def webapp(path: str = "") -> WebAppInfo:
    return WebAppInfo(url=get_settings().webapp_url.rstrip("/") + "/" + path.lstrip("/"))


def open_app(text: str = "Открыть приложение", path: str = "") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, web_app=webapp(path))]])


def start_kb(trial_available: bool) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="✦ Открыть приложение", web_app=webapp())]]
    if trial_available:
        rows.append([InlineKeyboardButton(text="🎁 Активировать пробный PRO", callback_data="trial:activate")])
    rows.append([InlineKeyboardButton(text="Тарифы", callback_data="plans"), InlineKeyboardButton(text="Помощь", callback_data="help")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def plans_kb(plans: list[tuple[str, str, int]], auto_renew_sub: int | None) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"{title} · {price} ⭐", callback_data=f"buy:{code}")] for code, title, price in plans]
    if auto_renew_sub:
        rows.append([InlineKeyboardButton(text="Отключить автопродление", callback_data=f"renew:off:{auto_renew_sub}")])
    rows.append([InlineKeyboardButton(text="Открыть в приложении", web_app=webapp("subscription"))])
    return InlineKeyboardMarkup(inline_keyboard=rows)
