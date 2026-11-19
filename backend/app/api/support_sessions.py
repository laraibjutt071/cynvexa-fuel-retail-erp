"""
Phase 5b: the Super Admin's only path into a tenant's business data - see
docs/PHASE_5B_SUPER_ADMIN_SUPPORT_SESSIONS_AUDIT.md. Strictly read-only
(app/core/support_sessions.py enforces this everywhere a session is
consulted); creation/ending/listing here is superuser-only, same as the
rest of app/api/platform.py.
"""

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_station_or_404
from app.api.deps import get_db, require_superuser
from app.core.audit import write_audit_log
from app.core.support_sessions import SUPPORT_SESSION_MAX_MINUTES
from app.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.models.mixins import utcnow
from app.models.organization import Organization
from app.models.station import Station
from app.models.support_session import SupportSession
from app.models.user import User
from app.schemas.support_session import SupportSessionCreate, SupportSessionRead

router = APIRouter(prefix="/platform/support-sessions", tags=["support-sessions"])


def _to_read(session: SupportSession, *, organization_name: str, station_name: str | None) -> SupportSessionRead:
    if session.ended_at is not None:
        status = "ended"
    elif session.expires_at <= utcnow():
        status = "expired"
    else:
        status = "active"
    return SupportSessionRead(
        id=session.id,
        organization_id=session.organization_id,
        organization_name=organization_name,
        station_id=session.station_id,
        station_name=station_name,
        reason=session.reason,
        created_at=session.created_at,
        expires_at=session.expires_at,
        ended_at=session.ended_at,
        status=status,
    )


@router.post("", response_model=SupportSessionRead, status_code=201)
async def create_support_session(
    payload: SupportSessionCreate,
    request: Request,
    current_user: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> SupportSessionRead:
    org = (
        await db.execute(select(Organization).where(Organization.id == payload.organization_id))
    ).scalar_one_or_none()
    if org is None:
        raise NotFoundError("Organization not found.")

    station_name: str | None = None
    if payload.station_id is not None:
        station = await get_station_or_404(db, payload.organization_id, payload.station_id)
        station_name = station.name

    # Lock the admin's own existing non-ended row (if any) so two
    # concurrent creation requests can't both decide "no active session"
    # at once. If it's already past its own expiry, close it here rather
    # than letting a stale row block a legitimate new session forever.
    existing = (
        await db.execute(
            select(SupportSession)
            .where(SupportSession.superuser_id == current_user.id, SupportSession.ended_at.is_(None))
            .with_for_update()
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.expires_at > utcnow():
            raise ConflictError(
                "You already have an active support session. End it before starting another."
            )
        existing.ended_at = utcnow()
        await db.flush()

    session = SupportSession(
        superuser_id=current_user.id,
        organization_id=payload.organization_id,
        station_id=payload.station_id,
        reason=payload.reason,
        expires_at=utcnow() + timedelta(minutes=min(payload.duration_minutes, SUPPORT_SESSION_MAX_MINUTES)),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(session)
    try:
        await db.flush()
    except IntegrityError:
        # The partial unique index caught a race the row lock above
        # didn't (the admin's first-ever session, with no existing row to
        # lock) - same outcome as the explicit check above.
        await db.rollback()
        raise ConflictError(
            "You already have an active support session. End it before starting another."
        )

    await write_audit_log(
        db,
        action="support_session.create",
        entity_type="SupportSession",
        entity_id=str(session.id),
        actor_user_id=current_user.id,
        organization_id=session.organization_id,
        station_id=session.station_id,
        after={"reason": session.reason, "duration_minutes": payload.duration_minutes},
        ip_address=session.ip_address,
    )
    await db.commit()
    return _to_read(session, organization_name=org.name, station_name=station_name)


@router.get("/active", response_model=SupportSessionRead | None)
async def get_active_support_session_route(
    current_user: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> SupportSessionRead | None:
    session = (
        await db.execute(
            select(SupportSession)
            .where(
                SupportSession.superuser_id == current_user.id,
                SupportSession.ended_at.is_(None),
                SupportSession.expires_at > utcnow(),
            )
            .order_by(SupportSession.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if session is None:
        return None
    org = (await db.execute(select(Organization).where(Organization.id == session.organization_id))).scalar_one()
    station_name = None
    if session.station_id is not None:
        station = (await db.execute(select(Station).where(Station.id == session.station_id))).scalar_one_or_none()
        station_name = station.name if station else None
    return _to_read(session, organization_name=org.name, station_name=station_name)


@router.get("", response_model=list[SupportSessionRead])
async def list_support_sessions(
    current_user: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> list[SupportSessionRead]:
    """The caller's own session history - deliberately scoped to the
    caller, not every admin's sessions, least-privilege by default."""
    sessions = list(
        (
            await db.execute(
                select(SupportSession)
                .where(SupportSession.superuser_id == current_user.id)
                .order_by(SupportSession.created_at.desc())
                .limit(100)
            )
        )
        .scalars()
        .all()
    )
    if not sessions:
        return []
    org_ids = {s.organization_id for s in sessions}
    station_ids = {s.station_id for s in sessions if s.station_id is not None}
    orgs = {o.id: o.name for o in (await db.execute(select(Organization).where(Organization.id.in_(org_ids)))).scalars().all()}
    stations = (
        {s.id: s.name for s in (await db.execute(select(Station).where(Station.id.in_(station_ids)))).scalars().all()}
        if station_ids
        else {}
    )
    return [
        _to_read(s, organization_name=orgs.get(s.organization_id, "Unknown"), station_name=stations.get(s.station_id))
        for s in sessions
    ]


@router.post("/{session_id}/end", response_model=SupportSessionRead)
async def end_support_session(
    session_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> SupportSessionRead:
    session = (await db.execute(select(SupportSession).where(SupportSession.id == session_id))).scalar_one_or_none()
    if session is None:
        raise NotFoundError("Support session not found.")
    if session.superuser_id != current_user.id:
        raise PermissionDeniedError("You cannot end another administrator's support session.")

    org = (await db.execute(select(Organization).where(Organization.id == session.organization_id))).scalar_one()
    station_name = None
    if session.station_id is not None:
        station = (await db.execute(select(Station).where(Station.id == session.station_id))).scalar_one_or_none()
        station_name = station.name if station else None

    if session.ended_at is None:
        session.ended_at = utcnow()
        await db.flush()
        await write_audit_log(
            db,
            action="support_session.end",
            entity_type="SupportSession",
            entity_id=str(session.id),
            actor_user_id=current_user.id,
            organization_id=session.organization_id,
            station_id=session.station_id,
            ip_address=request.client.host if request.client else None,
        )
        await db.commit()
    return _to_read(session, organization_name=org.name, station_name=station_name)
