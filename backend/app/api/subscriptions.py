"""
Org-scoped, read-only view of an organization's own subscription - the
counterpart to the platform-admin endpoints in app/api/platform.py, which
are the only place a subscription can actually be created or changed. An
organization can see its own plan, status and payment history; it can never
modify any of it from here.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db, require_permission
from app.core.permission_codes import SUBSCRIPTION_READ
from app.exceptions import NotFoundError
from app.models.subscription import Subscription
from app.models.subscription_payment import SubscriptionPayment
from app.models.user import User
from app.schemas.subscription import SubscriptionPaymentRead, SubscriptionRead

router = APIRouter(prefix="/organizations/{organization_id}/subscription", tags=["subscription"])


@router.get("", response_model=SubscriptionRead)
async def get_my_subscription(
    organization_id: uuid.UUID,
    current_user: User = Depends(require_permission(SUBSCRIPTION_READ)),
    db: AsyncSession = Depends(get_db),
) -> Subscription:
    stmt = (
        select(Subscription)
        .options(selectinload(Subscription.plan))
        .where(Subscription.organization_id == organization_id)
    )
    sub = (await db.execute(stmt)).scalar_one_or_none()
    if sub is None:
        raise NotFoundError("This organization has no subscription yet - contact CYNVEXA to set one up.")
    return sub


@router.get("/payments", response_model=list[SubscriptionPaymentRead])
async def list_my_subscription_payments(
    organization_id: uuid.UUID,
    current_user: User = Depends(require_permission(SUBSCRIPTION_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[SubscriptionPayment]:
    sub = (
        await db.execute(select(Subscription).where(Subscription.organization_id == organization_id))
    ).scalar_one_or_none()
    if sub is None:
        raise NotFoundError("This organization has no subscription yet - contact CYNVEXA to set one up.")

    result = await db.execute(
        select(SubscriptionPayment)
        .where(SubscriptionPayment.subscription_id == sub.id)
        .order_by(SubscriptionPayment.created_at.desc())
    )
    return list(result.scalars().all())
