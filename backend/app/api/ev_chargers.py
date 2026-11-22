import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_ev_charger_or_404, get_station_or_404
from app.api.deps import get_db, require_permission
from app.core.audit import write_audit_log
from app.core.permission_codes import EV_CHARGER_MANAGE, EV_CHARGER_READ
from app.exceptions import ConflictError, NotFoundError
from app.models.ev_charger import EVCharger, EVChargerPort
from app.models.user import User
from app.schemas.ev_charger import (
    EVChargerCreate,
    EVChargerPortCreate,
    EVChargerPortRead,
    EVChargerPortUpdate,
    EVChargerRead,
    EVChargerUpdate,
)

router = APIRouter(
    prefix="/organizations/{organization_id}/stations/{station_id}/ev-chargers", tags=["ev-chargers"]
)


async def _get_port_or_404(db: AsyncSession, charger_id: uuid.UUID, port_id: uuid.UUID) -> EVChargerPort:
    port = (
        await db.execute(
            select(EVChargerPort).where(EVChargerPort.id == port_id, EVChargerPort.charger_id == charger_id)
        )
    ).scalar_one_or_none()
    if port is None:
        raise NotFoundError("EV charger port not found on this charger.")
    return port


@router.post("", response_model=EVChargerRead, status_code=201)
async def create_ev_charger(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    payload: EVChargerCreate,
    request: Request,
    current_user: User = Depends(require_permission(EV_CHARGER_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> EVCharger:
    await get_station_or_404(db, organization_id, station_id)

    charger = EVCharger(
        station_id=station_id,
        **payload.model_dump(exclude={"charger_type"}),
        charger_type=payload.charger_type.value,
    )
    db.add(charger)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ConflictError(f"An EV charger with code '{payload.code}' already exists at this station.")

    await write_audit_log(
        db,
        action="ev_charger.create",
        entity_type="EVCharger",
        entity_id=str(charger.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={"code": charger.code, "label": charger.label, "charger_type": charger.charger_type},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return charger


@router.get("", response_model=list[EVChargerRead])
async def list_ev_chargers(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    current_user: User = Depends(require_permission(EV_CHARGER_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[EVCharger]:
    result = await db.execute(select(EVCharger).where(EVCharger.station_id == station_id))
    return list(result.scalars().all())


@router.get("/{charger_id}", response_model=EVChargerRead)
async def get_ev_charger(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    charger_id: uuid.UUID,
    current_user: User = Depends(require_permission(EV_CHARGER_READ)),
    db: AsyncSession = Depends(get_db),
) -> EVCharger:
    return await get_ev_charger_or_404(db, station_id, charger_id)


@router.patch("/{charger_id}", response_model=EVChargerRead)
async def update_ev_charger(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    charger_id: uuid.UUID,
    payload: EVChargerUpdate,
    request: Request,
    current_user: User = Depends(require_permission(EV_CHARGER_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> EVCharger:
    charger = await get_ev_charger_or_404(db, station_id, charger_id)
    before = {"label": charger.label, "is_active": charger.is_active}
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(charger, field, value)
    await db.flush()
    after = {"label": charger.label, "is_active": charger.is_active}

    await write_audit_log(
        db,
        action="ev_charger.update",
        entity_type="EVCharger",
        entity_id=str(charger.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        before=before,
        after=after,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return charger


# ---------------------------------------------------------------------------
# Ports
# ---------------------------------------------------------------------------


@router.post("/{charger_id}/ports", response_model=EVChargerPortRead, status_code=201)
async def create_ev_charger_port(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    charger_id: uuid.UUID,
    payload: EVChargerPortCreate,
    request: Request,
    current_user: User = Depends(require_permission(EV_CHARGER_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> EVChargerPort:
    await get_ev_charger_or_404(db, station_id, charger_id)

    port = EVChargerPort(charger_id=charger_id, **payload.model_dump())
    db.add(port)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ConflictError(f"A port with code '{payload.port_code}' already exists on this charger.")

    await write_audit_log(
        db,
        action="ev_charger_port.create",
        entity_type="EVChargerPort",
        entity_id=str(port.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={"charger_id": str(charger_id), "port_code": port.port_code},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return port


@router.get("/{charger_id}/ports", response_model=list[EVChargerPortRead])
async def list_ev_charger_ports(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    charger_id: uuid.UUID,
    current_user: User = Depends(require_permission(EV_CHARGER_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[EVChargerPort]:
    await get_ev_charger_or_404(db, station_id, charger_id)
    result = await db.execute(select(EVChargerPort).where(EVChargerPort.charger_id == charger_id))
    return list(result.scalars().all())


@router.patch("/{charger_id}/ports/{port_id}", response_model=EVChargerPortRead)
async def update_ev_charger_port(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    charger_id: uuid.UUID,
    port_id: uuid.UUID,
    payload: EVChargerPortUpdate,
    request: Request,
    current_user: User = Depends(require_permission(EV_CHARGER_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> EVChargerPort:
    await get_ev_charger_or_404(db, station_id, charger_id)
    port = await _get_port_or_404(db, charger_id, port_id)

    before = {"status": port.status, "is_active": port.is_active}
    update_data = payload.model_dump(exclude_unset=True)
    if "status" in update_data and update_data["status"] is not None:
        update_data["status"] = update_data["status"].value if hasattr(update_data["status"], "value") else update_data["status"]
    for field, value in update_data.items():
        setattr(port, field, value)
    await db.flush()
    after = {"status": port.status, "is_active": port.is_active}

    await write_audit_log(
        db,
        action="ev_charger_port.update",
        entity_type="EVChargerPort",
        entity_id=str(port.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        before=before,
        after=after,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return port
