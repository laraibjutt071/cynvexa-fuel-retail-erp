import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.role import Permission, Role, role_permissions
from app.models.user_station_role import UserStationRole


async def user_has_permission(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    organization_id: uuid.UUID,
    station_id: uuid.UUID | None,
    permission_code: str,
) -> bool:
    """
    Access-isolation boundary: a user may act on organization_id (and, when given,
    the specific station_id) only if they hold an ACTIVE UserStationRole in that
    organization whose role grants permission_code, and whose own station scope is
    either NULL (org-wide, e.g. Owner) or exactly station_id.

    This is the single query every permission check in the app ultimately goes
    through. It is deliberately not "trust the caller's org/station" — the
    organization_id/station_id passed in always come from the resource being
    acted on (resolved server-side), never from a client-asserted claim.
    """
    stmt = (
        select(UserStationRole.id)
        .join(Role, Role.id == UserStationRole.role_id)
        .join(role_permissions, role_permissions.c.role_id == Role.id)
        .join(Permission, Permission.id == role_permissions.c.permission_id)
        .where(
            UserStationRole.user_id == user_id,
            UserStationRole.organization_id == organization_id,
            UserStationRole.is_active.is_(True),
            Permission.code == permission_code,
        )
        .limit(1)
    )
    if station_id is not None:
        # Target is a specific station: an org-wide role (station_id NULL) or a role
        # scoped to that exact station both satisfy it. A role scoped to a *different*
        # station must not.
        stmt = stmt.where(
            (UserStationRole.station_id.is_(None)) | (UserStationRole.station_id == station_id)
        )
    # else: target is an org-level resource — any active role in this organization
    # that grants the permission suffices, regardless of that role's own station scope.

    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None


async def get_station_visibility_scope(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    organization_id: uuid.UUID,
    permission_code: str,
) -> set[uuid.UUID] | None:
    """
    For "list everything of mine in this org" style reads (the audit log
    today) where `require_permission` only confirmed the permission exists
    *somewhere* in the org: returns `None` if the caller holds an org-wide
    (station_id NULL) active role granting permission_code - meaning no
    station filtering is needed, they see every station's data. Otherwise
    returns the (possibly multi-station) set of station_ids their roles
    cover, which the caller must then filter rows by, to avoid a
    station-scoped viewer seeing another station's records.
    """
    stmt = (
        select(UserStationRole.station_id)
        .join(Role, Role.id == UserStationRole.role_id)
        .join(role_permissions, role_permissions.c.role_id == Role.id)
        .join(Permission, Permission.id == role_permissions.c.permission_id)
        .where(
            UserStationRole.user_id == user_id,
            UserStationRole.organization_id == organization_id,
            UserStationRole.is_active.is_(True),
            Permission.code == permission_code,
        )
        .distinct()
    )
    station_ids = {row[0] for row in (await db.execute(stmt)).all()}
    if None in station_ids:
        return None
    return station_ids


async def actor_can_grant_scope(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    organization_id: uuid.UUID,
    target_station_id: uuid.UUID | None,
    permission_code: str,
) -> bool:
    """
    Stricter than `user_has_permission`, and used only to decide whether
    `user_id` may create or revoke ANOTHER user's UserStationRole scoped to
    `target_station_id`. An actor may only grant/revoke a scope covered by
    one of their OWN active roles: an org-wide role (station_id NULL) covers
    every station and the org-wide scope itself; a station-scoped role
    covers only that same station and NEVER the org-wide scope.

    This must not be collapsed into `user_has_permission`: there,
    target_station_id=None means "an org-level action with no particular
    station", so any active org role with the permission qualifies - correct
    for reading an organization's profile, say. Here, target_station_id=None
    means "grant org-wide access", which is a strictly wider privilege than a
    station-scoped role has, so it must require an org-wide role to grant it.
    Using `user_has_permission`'s looser rule here would let a station-scoped
    holder of `user:assign_role` escalate someone else to org-wide access.
    """
    stmt = (
        select(UserStationRole.id)
        .join(Role, Role.id == UserStationRole.role_id)
        .join(role_permissions, role_permissions.c.role_id == Role.id)
        .join(Permission, Permission.id == role_permissions.c.permission_id)
        .where(
            UserStationRole.user_id == user_id,
            UserStationRole.organization_id == organization_id,
            UserStationRole.is_active.is_(True),
            Permission.code == permission_code,
        )
        .limit(1)
    )
    if target_station_id is None:
        stmt = stmt.where(UserStationRole.station_id.is_(None))
    else:
        stmt = stmt.where(
            (UserStationRole.station_id.is_(None))
            | (UserStationRole.station_id == target_station_id)
        )
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None
