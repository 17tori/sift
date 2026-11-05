"""Runtime-editable settings stored in `app_settings` (trial, referral rewards, ...)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AppSetting

DEFAULTS: dict[str, Any] = {
    "trial": {"enabled": True, "days": 3, "plan": "pro", "auto_activate": False},
    "referral": {
        "enabled": True,
        "registration_reward_searches": 3,
        "first_purchase_reward_searches": 20,
        "invitee_bonus_searches": 2,
    },
    "basic_marketplaces": ["ebay", "aliexpress", "wildberries"],
    "gifts": {
        "enabled": True,
        "packs": [
            {"code": "g5", "searches": 5, "stars": 49},
            {"code": "g20", "searches": 20, "stars": 149},
            {"code": "g50", "searches": 50, "stars": 299},
        ],
    },
}


async def get_setting(session: AsyncSession, key: str) -> Any:
    row = await session.scalar(select(AppSetting.value).where(AppSetting.key == key))
    default = DEFAULTS.get(key)
    if row is None:
        return default
    if isinstance(default, dict) and isinstance(row, dict):
        return {**default, **row}
    return row


async def set_setting(session: AsyncSession, key: str, value: Any) -> None:
    stmt = insert(AppSetting).values(key=key, value=value)
    stmt = stmt.on_conflict_do_update(index_elements=[AppSetting.key], set_={"value": value})
    await session.execute(stmt)
