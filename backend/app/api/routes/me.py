from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, get_session
from app.core import ratelimit
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.models import Favorite, Payment, SearchSession, Subscription, User
from app.schemas.common import (
    AutoRenewIn,
    MeOut,
    PaymentOut,
    PlanOut,
    PreferencesIn,
    QuotaOut,
    ReferralOut,
    SubscriptionOut,
    SupportIn,
    TrialOut,
)
from app.services import notifications, payments, referrals, subscriptions, trial
from app.services.app_settings import get_setting

router = APIRouter(prefix="/api/v1")


async def build_me(session: AsyncSession, user: User) -> MeOut:
    s = get_settings()
    ent = await subscriptions.entitlement(session, user)
    tcfg = await trial.trial_config(session)
    now = datetime.now(UTC)
    total = await session.scalar(select(func.count()).select_from(SearchSession).where(SearchSession.user_id == user.id))
    favs = await session.scalar(select(func.count()).select_from(Favorite).where(Favorite.user_id == user.id))
    return MeOut(
        id=user.id,
        telegram_id=user.telegram_id,
        username=user.username,
        first_name=user.first_name,
        photo_url=user.photo_url,
        language_code=user.language_code,
        created_at=user.created_at,
        is_admin=user.telegram_id in s.admin_telegram_ids,
        plan=PlanOut.model_validate(ent.plan),
        subscription=SubscriptionOut.model_validate(ent.subscription) if ent.subscription else None,
        quota=QuotaOut(
            used=ent.used, limit=ent.limit, window=ent.window, resets_at=ent.window_resets_at, bonus=ent.bonus, remaining=ent.remaining
        ),
        trial=TrialOut(
            available=await trial.is_available(session, user),
            active=bool(ent.is_trial and user.trial_ends_at and user.trial_ends_at > now),
            used=user.trial_used,
            ends_at=user.trial_ends_at,
            days=int(tcfg.get("days", 3)),
        ),
        preferences=user.preferences or {},
        total_searches=int(total or 0),
        favorites_count=int(favs or 0),
    )


@router.get("/me", response_model=MeOut)
async def me(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> MeOut:
    return await build_me(session, user)


@router.patch("/me/preferences", response_model=MeOut)
async def update_preferences(body: PreferencesIn, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> MeOut:
    prefs = dict(user.preferences or {})
    prefs.update(body.model_dump(exclude_none=True))
    user.preferences = prefs
    await session.flush()
    return await build_me(session, user)


@router.post("/trial/activate", response_model=MeOut)
async def activate_trial(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> MeOut:
    await ratelimit.hit(f"trial:{user.id}", limit=5, window_seconds=3600)
    await trial.activate(session, user)
    await session.flush()
    return await build_me(session, user)


@router.get("/subscriptions", response_model=list[SubscriptionOut])
async def list_subscriptions(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> list[SubscriptionOut]:
    rows = (
        await session.scalars(select(Subscription).where(Subscription.user_id == user.id).order_by(Subscription.created_at.desc()).limit(50))
    ).all()
    return [SubscriptionOut.model_validate(r) for r in rows]


@router.post("/subscriptions/{subscription_id}/auto-renew", response_model=SubscriptionOut)
async def auto_renew(
    subscription_id: int, body: AutoRenewIn, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> SubscriptionOut:
    await ratelimit.hit(f"renew:{user.id}", limit=10, window_seconds=3600)
    sub = await payments.set_auto_renew(session, user, subscription_id, body.enabled)
    return SubscriptionOut.model_validate(sub)


@router.get("/payments", response_model=list[PaymentOut])
async def list_payments(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> list[PaymentOut]:
    rows = (await session.scalars(select(Payment).where(Payment.user_id == user.id).order_by(Payment.created_at.desc()).limit(100))).all()
    return [PaymentOut.model_validate(r) for r in rows]


@router.get("/referrals", response_model=ReferralOut)
async def referral_info(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> ReferralOut:
    s = get_settings()
    cfg = await get_setting(session, "referral")
    st = await referrals.stats(session, user.id)
    link = f"https://t.me/{s.bot_username}?start=ref_{user.referral_code}" if s.bot_username else ""
    return ReferralOut(
        code=user.referral_code,
        link=link,
        **st,
        reward_registration=int(cfg.get("registration_reward_searches", 0)),
        reward_first_purchase=int(cfg.get("first_purchase_reward_searches", 0)),
        invitee_bonus=int(cfg.get("invitee_bonus_searches", 0)),
    )


@router.post("/support", status_code=202)
async def support(body: SupportIn, user: User = Depends(current_user)) -> dict[str, str]:
    await ratelimit.hit(f"support:{user.id}", limit=5, window_seconds=3600)
    s = get_settings()
    if not s.admin_telegram_ids:
        raise AppError("support_unavailable", "Поддержка временно недоступна.", status_code=503)
    from html import escape

    text = (
        f"🆘 <b>Поддержка</b>\nОт: {escape(user.first_name)} (@{escape(user.username or '—')}, "
        f"id <code>{user.telegram_id}</code>)\n\n{escape(body.message)}"
    )
    delivered = 0
    for admin_id in s.admin_telegram_ids:
        try:
            await notifications.get_bot().send_message(admin_id, text)
            delivered += 1
        except Exception:  # noqa: BLE001
            continue
    if not delivered:
        raise AppError("support_unavailable", "Не удалось доставить сообщение. Попробуйте позже.", status_code=503)
    return {"status": "sent"}
