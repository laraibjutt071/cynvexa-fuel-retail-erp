"""
Platform-administration endpoints: managing the Plan catalog and every
organization's Subscription/payments. Every endpoint here depends on
require_superuser, never require_permission - this is deliberately outside
the organization-scoped role system (there is no "organization" in a plan's
own URL), matching how organization creation already works (see
app/api/organizations.py). Not exposed to regular organization users at all.
"""

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db, require_superuser
from app.core.audit import write_audit_log
from app.exceptions import ConflictError, NotFoundError
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.subscription_payment import SubscriptionPayment
from app.models.user import User
from app.schemas.plan import PlanCreate, PlanRead, PlanUpdate
from app.schemas.subscription import (
    SubscriptionCreate,
    SubscriptionPaymentCreate,
    SubscriptionPaymentRead,
    SubscriptionRead,
    SubscriptionUpdate,
)

router = APIRouter(prefix="/platform", tags=["platform"])

# No auth at all - a prospective customer looking at the sign-up/pricing
# page hasn't got an account yet. Deliberately a separate router/path from
# /platform/plans above (which is the full CRUD, superuser-only view) and
# deliberately read-only: only active plans, and only the fields a pricing
# page needs.
public_router = APIRouter(tags=["public"])


@public_router.get("/plans", response_model=list[PlanRead])
async def list_public_plans(db: AsyncSession = Depends(get_db)) -> list[Plan]:
    result = await db.execute(select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.price_monthly))
    return list(result.scalars().all())


# ---- Plans (platform-admin, full CRUD) --------------------------------------


@router.post("/plans", response_model=PlanRead, status_code=201)
async def create_plan(
    payload: PlanCreate,
    request: Request,
    current_user: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> Plan:
    plan = Plan(**payload.model_dump())
    db.add(plan)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ConflictError(f"A plan with code '{payload.code}' already exists.")

    await write_audit_log(
        db,
        action="plan.create",
        entity_type="Plan",
        entity_id=str(plan.id),
        actor_user_id=current_user.id,
        after=payload.model_dump(mode="json"),
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return plan


@router.get("/plans", response_model=list[PlanRead])
async def list_plans(
    current_user: User = Depends(require_superuser), db: AsyncSession = Depends(get_db)
) -> list[Plan]:
    result = await db.execute(select(Plan).order_by(Plan.price_monthly))
    return list(result.scalars().all())


@router.patch("/plans/{plan_id}", response_model=PlanRead)
async def update_plan(
    plan_id: uuid.UUID,
    payload: PlanUpdate,
    request: Request,
    current_user: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> Plan:
    plan = (await db.execute(select(Plan).where(Plan.id == plan_id))).scalar_one_or_none()
    if plan is None:
        raise NotFoundError("Plan not found.")

    update_data = payload.model_dump(exclude_unset=True)
    before = {field: getattr(plan, field) for field in update_data}
    for field, value in update_data.items():
        setattr(plan, field, value)
    await db.flush()

    await write_audit_log(
        db,
        action="plan.update",
        entity_type="Plan",
        entity_id=str(plan.id),
        actor_user_id=current_user.id,
        before={k: str(v) for k, v in before.items()},
        after={k: str(v) for k, v in update_data.items()},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return plan


# ---- Subscriptions -----------------------------------------------------------


@router.get("/subscriptions", response_model=list[SubscriptionRead])
async def list_subscriptions(
    current_user: User = Depends(require_superuser), db: AsyncSession = Depends(get_db)
) -> list[Subscription]:
    """Every organization's subscription, platform-wide - the view a platform
    admin needs to see who's trialing, active, past due or expired."""
    result = await db.execute(select(Subscription).options(selectinload(Subscription.plan)))
    return list(result.scalars().all())


async def _get_subscription_or_404(db: AsyncSession, organization_id: uuid.UUID) -> Subscription:
    stmt = (
        select(Subscription)
        .options(selectinload(Subscription.plan))
        .where(Subscription.organization_id == organization_id)
    )
    sub = (await db.execute(stmt)).scalar_one_or_none()
    if sub is None:
        raise NotFoundError("This organization has no subscription yet.")
    return sub


@router.post("/organizations/{organization_id}/subscription", response_model=SubscriptionRead, status_code=201)
async def create_subscription(
    organization_id: uuid.UUID,
    payload: SubscriptionCreate,
    request: Request,
    current_user: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> Subscription:
    sub = Subscription(organization_id=organization_id, **payload.model_dump())
    db.add(sub)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ConflictError("This organization already has a subscription - use update instead.")

    await db.refresh(sub, attribute_names=["plan"])
    await write_audit_log(
        db,
        action="subscription.create",
        entity_type="Subscription",
        entity_id=str(sub.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        after=payload.model_dump(mode="json"),
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return sub


@router.get("/organizations/{organization_id}/subscription", response_model=SubscriptionRead)
async def get_subscription_platform(
    organization_id: uuid.UUID,
    current_user: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> Subscription:
    return await _get_subscription_or_404(db, organization_id)


@router.patch("/subscriptions/{subscription_id}", response_model=SubscriptionRead)
async def update_subscription(
    subscription_id: uuid.UUID,
    payload: SubscriptionUpdate,
    request: Request,
    current_user: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> Subscription:
    sub = (
        await db.execute(
            select(Subscription).options(selectinload(Subscription.plan)).where(Subscription.id == subscription_id)
        )
    ).scalar_one_or_none()
    if sub is None:
        raise NotFoundError("Subscription not found.")

    update_data = payload.model_dump(exclude_unset=True)
    before = {field: getattr(sub, field) for field in update_data}
    for field, value in update_data.items():
        setattr(sub, field, value)
    await db.flush()
    if "plan_id" in update_data:
        await db.refresh(sub, attribute_names=["plan"])

    await write_audit_log(
        db,
        action="subscription.update",
        entity_type="Subscription",
        entity_id=str(sub.id),
        actor_user_id=current_user.id,
        organization_id=sub.organization_id,
        before={k: str(v) for k, v in before.items()},
        after={k: str(v) for k, v in update_data.items()},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return sub


@router.post(
    "/subscriptions/{subscription_id}/payments", response_model=SubscriptionPaymentRead, status_code=201
)
async def record_subscription_payment(
    subscription_id: uuid.UUID,
    payload: SubscriptionPaymentCreate,
    request: Request,
    current_user: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionPayment:
    sub = (await db.execute(select(Subscription).where(Subscription.id == subscription_id))).scalar_one_or_none()
    if sub is None:
        raise NotFoundError("Subscription not found.")

    payment = SubscriptionPayment(
        subscription_id=subscription_id,
        recorded_by_user_id=current_user.id,
        **payload.model_dump(),
    )
    db.add(payment)
    await db.flush()

    await write_audit_log(
        db,
        action="subscription_payment.record",
        entity_type="SubscriptionPayment",
        entity_id=str(payment.id),
        actor_user_id=current_user.id,
        organization_id=sub.organization_id,
        after=payload.model_dump(mode="json"),
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return payment


@router.get(
    "/subscriptions/{subscription_id}/payments", response_model=list[SubscriptionPaymentRead]
)
async def list_subscription_payments_platform(
    subscription_id: uuid.UUID,
    current_user: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> list[SubscriptionPayment]:
    result = await db.execute(
        select(SubscriptionPayment)
        .where(SubscriptionPayment.subscription_id == subscription_id)
        .order_by(SubscriptionPayment.created_at.desc())
    )
    return list(result.scalars().all())
