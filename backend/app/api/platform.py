"""
Platform-administration endpoints: managing the Plan catalog and every
organization's Subscription/payments. Every endpoint here depends on
require_superuser, never require_permission - this is deliberately outside
the organization-scoped role system (there is no "organization" in a plan's
own URL), matching how organization creation already works (see
app/api/organizations.py). Not exposed to regular organization users at all.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db, require_superuser
from app.core.audit import write_audit_log
from app.core.tenant_provisioning import provision_organization_with_owner
from app.exceptions import ConflictError, NotFoundError
from app.models.audit_log import AuditLog
from app.models.organization import Organization
from app.models.plan import Plan
from app.models.role import Role
from app.models.station import Station
from app.models.subscription import Subscription
from app.models.subscription_payment import SubscriptionPayment
from app.models.user import User
from app.models.user_station_role import UserStationRole
from app.schemas.audit import AuditLogRead
from app.schemas.organization import PlatformOrganizationRow, TenantOnboardingRequest, TenantOnboardingResponse
from app.schemas.plan import PlanCreate, PlanRead, PlanUpdate
from app.schemas.subscription import (
    SubscriptionCreate,
    SubscriptionPaymentCreate,
    SubscriptionPaymentRead,
    SubscriptionRead,
    SubscriptionUpdate,
)

router = APIRouter(prefix="/platform", tags=["platform"])


# ---- Tenant onboarding ("Create Petrol Pump") ---------------------------------


@router.post("/organizations", response_model=TenantOnboardingResponse, status_code=201)
async def onboard_organization(
    payload: TenantOnboardingRequest,
    request: Request,
    current_user: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> TenantOnboardingResponse:
    """The Super Admin 'Create Petrol Pump' workflow - provisions the
    organization, its first station, the owner account, and the Owner role
    assignment in one atomic call, via the exact same provisioning logic
    /auth/register uses (app/core/tenant_provisioning.py). Unlike
    self-registration, the caller (the platform admin) is never signed in
    as the new owner - no tokens are issued here."""
    tenant = await provision_organization_with_owner(
        db,
        company_name=payload.company_name,
        owner_full_name=payload.owner_full_name,
        owner_email=payload.owner_email,
        owner_password=payload.owner_password,
        station_name=payload.station_name,
        plan_code=payload.plan_code,
        phone=payload.phone,
        address=payload.address,
        city=payload.city,
        province=payload.province,
        country=payload.country,
    )

    await write_audit_log(
        db,
        action="organization.onboard_by_platform_admin",
        entity_type="Organization",
        entity_id=str(tenant.organization.id),
        actor_user_id=current_user.id,
        organization_id=tenant.organization.id,
        after={"name": tenant.organization.name, "owner_email": tenant.owner.email},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()

    return TenantOnboardingResponse(
        organization_id=tenant.organization.id,
        organization_name=tenant.organization.name,
        station_id=tenant.station.id,
        owner_user_id=tenant.owner.id,
        owner_email=tenant.owner.email,
    )


# ---- Platform dashboard: stats and activity -----------------------------------


@router.get("/stats")
async def platform_stats(
    current_user: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Every number here is a real COUNT(*) against the actual tables a
    platform admin would otherwise have to list and count by hand - never
    a fabricated or cached figure."""
    total_orgs = (await db.execute(select(func.count()).select_from(Organization))).scalar_one()
    active_orgs = (
        await db.execute(select(func.count()).select_from(Organization).where(Organization.is_active.is_(True)))
    ).scalar_one()
    suspended_orgs = total_orgs - active_orgs

    # An "Owner" holds a station_id IS NULL (org-wide) UserStationRole - the
    # same shape every Owner row has since app/core/tenant_provisioning.py
    # creates it. Distinct user_id so one person can't inflate the count by
    # somehow holding more than one such row.
    owner_role_id_subq = select(func.count(func.distinct(UserStationRole.user_id))).where(
        UserStationRole.station_id.is_(None), UserStationRole.is_active.is_(True)
    )
    total_owners = (await db.execute(owner_role_id_subq)).scalar_one()

    total_users = (await db.execute(select(func.count()).select_from(User).where(User.is_superuser.is_(False)))).scalar_one()

    recent_orgs_stmt = select(Organization).order_by(Organization.created_at.desc()).limit(5)
    recent_orgs = (await db.execute(recent_orgs_stmt)).scalars().all()

    return {
        "total_organizations": total_orgs,
        "active_organizations": active_orgs,
        "suspended_organizations": suspended_orgs,
        "total_owners": total_owners,
        "total_users": total_users,
        "recent_organizations": [
            {
                "id": str(o.id),
                "name": o.name,
                "is_active": o.is_active,
                "created_at": o.created_at.isoformat(),
            }
            for o in recent_orgs
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


async def _enrich_organizations(db: AsyncSession, orgs: list[Organization]) -> list[PlatformOrganizationRow]:
    """Shared by the list and single-organization enriched reads (Phase
    5c/5b) - one row per organization with its owner, real
    station/employee counts, and last activity, aggregated server-side
    with GROUP BY queries (never one query per organization)."""
    if not orgs:
        return []
    org_ids = [o.id for o in orgs]

    station_counts = dict(
        (await db.execute(
            select(Station.organization_id, func.count())
            .where(Station.organization_id.in_(org_ids))
            .group_by(Station.organization_id)
        )).all()
    )
    employee_counts = dict(
        (await db.execute(
            select(UserStationRole.organization_id, func.count(func.distinct(UserStationRole.user_id)))
            .where(UserStationRole.organization_id.in_(org_ids), UserStationRole.is_active.is_(True))
            .group_by(UserStationRole.organization_id)
        )).all()
    )
    last_activity = dict(
        (await db.execute(
            select(AuditLog.organization_id, func.max(AuditLog.created_at))
            .where(AuditLog.organization_id.in_(org_ids))
            .group_by(AuditLog.organization_id)
        )).all()
    )
    # One org-wide Owner per organization, same "station_id IS NULL" shape
    # platform_stats already uses - picks whichever is first if more than
    # one somehow holds it, never fabricated.
    owner_rows = (
        await db.execute(
            select(UserStationRole.organization_id, User.full_name, User.email)
            .join(User, User.id == UserStationRole.user_id)
            .join(Role, Role.id == UserStationRole.role_id)
            .where(
                UserStationRole.organization_id.in_(org_ids),
                UserStationRole.station_id.is_(None),
                UserStationRole.is_active.is_(True),
                Role.name == "Owner",
            )
        )
    ).all()
    owner_by_org: dict[uuid.UUID, tuple[str, str]] = {}
    for org_id, full_name, email in owner_rows:
        owner_by_org.setdefault(org_id, (full_name, email))

    return [
        PlatformOrganizationRow(
            id=org.id,
            name=org.name,
            city=org.city,
            is_active=org.is_active,
            created_at=org.created_at,
            owner_full_name=owner_by_org.get(org.id, (None, None))[0],
            owner_email=owner_by_org.get(org.id, (None, None))[1],
            station_count=station_counts.get(org.id, 0),
            employee_count=employee_counts.get(org.id, 0),
            last_activity_at=last_activity.get(org.id),
        )
        for org in orgs
    ]


@router.get("/organizations", response_model=list[PlatformOrganizationRow])
async def list_organizations_enriched(
    q: str | None = Query(default=None, max_length=200),
    status: str | None = Query(default=None, pattern="^(active|suspended)$"),
    current_user: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> list[PlatformOrganizationRow]:
    """The Super Admin client directory (Phase 5c)."""
    org_stmt = select(Organization)
    if q:
        org_stmt = org_stmt.where(Organization.name.ilike(f"%{q}%"))
    if status == "active":
        org_stmt = org_stmt.where(Organization.is_active.is_(True))
    elif status == "suspended":
        org_stmt = org_stmt.where(Organization.is_active.is_(False))
    org_stmt = org_stmt.order_by(Organization.created_at.desc())
    orgs = list((await db.execute(org_stmt)).scalars().all())
    return await _enrich_organizations(db, orgs)


@router.get("/organizations/{organization_id}", response_model=PlatformOrganizationRow)
async def get_organization_enriched(
    organization_id: uuid.UUID,
    current_user: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> PlatformOrganizationRow:
    """Phase 5b: lets the Super Admin review a target organization's
    identity (before deciding to start a support session) without that
    lookup itself requiring one - this is the same directory data
    list_organizations_enriched already exposes, just for one row."""
    org = (await db.execute(select(Organization).where(Organization.id == organization_id))).scalar_one_or_none()
    if org is None:
        raise NotFoundError("Organization not found.")
    rows = await _enrich_organizations(db, [org])
    return rows[0]


@router.get("/audit-log", response_model=list[AuditLogRead])
async def platform_audit_log(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> list[AuditLog]:
    """Platform-wide recent activity, across every organization - the
    org-scoped GET /organizations/{id}/audit-log already exists for a
    tenant's own view; this is the same table, the platform-admin view of
    everything at once, superuser-only."""
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    return list((await db.execute(stmt)).scalars().all())

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
