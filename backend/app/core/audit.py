import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


async def write_audit_log(
    db: AsyncSession,
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    actor_user_id: uuid.UUID | None,
    organization_id: uuid.UUID | None = None,
    station_id: uuid.UUID | None = None,
    before: dict | None = None,
    after: dict | None = None,
    ip_address: str | None = None,
) -> None:
    """
    Adds the AuditLog row to the current session WITHOUT committing. Callers must
    commit the mutation and this row together (same transaction, same db.commit()),
    so a failed mutation can never leave an audit entry and vice versa.

    Pass station_id whenever the event is about one specific station (a
    station create/update, or a role grant/revoke scoped to a station) -
    leaving it None for events with no natural station (org profile change,
    user account creation) is correct, not an oversight: see
    app/api/audit.py for how readers are filtered by it.
    """
    db.add(
        AuditLog(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_user_id=actor_user_id,
            organization_id=organization_id,
            station_id=station_id,
            before=before,
            after=after,
            ip_address=ip_address,
        )
    )
