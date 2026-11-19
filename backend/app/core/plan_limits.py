"""
Phase 8a: enforces a subscription plan's max_stations/max_users against new
additions, without restricting anything an organization already has.

Definitions (deliberately asymmetric, documented here because neither is
obvious from the column names alone):

- A STATION counts once created, regardless of Station.is_active. There is
  no station-delete feature in this app, so "deactivate one to free a slot,
  then create another" would be a loophole if deactivated stations didn't
  still count - a station is a physical business location, not a seat.
- A USER counts only while genuinely active: User.is_active AND an active
  UserStationRole in this organization. Deactivating staff is a normal,
  supported operation and should free a seat, matching ordinary seat-based
  SaaS billing intuition - unlike a station, there is a real, supported way
  to free this kind of slot. A pending (not yet accepted/expired/revoked)
  Invitation ALSO reserves a seat the moment it's created - otherwise an
  organization at its limit could invite far past it, and every one of
  those invitations would then race to accept into an over-limit
  organization. The reservation is released the moment the invitation is
  revoked or expires; it converts into the real seat it already reserved
  on acceptance, never an additional one (see `enforce_user_limit`'s
  `counting_pending` parameter).

No subscription at all => unrestricted, matching every organization that
predates Phase 7's subscription model (see docs/REMAINING_RISKS.md).
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import ConflictError
from app.models.invitation import Invitation
from app.models.mixins import utcnow
from app.models.organization import Organization
from app.models.plan import Plan
from app.models.station import Station
from app.models.subscription import Subscription
from app.models.user import User
from app.models.user_station_role import UserStationRole


async def _lock_organization(db: AsyncSession, organization_id: uuid.UUID) -> None:
    """Serializes concurrent limit checks for the SAME organization: a
    second concurrent request blocks here until the first commits (or
    rolls back) its creation, then re-counts against the up-to-date
    total - the same row-lock-then-check-then-insert pattern already used
    for support sessions (app/api/support_sessions.py)."""
    await db.execute(select(Organization.id).where(Organization.id == organization_id).with_for_update())


async def _get_plan(db: AsyncSession, organization_id: uuid.UUID) -> Plan | None:
    stmt = (
        select(Plan)
        .join(Subscription, Subscription.plan_id == Plan.id)
        .where(Subscription.organization_id == organization_id)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def enforce_station_limit(db: AsyncSession, organization_id: uuid.UUID) -> None:
    await _lock_organization(db, organization_id)
    plan = await _get_plan(db, organization_id)
    if plan is None or plan.max_stations is None:
        return
    current = (
        await db.execute(
            select(func.count()).select_from(Station).where(Station.organization_id == organization_id)
        )
    ).scalar_one()
    if current >= plan.max_stations:
        raise ConflictError(
            f"This organization's plan ({plan.name}) allows up to {plan.max_stations} station(s), "
            "and that limit has been reached. Ask your platform administrator to upgrade the "
            "subscription plan to add another station."
        )


async def enforce_user_limit(db: AsyncSession, organization_id: uuid.UUID, *, counting_pending: bool) -> None:
    """
    counting_pending=True: called when reserving a NEW seat (creating a
    user directly, or creating an invitation) - current active users plus
    every other still-pending invitation must leave room for one more.

    counting_pending=False: called when an already-pending invitation is
    being accepted - its own seat was already reserved when it was
    created, so only the current active-user count (not pending
    invitations) is checked against the limit.
    """
    await _lock_organization(db, organization_id)
    plan = await _get_plan(db, organization_id)
    if plan is None or plan.max_users is None:
        return

    active_users = (
        await db.execute(
            select(func.count(func.distinct(UserStationRole.user_id)))
            .join(User, User.id == UserStationRole.user_id)
            .where(
                UserStationRole.organization_id == organization_id,
                UserStationRole.is_active.is_(True),
                User.is_active.is_(True),
            )
        )
    ).scalar_one()

    current = active_users
    if counting_pending:
        pending_invitations = (
            await db.execute(
                select(func.count())
                .select_from(Invitation)
                .where(
                    Invitation.organization_id == organization_id,
                    Invitation.accepted_at.is_(None),
                    Invitation.revoked_at.is_(None),
                    Invitation.expires_at > utcnow(),
                )
            )
        ).scalar_one()
        current += pending_invitations

    if current >= plan.max_users:
        raise ConflictError(
            f"This organization's plan ({plan.name}) allows up to {plan.max_users} user account(s) "
            "(active employees plus pending invitations), and that limit has been reached. "
            "Deactivate an unused account, or ask your platform administrator to upgrade the "
            "subscription plan to add another."
        )
