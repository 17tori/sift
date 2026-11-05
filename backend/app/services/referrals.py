"""Referral program: attribution at registration, rewards with DB-level idempotency."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Referral, ReferralReward, User
from app.services.app_settings import get_setting

log = logging.getLogger(__name__)


async def attach_referrer(session: AsyncSession, new_user: User, code: str) -> bool:
    """Only called for a user created in this very transaction (no retroactive referrals)."""
    cfg = await get_setting(session, "referral")
    if not cfg.get("enabled", True):
        return False
    referrer = await session.scalar(select(User).where(User.referral_code == code))
    if referrer is None or referrer.id == new_user.id or referrer.is_blocked:
        return False  # unknown code or self-referral
    if referrer.referred_by_id == new_user.id:
        return False  # A->B->A loop
    res = await session.execute(
        insert(Referral)
        .values(referrer_id=referrer.id, referred_id=new_user.id)
        .on_conflict_do_nothing(index_elements=[Referral.referred_id])
        .returning(Referral.id)
    )
    referral_id = res.scalar_one_or_none()
    if referral_id is None:
        return False
    new_user.referred_by_id = referrer.id
    await _reward(session, referral_id, referrer.id, "registration", int(cfg.get("registration_reward_searches", 0)))
    await _reward(session, referral_id, new_user.id, "invitee_bonus", int(cfg.get("invitee_bonus_searches", 0)))
    return True


async def on_first_purchase(session: AsyncSession, user_id: int) -> None:
    ref = await session.scalar(select(Referral).where(Referral.referred_id == user_id).with_for_update())
    if ref is None or ref.first_purchase_at is not None:
        return
    ref.first_purchase_at = datetime.now(UTC)
    cfg = await get_setting(session, "referral")
    if cfg.get("enabled", True):
        await _reward(session, ref.id, ref.referrer_id, "first_purchase", int(cfg.get("first_purchase_reward_searches", 0)))


async def _reward(session: AsyncSession, referral_id: int, beneficiary_id: int, event: str, amount: int) -> None:
    if amount <= 0:
        return
    res = await session.execute(
        insert(ReferralReward)
        .values(referral_id=referral_id, beneficiary_id=beneficiary_id, event=event, reward_type="searches", amount=amount)
        .on_conflict_do_nothing(constraint="uq_referral_rewards_referral_event")
        .returning(ReferralReward.id)
    )
    if res.scalar_one_or_none() is None:
        return  # already granted -> no double reward
    await session.execute(update(User).where(User.id == beneficiary_id).values(bonus_searches=User.bonus_searches + amount))


async def stats(session: AsyncSession, user_id: int) -> dict[str, int]:
    invited = await session.scalar(select(func.count()).select_from(Referral).where(Referral.referrer_id == user_id))
    purchased = await session.scalar(
        select(func.count()).select_from(Referral).where(Referral.referrer_id == user_id, Referral.first_purchase_at.is_not(None))
    )
    earned = await session.scalar(
        select(func.coalesce(func.sum(ReferralReward.amount), 0)).where(
            ReferralReward.beneficiary_id == user_id, ReferralReward.event != "invitee_bonus"
        )
    )
    return {"invited": int(invited or 0), "purchased": int(purchased or 0), "earned_searches": int(earned or 0)}
