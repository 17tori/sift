from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, get_session
from app.core import ratelimit
from app.core.errors import NotFound
from app.db.models import PaymentIntent, Plan, User
from app.schemas.common import IntentOut, InvoiceIn, InvoiceOut, PlanOut
from app.services import payments

router = APIRouter(prefix="/api/v1")


@router.get("/plans", response_model=list[PlanOut])
async def list_plans(session: AsyncSession = Depends(get_session)) -> list[PlanOut]:
    rows = (await session.scalars(select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.sort_order))).all()
    return [PlanOut.model_validate(p) for p in rows]


@router.post("/payments/invoice", response_model=InvoiceOut)
async def create_invoice(body: InvoiceIn, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> InvoiceOut:
    await ratelimit.hit(f"invoice:{user.id}", limit=10, window_seconds=600)
    intent = await payments.create_invoice(session, user, body.plan_code)
    assert intent.invoice_link
    return InvoiceOut(intent_id=intent.id, invoice_link=intent.invoice_link, amount_stars=intent.amount_stars, recurring=intent.recurring)


@router.get("/payments/intents/{intent_id}", response_model=IntentOut)
async def intent_status(intent_id: uuid.UUID, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> IntentOut:
    intent = await session.get(PaymentIntent, intent_id)
    if intent is None or intent.user_id != user.id:
        raise NotFound("intent_not_found")
    return IntentOut(intent_id=intent.id, status=intent.status, plan_code=intent.plan_code)
