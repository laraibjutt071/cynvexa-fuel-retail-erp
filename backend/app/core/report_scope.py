"""
Phase 8b: the one place that resolves "which stations in this organization
may this caller's report see", shared by every org-wide report endpoint
(app/api/org_reports.py) and refactored into the pre-existing
pending-approvals report (app/api/reports.py) so both go through the exact
same rule rather than two copies that could drift apart.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import get_station_visibility_scope
from app.core.support_sessions import superuser_visible_station_ids
from app.exceptions import NotFoundError, PermissionDeniedError
from app.models.station import Station
from app.models.user import User


async def resolve_visible_station_ids(
    db: AsyncSession, *, current_user: User, organization_id: uuid.UUID, permission_code: str
) -> set[uuid.UUID] | None:
    """None means "every station in the org" (an org-wide role grant, or
    for a superuser, an org-wide support session) - otherwise the concrete
    set of stations a station-scoped grant covers. Identical rule
    require_permission already used to let the caller reach this endpoint
    at all; this is just the data-filtering half of it."""
    if current_user.is_superuser:
        return await superuser_visible_station_ids(db, current_user=current_user, organization_id=organization_id)
    return await get_station_visibility_scope(
        db, user_id=current_user.id, organization_id=organization_id, permission_code=permission_code
    )


async def resolve_authorized_station_ids(
    db: AsyncSession,
    *,
    current_user: User,
    organization_id: uuid.UUID,
    permission_code: str,
    requested_station_ids: list[uuid.UUID] | None,
) -> list[uuid.UUID]:
    """
    The concrete, authorized list of station ids an org-wide report may
    aggregate over - every station in the org the caller can see, or (when
    requested_station_ids narrows it) the intersection with that explicit
    filter. Never returns None: every call site gets a real list, even
    when that list is "every station in the org".

    A requested station id that doesn't belong to this organization at all
    raises the same generic 404 every other station lookup in this app
    already raises (app/api/common.py::get_station_or_404) - consistent,
    not a new information leak. A requested station id that does belong to
    the org but isn't in the caller's own visible set raises a generic 403
    naming no station - a station-scoped viewer must never learn anything
    about a station outside their own scope, including whether it exists.
    """
    all_org_station_ids = {
        row[0]
        for row in (
            await db.execute(select(Station.id).where(Station.organization_id == organization_id))
        ).all()
    }
    visible = await resolve_visible_station_ids(
        db, current_user=current_user, organization_id=organization_id, permission_code=permission_code
    )
    authorized = all_org_station_ids if visible is None else (all_org_station_ids & visible)

    if requested_station_ids is None:
        return sorted(authorized, key=str)

    requested = set(requested_station_ids)
    if requested - all_org_station_ids:
        raise NotFoundError("Station not found.")
    if requested - authorized:
        raise PermissionDeniedError("You are not authorized to view one or more of the requested stations.")
    return sorted(requested, key=str)
