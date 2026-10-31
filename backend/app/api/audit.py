import uuid
from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_permission
from app.core.csv_export import csv_response
from app.core.permission_codes import AUDIT_READ
from app.core.permissions import get_station_visibility_scope
from app.exceptions import ValidationFailedError
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.audit import AuditLogRead

router = APIRouter(prefix="/organizations/{organization_id}/audit-log", tags=["audit"])


def _build_filtered_stmt(
    organization_id: uuid.UUID,
    *,
    action: str | None,
    entity_type: str | None,
    actor_user_id: uuid.UUID | None,
    station_id: uuid.UUID | None,
    date_from: date | None,
    date_to: date | None,
):
    stmt = select(AuditLog).where(AuditLog.organization_id == organization_id)
    if action is not None:
        stmt = stmt.where(AuditLog.action == action)
    if entity_type is not None:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if actor_user_id is not None:
        stmt = stmt.where(AuditLog.actor_user_id == actor_user_id)
    if station_id is not None:
        stmt = stmt.where(AuditLog.station_id == station_id)
    if date_from is not None:
        stmt = stmt.where(AuditLog.created_at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
    if date_to is not None:
        if date_from is not None and date_to < date_from:
            raise ValidationFailedError("date_to must not be before date_from.")
        stmt = stmt.where(AuditLog.created_at <= datetime.combine(date_to, time.max, tzinfo=timezone.utc))
    return stmt


async def _apply_visibility_scope(
    db: AsyncSession, stmt, *, current_user: User, organization_id: uuid.UUID
):
    if current_user.is_superuser:
        return stmt
    visible_station_ids = await get_station_visibility_scope(
        db, user_id=current_user.id, organization_id=organization_id, permission_code=AUDIT_READ
    )
    if visible_station_ids is not None:
        stmt = stmt.where((AuditLog.station_id.is_(None)) | (AuditLog.station_id.in_(visible_station_ids)))
    return stmt


@router.get("", response_model=list[AuditLogRead])
async def list_audit_log(
    organization_id: uuid.UUID,
    action: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    actor_user_id: uuid.UUID | None = Query(default=None),
    station_id: uuid.UUID | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(require_permission(AUDIT_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[AuditLog]:
    stmt = _build_filtered_stmt(
        organization_id,
        action=action,
        entity_type=entity_type,
        actor_user_id=actor_user_id,
        station_id=station_id,
        date_from=date_from,
        date_to=date_to,
    )
    # require_permission only confirmed AUDIT_READ exists SOMEWHERE in this
    # org - a holder scoped to one station must not see another station's
    # events.
    stmt = await _apply_visibility_scope(db, stmt, current_user=current_user, organization_id=organization_id)
    stmt = stmt.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/export")
async def export_audit_log(
    organization_id: uuid.UUID,
    action: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    actor_user_id: uuid.UUID | None = Query(default=None),
    station_id: uuid.UUID | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    limit: int = Query(default=5000, ge=1, le=20000),
    current_user: User = Depends(require_permission(AUDIT_READ)),
    db: AsyncSession = Depends(get_db),
):
    stmt = _build_filtered_stmt(
        organization_id,
        action=action,
        entity_type=entity_type,
        actor_user_id=actor_user_id,
        station_id=station_id,
        date_from=date_from,
        date_to=date_to,
    )
    stmt = await _apply_visibility_scope(db, stmt, current_user=current_user, organization_id=organization_id)
    stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    csv_rows = [
        {
            "created_at": r.created_at.isoformat(),
            "action": r.action,
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "actor_user_id": str(r.actor_user_id) if r.actor_user_id else "",
            "station_id": str(r.station_id) if r.station_id else "",
            "before": r.before,
            "after": r.after,
        }
        for r in rows
    ]
    return csv_response(
        "audit-log.csv",
        ["created_at", "action", "entity_type", "entity_id", "actor_user_id", "station_id", "before", "after"],
        csv_rows,
    )
