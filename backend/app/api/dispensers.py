import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_station_or_404
from app.api.deps import get_db, require_permission
from app.core.audit import write_audit_log
from app.core.permission_codes import DISPENSER_MANAGE, DISPENSER_READ
from app.exceptions import ConflictError, NotFoundError
from app.models.dispenser import Dispenser
from app.models.user import User
from app.schemas.dispenser import DispenserCreate, DispenserRead, DispenserUpdate

router = APIRouter(
    prefix="/organizations/{organization_id}/stations/{station_id}/dispensers", tags=["dispensers"]
)


async def _get_dispenser_in_station_or_404(
    db: AsyncSession, station_id: uuid.UUID, dispenser_id: uuid.UUID
) -> Dispenser:
    dispenser = (
        await db.execute(
            select(Dispenser).where(Dispenser.id == dispenser_id, Dispenser.station_id == station_id)
        )
    ).scalar_one_or_none()
    if dispenser is None:
        raise NotFoundError("Dispenser not found.")
    return dispenser


@router.post("", response_model=DispenserRead, status_code=201)
async def create_dispenser(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    payload: DispenserCreate,
    request: Request,
    current_user: User = Depends(require_permission(DISPENSER_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> Dispenser:
    await get_station_or_404(db, organization_id, station_id)

    dispenser = Dispenser(station_id=station_id, **payload.model_dump())
    db.add(dispenser)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ConflictError(f"A dispenser with code '{payload.code}' already exists at this station.")

    await write_audit_log(
        db,
        action="dispenser.create",
        entity_type="Dispenser",
        entity_id=str(dispenser.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={"code": dispenser.code, "name": dispenser.name},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return dispenser


@router.get("", response_model=list[DispenserRead])
async def list_dispensers(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    current_user: User = Depends(require_permission(DISPENSER_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[Dispenser]:
    result = await db.execute(select(Dispenser).where(Dispenser.station_id == station_id))
    return list(result.scalars().all())


@router.get("/{dispenser_id}", response_model=DispenserRead)
async def get_dispenser(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    dispenser_id: uuid.UUID,
    current_user: User = Depends(require_permission(DISPENSER_READ)),
    db: AsyncSession = Depends(get_db),
) -> Dispenser:
    return await _get_dispenser_in_station_or_404(db, station_id, dispenser_id)


@router.patch("/{dispenser_id}", response_model=DispenserRead)
async def update_dispenser(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    dispenser_id: uuid.UUID,
    payload: DispenserUpdate,
    request: Request,
    current_user: User = Depends(require_permission(DISPENSER_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> Dispenser:
    dispenser = await _get_dispenser_in_station_or_404(db, station_id, dispenser_id)

    before = {"name": dispenser.name, "is_active": dispenser.is_active}
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(dispenser, field, value)
    await db.flush()
    after = {"name": dispenser.name, "is_active": dispenser.is_active}

    await write_audit_log(
        db,
        action="dispenser.update",
        entity_type="Dispenser",
        entity_id=str(dispenser.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        before=before,
        after=after,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return dispenser
