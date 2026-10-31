import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_fuel_grade_or_404, get_organization_or_404, get_station_or_404
from app.api.deps import get_db, require_permission
from app.core.audit import write_audit_log
from app.core.permission_codes import TANK_MANAGE, TANK_READ
from app.core.stock import get_book_stock
from app.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.models.tank import Tank
from app.models.user import User
from app.schemas.tank import TankCreate, TankRead, TankStockRead, TankUpdate

router = APIRouter(
    prefix="/organizations/{organization_id}/stations/{station_id}/tanks", tags=["tanks"]
)


async def _get_tank_in_station_or_404(db: AsyncSession, station_id: uuid.UUID, tank_id: uuid.UUID) -> Tank:
    tank = (
        await db.execute(select(Tank).where(Tank.id == tank_id, Tank.station_id == station_id))
    ).scalar_one_or_none()
    if tank is None:
        raise NotFoundError("Tank not found.")
    return tank


@router.post("", response_model=TankRead, status_code=201)
async def create_tank(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    payload: TankCreate,
    request: Request,
    current_user: User = Depends(require_permission(TANK_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> Tank:
    await get_station_or_404(db, organization_id, station_id)
    await get_fuel_grade_or_404(db, organization_id, payload.fuel_grade_id)

    tank = Tank(station_id=station_id, **payload.model_dump())
    db.add(tank)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ConflictError(f"A tank with code '{payload.code}' already exists at this station.")

    await write_audit_log(
        db,
        action="tank.create",
        entity_type="Tank",
        entity_id=str(tank.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={"code": tank.code, "capacity": str(tank.capacity), "safe_fill_limit": str(tank.safe_fill_limit)},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return tank


@router.get("", response_model=list[TankRead])
async def list_tanks(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    current_user: User = Depends(require_permission(TANK_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[Tank]:
    result = await db.execute(select(Tank).where(Tank.station_id == station_id))
    return list(result.scalars().all())


@router.get("/{tank_id}", response_model=TankStockRead)
async def get_tank(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    tank_id: uuid.UUID,
    current_user: User = Depends(require_permission(TANK_READ)),
    db: AsyncSession = Depends(get_db),
) -> TankStockRead:
    tank = await _get_tank_in_station_or_404(db, station_id, tank_id)
    book_stock = await get_book_stock(db, tank.id)
    return TankStockRead(
        **TankRead.model_validate(tank).model_dump(),
        book_stock=book_stock,
        safe_capacity_available=tank.safe_fill_limit - book_stock,
    )


@router.patch("/{tank_id}", response_model=TankRead)
async def update_tank(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    tank_id: uuid.UUID,
    payload: TankUpdate,
    request: Request,
    current_user: User = Depends(require_permission(TANK_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> Tank:
    tank = await _get_tank_in_station_or_404(db, station_id, tank_id)

    if payload.safe_fill_limit is not None and payload.safe_fill_limit > tank.capacity:
        raise ValidationFailedError("safe_fill_limit cannot exceed the tank's capacity.")

    before = {"name": tank.name, "safe_fill_limit": str(tank.safe_fill_limit), "is_active": tank.is_active}
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(tank, field, value)
    await db.flush()
    after = {"name": tank.name, "safe_fill_limit": str(tank.safe_fill_limit), "is_active": tank.is_active}

    await write_audit_log(
        db,
        action="tank.update",
        entity_type="Tank",
        entity_id=str(tank.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        before=before,
        after=after,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return tank
