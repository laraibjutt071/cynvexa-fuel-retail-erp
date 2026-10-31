import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_fuel_grade_or_404, get_organization_or_404, get_station_or_404
from app.api.deps import get_db, require_permission
from app.core.audit import write_audit_log
from app.core.permission_codes import FUEL_PRICE_CREATE, FUEL_PRICE_READ
from app.core.pricing import get_current_price
from app.exceptions import ConflictError, NotFoundError
from app.models.fuel_price import FuelPrice
from app.models.user import User
from app.schemas.fuel_price import FuelPriceCreate, FuelPriceRead

router = APIRouter(
    prefix="/organizations/{organization_id}/stations/{station_id}/fuel-prices", tags=["fuel-prices"]
)


@router.post("", response_model=FuelPriceRead, status_code=201)
async def create_fuel_price(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    payload: FuelPriceCreate,
    request: Request,
    current_user: User = Depends(require_permission(FUEL_PRICE_CREATE)),
    db: AsyncSession = Depends(get_db),
) -> FuelPrice:
    await get_station_or_404(db, organization_id, station_id)
    await get_fuel_grade_or_404(db, organization_id, payload.fuel_grade_id)

    price = FuelPrice(station_id=station_id, created_by_user_id=current_user.id, **payload.model_dump())
    db.add(price)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ConflictError(
            "A price for this fuel grade at this station is already effective from that exact timestamp."
        )

    await write_audit_log(
        db,
        action="fuel_price.create",
        entity_type="FuelPrice",
        entity_id=str(price.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={
            "fuel_grade_id": str(price.fuel_grade_id),
            "price_per_litre": str(price.price_per_litre),
            "effective_from": price.effective_from.isoformat(),
        },
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return price


@router.get("", response_model=list[FuelPriceRead])
async def list_fuel_prices(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    fuel_grade_id: uuid.UUID | None = None,
    current_user: User = Depends(require_permission(FUEL_PRICE_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[FuelPrice]:
    stmt = select(FuelPrice).where(FuelPrice.station_id == station_id)
    if fuel_grade_id is not None:
        stmt = stmt.where(FuelPrice.fuel_grade_id == fuel_grade_id)
    stmt = stmt.order_by(FuelPrice.effective_from.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/current", response_model=FuelPriceRead)
async def get_current_fuel_price(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    fuel_grade_id: uuid.UUID,
    current_user: User = Depends(require_permission(FUEL_PRICE_READ)),
    db: AsyncSession = Depends(get_db),
) -> FuelPrice:
    price = await get_current_price(db, station_id=station_id, fuel_grade_id=fuel_grade_id)
    if price is None:
        raise NotFoundError("No fuel price has been set for this grade at this station yet.")
    return price
