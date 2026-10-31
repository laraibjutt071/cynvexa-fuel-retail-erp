import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_station_or_404
from app.api.deps import get_db, require_permission
from app.core.permission_codes import NOZZLE_READ
from app.core.pricing import get_current_price
from app.models.dispenser import Dispenser
from app.models.fuel_grade import FuelGrade
from app.models.nozzle import Nozzle
from app.models.shift_nozzle_reading import ShiftNozzleReading
from app.models.tank import Tank
from app.models.user import User
from app.schemas.nozzle_overview import NozzleOverviewRead

router = APIRouter(prefix="/organizations/{organization_id}/stations/{station_id}/nozzles", tags=["nozzles"])


@router.get("", response_model=list[NozzleOverviewRead])
async def list_station_nozzle_overview(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    current_user: User = Depends(require_permission(NOZZLE_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[NozzleOverviewRead]:
    """
    Every nozzle at this station, across every dispenser, with enough
    context (tank/fuel-grade names, current price, last closing totalizer)
    for the Daily Entry workspace to render and pre-fill a reading row in
    one call - the per-dispenser `.../dispensers/{id}/nozzles` endpoint
    stays as the master-data CRUD surface; this is a read-only overview on
    top of it.
    """
    await get_station_or_404(db, organization_id, station_id)

    rows = (
        await db.execute(
            select(Nozzle, Dispenser, Tank, FuelGrade)
            .join(Dispenser, Dispenser.id == Nozzle.dispenser_id)
            .join(Tank, Tank.id == Nozzle.tank_id)
            .join(FuelGrade, FuelGrade.id == Tank.fuel_grade_id)
            .where(Dispenser.station_id == station_id)
            .order_by(Dispenser.code, Nozzle.code)
        )
    ).all()

    out: list[NozzleOverviewRead] = []
    for nozzle, dispenser, tank, grade in rows:
        last_reading = (
            await db.execute(
                select(ShiftNozzleReading)
                .where(
                    ShiftNozzleReading.nozzle_id == nozzle.id,
                    ShiftNozzleReading.closing_totalizer.is_not(None),
                )
                .order_by(ShiftNozzleReading.closing_recorded_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        price = await get_current_price(db, station_id=station_id, fuel_grade_id=grade.id)

        out.append(
            NozzleOverviewRead(
                nozzle_id=nozzle.id,
                nozzle_code=nozzle.code,
                dispenser_id=dispenser.id,
                dispenser_code=dispenser.code,
                tank_id=tank.id,
                tank_code=tank.code,
                fuel_grade_id=grade.id,
                fuel_grade_name=grade.name,
                last_closing_totalizer=last_reading.closing_totalizer if last_reading else None,
                current_price_per_litre=price.price_per_litre if price else None,
            )
        )
    return out
