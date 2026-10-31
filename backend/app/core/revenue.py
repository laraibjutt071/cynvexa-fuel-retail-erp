import uuid
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pricing import get_current_price
from app.exceptions import ValidationFailedError
from app.models.fuel_price import FuelPrice
from app.models.nozzle import Nozzle
from app.models.shift import Shift
from app.models.shift_nozzle_reading import ShiftNozzleReading
from app.models.shift_price_change import ShiftPriceChange, ShiftPriceChangeReading
from app.models.tank import Tank

TWO_PLACES = Decimal("0.01")


def round_money(value: Decimal) -> Decimal:
    """
    The one rounding rule for every money figure this app computes:
    round-half-up to 2 decimal places, applied ONCE to a final total rather
    than to each line item before summing (summing exact, unrounded line
    items first is a deliberate choice to avoid compounding rounding error
    across many small litre segments - see docs/ASSUMPTIONS.md #20). This
    is a reasonable default, not an accounting determination: an
    accountant may require round-half-even ("banker's rounding") or
    per-line rounding instead, and that is still open.
    """
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


async def _nozzle_revenue(
    db: AsyncSession, shift: Shift, reading: ShiftNozzleReading, tank: Tank
) -> Decimal:
    if reading.dispensed_litres is None:
        return Decimal(0)

    price_changes = (
        await db.execute(
            select(ShiftPriceChange)
            .where(
                ShiftPriceChange.shift_id == shift.id,
                ShiftPriceChange.fuel_grade_id == tank.fuel_grade_id,
            )
            .order_by(ShiftPriceChange.effective_at)
        )
    ).scalars().all()

    # Only price changes that have a boundary reading for THIS specific
    # nozzle can be used to split ITS litres - a price change affecting the
    # grade but never read on this nozzle (e.g. require_price_change_reading
    # was off) cannot be placed on this nozzle's totalizer timeline at all.
    boundaries: list[tuple[Decimal, FuelPrice | None, FuelPrice]] = []
    for pc in price_changes:
        pc_reading = (
            await db.execute(
                select(ShiftPriceChangeReading).where(
                    ShiftPriceChangeReading.shift_price_change_id == pc.id,
                    ShiftPriceChangeReading.nozzle_id == reading.nozzle_id,
                )
            )
        ).scalar_one_or_none()
        if pc_reading is None:
            continue
        old_price = (
            (await db.execute(select(FuelPrice).where(FuelPrice.id == pc.old_price_id))).scalar_one_or_none()
            if pc.old_price_id
            else None
        )
        new_price = (await db.execute(select(FuelPrice).where(FuelPrice.id == pc.new_price_id))).scalar_one()
        boundaries.append((pc_reading.totalizer_reading, old_price, new_price))

    if not boundaries:
        price = await get_current_price(
            db, station_id=shift.station_id, fuel_grade_id=tank.fuel_grade_id, as_of=shift.opened_at
        )
        if price is None:
            raise ValidationFailedError(
                f"No fuel price is set for grade {tank.fuel_grade_id} at the time this shift opened - "
                "cannot compute expected revenue."
            )
        return reading.dispensed_litres * price.price_per_litre

    boundaries.sort(key=lambda b: b[0])

    first_old_price = boundaries[0][1]
    if first_old_price is None:
        raise ValidationFailedError(
            "The first mid-shift price change for this nozzle has no prior price on record - "
            "cannot determine what price applied before it."
        )

    points = [reading.opening_totalizer] + [b[0] for b in boundaries] + [reading.closing_totalizer]
    prices = [first_old_price.price_per_litre] + [b[2].price_per_litre for b in boundaries]

    total = Decimal(0)
    for i in range(len(prices)):
        segment_litres = points[i + 1] - points[i]
        if segment_litres < 0:
            raise ValidationFailedError(
                f"Price-change boundary readings for nozzle {reading.nozzle_id} are not in "
                "increasing order between the opening and closing totalizer."
            )
        total += segment_litres * prices[i]
    return total


async def _per_grade_revenue(db: AsyncSession, shift: Shift) -> dict[uuid.UUID, Decimal]:
    """Unrounded expected revenue for this shift, grouped by fuel grade.
    Shared by compute_expected_fuel_revenue (which sums everything into one
    unrounded total before its single rounding step) and
    compute_expected_fuel_revenue_by_grade (app/api/reports.py's daily
    sales report, which needs a per-grade breakdown)."""
    readings = (
        await db.execute(select(ShiftNozzleReading).where(ShiftNozzleReading.shift_id == shift.id))
    ).scalars().all()
    if not readings:
        return {}

    nozzles = (
        await db.execute(select(Nozzle).where(Nozzle.id.in_([r.nozzle_id for r in readings])))
    ).scalars().all()
    nozzle_by_id = {n.id: n for n in nozzles}

    tank_ids = {n.tank_id for n in nozzles}
    tanks = (await db.execute(select(Tank).where(Tank.id.in_(tank_ids)))).scalars().all()
    tank_by_id = {t.id: t for t in tanks}

    totals: dict[uuid.UUID, Decimal] = {}
    for reading in readings:
        nozzle = nozzle_by_id.get(reading.nozzle_id)
        if nozzle is None:
            continue
        tank = tank_by_id.get(nozzle.tank_id)
        if tank is None:
            continue
        amount = await _nozzle_revenue(db, shift, reading, tank)
        totals[tank.fuel_grade_id] = totals.get(tank.fuel_grade_id, Decimal(0)) + amount
    return totals


async def compute_expected_fuel_revenue(db: AsyncSession, shift: Shift) -> Decimal:
    """
    The only function that may compute a shift's expected fuel revenue.
    Sums every nozzle's revenue as exact (unrounded) Decimal, then rounds
    the total once - see round_money's docstring for why. Reads only
    ShiftNozzleReading/ShiftPriceChange/FuelPrice; never touches
    ShiftCashMovement or ShiftTender, so a deposit or expense can never
    leak into this figure - see app/core/reconciliation.py.
    """
    per_grade = await _per_grade_revenue(db, shift)
    return round_money(sum(per_grade.values(), Decimal(0)))


async def compute_expected_fuel_revenue_by_grade(db: AsyncSession, shift: Shift) -> dict[uuid.UUID, Decimal]:
    """Same inputs as compute_expected_fuel_revenue, broken out per fuel
    grade for the daily fuel sales report. Each grade's figure is rounded
    independently - these are report rows, not the shift's own
    reconciliation total, which deliberately rounds only once, after
    summing every grade's unrounded figure (see round_money's docstring)."""
    per_grade = await _per_grade_revenue(db, shift)
    return {grade_id: round_money(amount) for grade_id, amount in per_grade.items()}
