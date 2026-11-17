"""
The one place that creates a new petrol-pump tenant (Organization + its
first Station + an owner User + the Owner role assignment + a trial
Subscription), atomically. Two callers use this:

- POST /auth/register - public, self-service, the caller becomes the
  Owner and is signed in immediately.
- POST /platform/organizations - Super Admin "Create Petrol Pump"
  workflow (Phase 3); the caller is the platform admin, not the new
  owner, so no tokens are issued here - see app/api/platform.py.

Keeping this logic in one function is deliberate: the brief's own
instruction is "reuse existing organization registration ... wherever
possible, do not duplicate business logic." Nothing about who calls it
changes what it does to the database.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.exceptions import ConflictError, ServiceUnavailableError
from app.models.organization import Organization
from app.models.plan import Plan
from app.models.role import Role
from app.models.station import Station
from app.models.subscription import BillingCycle, Subscription, SubscriptionStatus
from app.models.user import User
from app.models.user_station_role import UserStationRole


@dataclass
class ProvisionedTenant:
    organization: Organization
    station: Station
    owner: User


async def provision_organization_with_owner(
    db: AsyncSession,
    *,
    company_name: str,
    owner_full_name: str,
    owner_email: str,
    owner_password: str,
    station_name: str = "Main Station",
    plan_code: str | None = None,
    phone: str | None = None,
    address: str | None = None,
    city: str | None = None,
    province: str | None = None,
    country: str | None = None,
) -> ProvisionedTenant:
    """Flushes (does not commit) a new Organization, its first Station, the
    owner User, the UserStationRole granting them org-wide Owner, and a
    14-day-trial Subscription. The caller writes its own audit log entry
    and commits - this function never commits, so a caller can add more
    to the same transaction (or roll it all back) before it's final."""
    existing = (await db.execute(select(User).where(User.email == owner_email))).scalar_one_or_none()
    if existing is not None:
        raise ConflictError("An account with this email already exists. Try logging in instead.")

    owner_role = (await db.execute(select(Role).where(Role.name == "Owner"))).scalar_one_or_none()
    if owner_role is None:
        raise ServiceUnavailableError("This CYNVEXA instance isn't fully set up yet. Please contact support.")

    resolved_plan_code = plan_code or "starter"
    plan = (
        await db.execute(select(Plan).where(Plan.code == resolved_plan_code, Plan.is_active.is_(True)))
    ).scalar_one_or_none()
    if plan is None:
        raise ServiceUnavailableError(f"The '{resolved_plan_code}' plan isn't available right now. Please contact support.")

    owner = User(email=owner_email, full_name=owner_full_name, hashed_password=hash_password(owner_password))
    db.add(owner)
    await db.flush()

    org = Organization(
        name=company_name,
        phone=phone,
        address=address,
        city=city,
        province=province,
        country=country,
    )
    db.add(org)
    await db.flush()

    station = Station(organization_id=org.id, name=station_name, code="ST-1")
    db.add(station)
    await db.flush()

    db.add(UserStationRole(user_id=owner.id, organization_id=org.id, station_id=None, role_id=owner_role.id))

    now = datetime.now(timezone.utc)
    trial_ends = now + timedelta(days=14)
    db.add(
        Subscription(
            organization_id=org.id,
            plan_id=plan.id,
            status=SubscriptionStatus.TRIAL,
            billing_cycle=BillingCycle.MONTHLY,
            trial_ends_at=trial_ends,
            current_period_start=now,
            current_period_end=trial_ends,
        )
    )
    await db.flush()

    return ProvisionedTenant(organization=org, station=station, owner=owner)
