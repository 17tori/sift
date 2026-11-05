from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

import orjson
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import admin_user, get_session
from app.api.routes.me import build_me
from app.core.config import get_settings
from app.core.errors import AppError, NotFound
from app.core.logging import ERRORS_KEY
from app.core.redis import get_redis
from app.db.models import AdminLog, MarketplaceStatus, Payment, Plan, SearchSession, Subscription, User
from app.marketplace import registry
from app.schemas.common import MeOut, PaymentOut, PlanOut, SubscriptionOut
from app.search.pipeline import AI_STATS_KEY
from app.services import admin_stats, payments, subscriptions
from app.services.app_settings import DEFAULTS, get_setting, set_setting

router = APIRouter(prefix="/api/v1/admin")


async def _log(session: AsyncSession, admin: User, action: str, target: str | None, payload: dict[str, Any]) -> None:
    session.add(
        AdminLog(admin_telegram_id=admin.telegram_id, action=action, target=target, payload=orjson.loads(orjson.dumps(payload, default=str)))
    )


@router.get("/overview")
async def overview(_: User = Depends(admin_user), session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    return await admin_stats.overview(session)


@router.get("/stats")
async def stats(days: int = Query(30), _: User = Depends(admin_user), session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    if days not in (7, 30, 90):
        raise AppError("bad_period", "Период: 7, 30 или 90 дней.")
    return await admin_stats.timeseries(session, days)


class AdminUserRow(BaseModel):
    id: int
    telegram_id: int
    username: str | None
    first_name: str
    created_at: datetime
    last_seen_at: datetime
    is_blocked: bool
    bonus_searches: int
    plan: str
    searches: int


@router.get("/users", response_model=list[AdminUserRow])
async def users(
    q: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, le=200),
    _: User = Depends(admin_user),
    session: AsyncSession = Depends(get_session),
) -> list[AdminUserRow]:
    stmt = select(User)
    if q:
        conds = [User.username.ilike(f"%{q.lstrip('@')}%"), User.first_name.ilike(f"%{q}%")]
        if q.isdigit():
            conds.append(User.telegram_id == int(q))
        stmt = stmt.where(or_(*conds))
    rows = (await session.scalars(stmt.order_by(User.created_at.desc()).offset(offset).limit(limit))).all()
    counts = (
        dict(
            (
                await session.execute(
                    select(SearchSession.user_id, func.count())
                    .where(SearchSession.user_id.in_([u.id for u in rows]))
                    .group_by(SearchSession.user_id)
                )
            ).all()
        )
        if rows
        else {}
    )
    out = []
    for u in rows:
        sub = await subscriptions.active_subscription(session, u.id)
        out.append(
            AdminUserRow(
                id=u.id,
                telegram_id=u.telegram_id,
                username=u.username,
                first_name=u.first_name,
                created_at=u.created_at,
                last_seen_at=u.last_seen_at,
                is_blocked=u.is_blocked,
                bonus_searches=u.bonus_searches,
                plan=(sub.plan_code + (" (trial)" if sub.source == "trial" else "")) if sub else "free",
                searches=int(counts.get(u.id, 0)),
            )
        )
    return out


@router.get("/users/{user_id}")
async def user_detail(user_id: int, _: User = Depends(admin_user), session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    u = await session.get(User, user_id)
    if u is None:
        raise NotFound("user_not_found")
    me: MeOut = await build_me(session, u)
    subs = (await session.scalars(select(Subscription).where(Subscription.user_id == u.id).order_by(Subscription.created_at.desc()))).all()
    pays = (await session.scalars(select(Payment).where(Payment.user_id == u.id).order_by(Payment.created_at.desc()))).all()
    return {
        "user": me.model_dump(),
        "is_blocked": u.is_blocked,
        "blocked_reason": u.blocked_reason,
        "subscriptions": [SubscriptionOut.model_validate(s).model_dump() for s in subs],
        "payments": [PaymentOut.model_validate(p).model_dump() for p in pays],
    }


class BlockIn(BaseModel):
    blocked: bool
    reason: str | None = Field(default=None, max_length=256)


@router.post("/users/{user_id}/block")
async def block_user(
    user_id: int, body: BlockIn, admin: User = Depends(admin_user), session: AsyncSession = Depends(get_session)
) -> dict[str, bool]:
    u = await session.get(User, user_id)
    if u is None:
        raise NotFound("user_not_found")
    if u.telegram_id in get_settings().admin_telegram_ids:
        raise AppError("cannot_block_admin", "Нельзя заблокировать администратора.")
    u.is_blocked, u.blocked_reason = body.blocked, body.reason if body.blocked else None
    await _log(session, admin, "block" if body.blocked else "unblock", str(user_id), body.model_dump())
    return {"blocked": u.is_blocked}


class GrantIn(BaseModel):
    plan_code: str
    days: int = Field(ge=1, le=3650)
    note: str | None = Field(default=None, max_length=256)


@router.post("/users/{user_id}/subscription", response_model=SubscriptionOut)
async def grant_subscription(
    user_id: int, body: GrantIn, admin: User = Depends(admin_user), session: AsyncSession = Depends(get_session)
) -> SubscriptionOut:
    if await session.get(User, user_id) is None:
        raise NotFound("user_not_found")
    await subscriptions.get_plan(session, body.plan_code)
    sub = await subscriptions.grant(session, user_id, body.plan_code, body.days, "admin", note=body.note)
    await _log(session, admin, "grant_subscription", str(user_id), body.model_dump())
    return SubscriptionOut.model_validate(sub)


@router.post("/subscriptions/{subscription_id}/revoke", response_model=SubscriptionOut)
async def revoke_subscription(
    subscription_id: int, admin: User = Depends(admin_user), session: AsyncSession = Depends(get_session)
) -> SubscriptionOut:
    sub = await session.get(Subscription, subscription_id, with_for_update=True)
    if sub is None:
        raise NotFound("subscription_not_found")
    sub.status, sub.expires_at, sub.auto_renew = "revoked", datetime.now(UTC), False
    await _log(session, admin, "revoke_subscription", str(subscription_id), {})
    return SubscriptionOut.model_validate(sub)


class BonusIn(BaseModel):
    delta: int = Field(ge=-10000, le=10000)


@router.post("/users/{user_id}/bonus")
async def adjust_bonus(
    user_id: int, body: BonusIn, admin: User = Depends(admin_user), session: AsyncSession = Depends(get_session)
) -> dict[str, int]:
    res = await session.execute(
        update(User)
        .where(User.id == user_id)
        .values(bonus_searches=func.greatest(User.bonus_searches + body.delta, 0))
        .returning(User.bonus_searches)
    )
    val = res.scalar_one_or_none()
    if val is None:
        raise NotFound("user_not_found")
    await _log(session, admin, "adjust_bonus", str(user_id), body.model_dump())
    return {"bonus_searches": val}


class AdminPaymentRow(PaymentOut):
    user_id: int
    telegram_payment_charge_id: str


@router.get("/payments", response_model=list[AdminPaymentRow])
async def list_payments(
    offset: int = Query(0, ge=0), limit: int = Query(50, le=200), _: User = Depends(admin_user), session: AsyncSession = Depends(get_session)
) -> list[AdminPaymentRow]:
    rows = (await session.scalars(select(Payment).order_by(Payment.created_at.desc()).offset(offset).limit(limit))).all()
    return [AdminPaymentRow.model_validate(p) for p in rows]


@router.post("/payments/{payment_id}/refund", response_model=AdminPaymentRow)
async def refund(payment_id: int, admin: User = Depends(admin_user), session: AsyncSession = Depends(get_session)) -> AdminPaymentRow:
    p = await payments.refund(session, payment_id)
    await _log(session, admin, "refund", str(payment_id), {"charge": p.telegram_payment_charge_id})
    return AdminPaymentRow.model_validate(p)


@router.get("/plans", response_model=list[PlanOut])
async def plans(_: User = Depends(admin_user), session: AsyncSession = Depends(get_session)) -> list[PlanOut]:
    return [PlanOut.model_validate(p) for p in (await session.scalars(select(Plan).order_by(Plan.sort_order))).all()]


class PlanPatch(BaseModel):
    title: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=500)
    price_stars: int | None = Field(default=None, ge=0, le=100000)
    period_days: int | None = Field(default=None, ge=0, le=3650)
    search_limit: int | None = Field(default=None, ge=0, le=100000)
    limit_window: Literal["day", "month"] | None = None
    priority: int | None = Field(default=None, ge=0, le=10)
    is_active: bool | None = None
    features: dict[str, Any] | None = None


@router.patch("/plans/{code}", response_model=PlanOut)
async def patch_plan(code: str, body: PlanPatch, admin: User = Depends(admin_user), session: AsyncSession = Depends(get_session)) -> PlanOut:
    plan = await session.get(Plan, code)
    if plan is None:
        raise NotFound("plan_not_found")
    data = body.model_dump(exclude_none=True)
    if code == "free" and data.get("price_stars"):
        raise AppError("free_is_free", "Тариф Free не может быть платным.")
    if "features" in data:
        data["features"] = {**(plan.features or {}), **data["features"]}
    for k, v in data.items():
        setattr(plan, k, v)
    await _log(session, admin, "patch_plan", code, data)
    await session.flush()
    return PlanOut.model_validate(plan)


@router.get("/settings")
async def get_settings_all(_: User = Depends(admin_user), session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    return {k: await get_setting(session, k) for k in DEFAULTS}


@router.put("/settings/{key}")
async def put_setting(
    key: str, value: dict[str, Any] | list[str], admin: User = Depends(admin_user), session: AsyncSession = Depends(get_session)
) -> Any:
    if key not in DEFAULTS:
        raise NotFound("setting_not_found")
    if isinstance(DEFAULTS[key], dict):
        if not isinstance(value, dict):
            raise AppError("bad_setting")
        allowed = set(DEFAULTS[key])
        value = {k: v for k, v in value.items() if k in allowed}
        value = {**(await get_setting(session, key)), **value}
    elif key == "basic_marketplaces":
        if not isinstance(value, list) or any(registry.get(c) is None for c in value):
            raise AppError("bad_setting", "Неизвестный маркетплейс.")
    await set_setting(session, key, value)
    await _log(session, admin, "put_setting", key, {"value": value})
    return value


@router.get("/errors")
async def errors(limit: int = Query(100, le=1000), _: User = Depends(admin_user)) -> list[dict[str, Any]]:
    raw = await get_redis().lrange(ERRORS_KEY, 0, limit - 1)
    return [orjson.loads(x) for x in raw]


@router.get("/integrations")
async def integrations(_: User = Depends(admin_user), session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    st = {r.code: r for r in (await session.scalars(select(MarketplaceStatus))).all()}
    mk = []
    for p in registry.providers().values():
        info, row = p.info(), st.get(p.code)
        mk.append(
            {
                "code": info.code,
                "name": info.name,
                "kind": info.kind.value,
                "enabled": p.enabled,
                "state": row.status if row else info.state.value,
                "note": info.note,
                "last_check_at": row.last_check_at if row else None,
                "last_ok_at": row.last_ok_at if row else None,
                "last_error": row.last_error if row else None,
                "latency_ms": row.latency_ms if row else None,
            }
        )
    s = get_settings()
    ai_raw = await get_redis().hgetall(AI_STATS_KEY)
    ai = {
        "vision": {
            "provider": s.vision_provider,
            "model": s.anthropic_model if s.vision_provider == "anthropic" else s.openai_compat_model,
            "ok": int(ai_raw.get("vision:ok", 0)),
            "fail": int(ai_raw.get("vision:fail", 0)),
            "last_ok": ai_raw.get("vision:last_ok"),
            "last_error": ai_raw.get("vision:last_error"),
        },
        "embedding": {
            "provider": s.embedding_provider,
            "dim": s.embedding_dim,
            "ok": int(ai_raw.get("embedding:ok", 0)),
            "fail": int(ai_raw.get("embedding:fail", 0)),
            "last_ok": ai_raw.get("embedding:last_ok"),
            "last_error": ai_raw.get("embedding:last_error"),
        },
    }
    return {"marketplaces": mk, "ai": ai}


@router.get("/logs")
async def admin_logs(_: User = Depends(admin_user), session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    rows = (await session.scalars(select(AdminLog).order_by(AdminLog.created_at.desc()).limit(200))).all()
    return [{"at": r.created_at, "admin": r.admin_telegram_id, "action": r.action, "target": r.target, "payload": r.payload} for r in rows]
