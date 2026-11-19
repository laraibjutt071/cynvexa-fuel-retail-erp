import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mixins import utcnow
from app.models.support_session import SupportSession
from app.models.user import User

# "Short configurable lifetime... strict maximum permitted lifetime" - the
# caller picks one of these, never an arbitrary client-supplied duration.
SUPPORT_SESSION_ALLOWED_DURATIONS_MINUTES = [15, 30, 60]
SUPPORT_SESSION_MAX_MINUTES = max(SUPPORT_SESSION_ALLOWED_DURATIONS_MINUTES)


async def get_active_support_session(
    db: AsyncSession, *, superuser_id: uuid.UUID, organization_id: uuid.UUID
) -> SupportSession | None:
    """The caller's current non-ended, non-expired session for this
    organization, or None. Deliberately scoped to (superuser_id,
    organization_id) together - a session opened for one organization
    never grants anything in another, and this is the only lookup
    require_permission (and everything that mirrors it) ever performs."""
    stmt = (
        select(SupportSession)
        .where(
            SupportSession.superuser_id == superuser_id,
            SupportSession.organization_id == organization_id,
            SupportSession.ended_at.is_(None),
            SupportSession.expires_at > utcnow(),
        )
        .order_by(SupportSession.created_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def support_session_grants(
    db: AsyncSession,
    *,
    current_user: User,
    organization_id: uuid.UUID,
    station_id: uuid.UUID | None,
    permission_code: str,
) -> SupportSession | None:
    """Returns the active support session that grants permission_code for
    this org/station, or None. Strictly read-only by design: any
    permission_code that isn't a ':read' code is rejected before a
    session is even looked up, so there is no code path by which an
    active session can ever satisfy a write check - see
    docs/PHASE_5B_SUPER_ADMIN_SUPPORT_SESSIONS_AUDIT.md's revision."""
    if not permission_code.endswith(":read"):
        return None
    session = await get_active_support_session(
        db, superuser_id=current_user.id, organization_id=organization_id
    )
    if session is None:
        return None
    # A station-scoped session (same semantics as a station-scoped
    # UserStationRole, see app/core/permissions.py::user_has_permission)
    # never covers a different station, and never covers an org-wide
    # resource (station_id target None) either - least privilege.
    if session.station_id is not None and session.station_id != station_id:
        return None
    return session


async def superuser_visible_station_ids(
    db: AsyncSession, *, current_user: User, organization_id: uuid.UUID
) -> set[uuid.UUID] | None:
    """Mirrors app/core/permissions.py::get_station_visibility_scope's
    return shape for the handful of read endpoints (audit log, expenses,
    pending-approvals report) that filter by every station the caller can
    see rather than just checking a single target station_id.
    None = unrestricted (an org-wide session); otherwise the one station
    the active session is scoped to. Callers only reach this once
    require_permission has already confirmed an active session exists for
    this organization."""
    session = await get_active_support_session(
        db, superuser_id=current_user.id, organization_id=organization_id
    )
    if session is None or session.station_id is None:
        return None
    return {session.station_id}
