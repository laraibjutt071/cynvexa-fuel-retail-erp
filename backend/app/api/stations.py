import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_organization_or_404, get_station_or_404
from app.api.deps import get_db, require_permission
from app.core.audit import write_audit_log
from app.core.permission_codes import STATION_CREATE, STATION_READ, STATION_UPDATE
from app.exceptions import ConflictError
from app.models.station import Station
from app.models.user import User
from app.schemas.station import StationCreate, StationRead, StationUpdate

router = APIRouter(prefix="/organizations/{organization_id}/stations", tags=["stations"])


@router.post("", response_model=StationRead, status_code=201)
async def create_station(
    organization_id: uuid.UUID,
    payload: StationCreate,
    request: Request,
    current_user: User = Depends(require_permission(STATION_CREATE)),
    db: AsyncSession = Depends(get_db),
) -> Station:
    # Required even though require_permission already checked a role exists
    # in this org for ordinary users: a superuser bypasses that check
    # entirely and could otherwise insert a station under an organization_id
    # that doesn't exist, which the FK constraint would reject - but as the
    # ConflictError below, misreporting it as a duplicate code.
    await get_organization_or_404(db, organization_id)

    station = Station(organization_id=organization_id, **payload.model_dump())
    db.add(station)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ConflictError(f"A station with code '{payload.code}' already exists in this organization.")

    await write_audit_log(
        db,
        action="station.create",
        entity_type="Station",
        entity_id=str(station.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station.id,
        after={"name": station.name, "code": station.code},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return station


@router.get("", response_model=list[StationRead])
async def list_stations(
    organization_id: uuid.UUID,
    current_user: User = Depends(require_permission(STATION_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[Station]:
    result = await db.execute(select(Station).where(Station.organization_id == organization_id))
    return list(result.scalars().all())


@router.get("/{station_id}", response_model=StationRead)
async def get_station(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    current_user: User = Depends(require_permission(STATION_READ)),
    db: AsyncSession = Depends(get_db),
) -> Station:
    return await get_station_or_404(db, organization_id, station_id)


@router.patch("/{station_id}", response_model=StationRead)
async def update_station(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    payload: StationUpdate,
    request: Request,
    current_user: User = Depends(require_permission(STATION_UPDATE)),
    db: AsyncSession = Depends(get_db),
) -> Station:
    station = await get_station_or_404(db, organization_id, station_id)
    update_data = payload.model_dump(exclude_unset=True)
    # Snapshot only the fields actually being changed, not a hand-maintained
    # list - a new StationUpdate field is then audited correctly for free.
    before = {field: getattr(station, field) for field in update_data}

    for field, value in update_data.items():
        setattr(station, field, value)
    await db.flush()

    after = {field: getattr(station, field) for field in update_data}
    before = {k: str(v) if isinstance(v, Decimal) else v for k, v in before.items()}
    after = {k: str(v) if isinstance(v, Decimal) else v for k, v in after.items()}
    await write_audit_log(
        db,
        action="station.update",
        entity_type="Station",
        entity_id=str(station.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station.id,
        before=before,
        after=after,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return station
