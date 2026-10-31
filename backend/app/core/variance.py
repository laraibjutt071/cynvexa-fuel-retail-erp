import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.stock import get_book_stock
from app.models.nozzle import Nozzle
from app.models.shift import Shift
from app.models.shift_nozzle_reading import ShiftNozzleReading
from app.models.shift_tank_reading import ShiftTankReading, TankReadingType
from app.models.station import Station
from app.models.tank import Tank
from app.schemas.shift import TankVarianceRead


async def compute_shift_tank_variance(
    db: AsyncSession, shift: Shift, station: Station
) -> list[TankVarianceRead]:
    """
    The one place that computes a shift's book-vs-physical tank variance -
    shared by the per-shift GET .../variance endpoint (app/api/shifts.py)
    and the cross-shift tank-variance report (app/api/reports.py), so the
    two can never drift apart.

    Book stock is projected from THIS shift's own dispensed total, not
    queried from the ledger "as of closed_at" - the ledger posting happens
    at approval time, chronologically after closed_at, so that query would
    always miss the shift's own postings. This projection is correct
    whether the shift is still open, closed-but-unapproved, or approved.
    """
    tank_readings = (
        await db.execute(select(ShiftTankReading).where(ShiftTankReading.shift_id == shift.id))
    ).scalars().all()
    readings_by_tank: dict[uuid.UUID, dict[str, Decimal]] = {}
    for r in tank_readings:
        readings_by_tank.setdefault(r.tank_id, {})[r.reading_type] = r.dip_reading

    nozzle_readings = (
        await db.execute(select(ShiftNozzleReading).where(ShiftNozzleReading.shift_id == shift.id))
    ).scalars().all()
    nozzle_ids = {r.nozzle_id for r in nozzle_readings}
    nozzles = (
        (await db.execute(select(Nozzle).where(Nozzle.id.in_(nozzle_ids)))).scalars().all()
        if nozzle_ids
        else []
    )
    tank_by_nozzle = {n.id: n.tank_id for n in nozzles}
    dispensed_by_tank: dict[uuid.UUID, Decimal] = {}
    for r in nozzle_readings:
        tank_id_for_nozzle = tank_by_nozzle.get(r.nozzle_id)
        if tank_id_for_nozzle is None:
            continue
        dispensed_by_tank[tank_id_for_nozzle] = dispensed_by_tank.get(
            tank_id_for_nozzle, Decimal(0)
        ) + (r.dispensed_litres or Decimal(0))

    results = []
    for tank_id, readings in readings_by_tank.items():
        tank = (
            await db.execute(select(Tank).where(Tank.id == tank_id, Tank.station_id == station.id))
        ).scalar_one_or_none()
        if tank is None:
            continue
        opening_book = await get_book_stock(db, tank_id, as_of=shift.opened_at)
        closing_book = opening_book - dispensed_by_tank.get(tank_id, Decimal(0))
        physical_opening = readings.get(TankReadingType.OPENING.value)
        physical_closing = readings.get(TankReadingType.CLOSING.value)

        opening_variance = physical_opening - opening_book if physical_opening is not None else None
        closing_variance = physical_closing - closing_book if physical_closing is not None else None
        closing_variance_percent = (
            (closing_variance / closing_book * 100)
            if closing_variance is not None and closing_book != 0
            else None
        )
        within_tolerance = (
            abs(closing_variance_percent) <= station.shift_variance_tolerance_percent
            if closing_variance_percent is not None
            else None
        )

        results.append(
            TankVarianceRead(
                tank_id=tank_id,
                tank_code=tank.code,
                opening_book_stock=opening_book,
                closing_book_stock=closing_book,
                physical_opening_reading=physical_opening,
                physical_closing_reading=physical_closing,
                opening_variance=opening_variance,
                closing_variance=closing_variance,
                closing_variance_percent=closing_variance_percent,
                within_tolerance=within_tolerance,
            )
        )

    return results
