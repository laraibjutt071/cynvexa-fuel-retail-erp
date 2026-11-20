"""
Phase 8b: organization-wide (multi-station) aggregation. Every function
here sums or groups figures that a single-station report (app/api/reports.py)
already computes per shift/tank/record - never a parallel calculation of
its own. Station authorization is resolved once by the caller
(app/core/report_scope.py::resolve_authorized_station_ids) and handed in
as a concrete list of station_ids; nothing here re-derives visibility.
"""

import uuid
from datetime import date, datetime, time, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.revenue import compute_expected_fuel_revenue_by_grade
from app.core.stock import get_book_stock
from app.models.fuel_grade import FuelGrade
from app.models.payment_method import PaymentMethod
from app.models.shift import Shift, ShiftStatus
from app.models.shift_tank_reading import ShiftTankReading
from app.models.shift_tender import ShiftTender
from app.models.station import Station
from app.models.stock_ledger_entry import StockLedgerEntry, StockMovementType
from app.models.tank import Tank


async def approved_shifts_in_range(
    db: AsyncSession, station_ids: list[uuid.UUID], date_from: date, date_to: date
) -> list[Shift]:
    """Same rule as app/api/reports.py::_approved_shifts_in_range, extended
    to many stations at once - only ever APPROVED shifts count toward a
    sales/revenue figure anywhere in this app, and this is the one place
    that rule is now shared between the single- and multi-station paths."""
    if not station_ids:
        return []
    start = datetime.combine(date_from, time.min, tzinfo=timezone.utc)
    end = datetime.combine(date_to, time.max, tzinfo=timezone.utc)
    result = await db.execute(
        select(Shift).where(
            Shift.station_id.in_(station_ids),
            Shift.status == ShiftStatus.APPROVED.value,
            Shift.opened_at >= start,
            Shift.opened_at <= end,
        )
    )
    return list(result.scalars().all())


async def sales_by_grade_and_station(
    db: AsyncSession, shifts: list[Shift]
) -> tuple[dict[uuid.UUID, dict[str, Decimal]], dict[uuid.UUID, dict[str, Decimal]]]:
    """
    Returns (by_grade, by_station), each mapping id -> {"litres": Decimal,
    "revenue": Decimal}. Revenue per shift comes from
    compute_expected_fuel_revenue_by_grade (the one function allowed to
    compute it - app/core/revenue.py); litres come from the stock ledger's
    own SALE postings, exactly like app/api/reports.py's own daily sales
    report - both deliberately reuse the identical two sources so a
    station's number here can never drift from what its own single-station
    report shows for the same shifts.
    """
    by_grade: dict[uuid.UUID, dict[str, Decimal]] = {}
    by_station: dict[uuid.UUID, dict[str, Decimal]] = {}
    if not shifts:
        return by_grade, by_station

    shift_by_id = {s.id: s for s in shifts}
    for shift in shifts:
        per_grade_revenue = await compute_expected_fuel_revenue_by_grade(db, shift)
        total_shift_revenue = Decimal(0)
        for grade_id, revenue in per_grade_revenue.items():
            g = by_grade.setdefault(grade_id, {"litres": Decimal(0), "revenue": Decimal(0)})
            g["revenue"] += revenue
            total_shift_revenue += revenue
        s = by_station.setdefault(shift.station_id, {"litres": Decimal(0), "revenue": Decimal(0)})
        s["revenue"] += total_shift_revenue

    ledger_rows = (
        await db.execute(
            select(StockLedgerEntry.reference_id, StockLedgerEntry.quantity, Tank.fuel_grade_id, Tank.station_id)
            .join(Tank, Tank.id == StockLedgerEntry.tank_id)
            .where(
                StockLedgerEntry.reference_type == "Shift",
                StockLedgerEntry.reference_id.in_(list(shift_by_id.keys())),
                StockLedgerEntry.movement_type == StockMovementType.SALE.value,
            )
        )
    ).all()
    for shift_id, quantity, grade_id, station_id in ledger_rows:
        if shift_id not in shift_by_id:
            continue
        g = by_grade.setdefault(grade_id, {"litres": Decimal(0), "revenue": Decimal(0)})
        g["litres"] += quantity
        s = by_station.setdefault(station_id, {"litres": Decimal(0), "revenue": Decimal(0)})
        s["litres"] += quantity

    return by_grade, by_station


async def sales_by_day(db: AsyncSession, shifts: list[Shift]) -> dict[date, dict[str, Decimal]]:
    """
    Returns {date: {"litres": Decimal, "revenue": Decimal}}, bucketed by
    each shift's own opened_at date - using the identical two sources as
    sales_by_grade_and_station above (per-shift expected revenue via
    compute_expected_fuel_revenue_by_grade, litres via the stock ledger's
    own SALE postings), just grouped by day instead of by grade/station.
    A day with no shift simply has no key here; callers fill the gap with
    zero when building a display series, so a client-facing trend never
    silently skips a day.
    """
    by_day: dict[date, dict[str, Decimal]] = {}
    if not shifts:
        return by_day

    shift_by_id = {s.id: s for s in shifts}
    shift_day = {s.id: s.opened_at.date() for s in shifts}

    for shift in shifts:
        per_grade_revenue = await compute_expected_fuel_revenue_by_grade(db, shift)
        bucket = by_day.setdefault(shift_day[shift.id], {"litres": Decimal(0), "revenue": Decimal(0)})
        bucket["revenue"] += sum(per_grade_revenue.values(), Decimal(0))

    ledger_rows = (
        await db.execute(
            select(StockLedgerEntry.reference_id, StockLedgerEntry.quantity).where(
                StockLedgerEntry.reference_type == "Shift",
                StockLedgerEntry.reference_id.in_(list(shift_by_id.keys())),
                StockLedgerEntry.movement_type == StockMovementType.SALE.value,
            )
        )
    ).all()
    for shift_id, quantity in ledger_rows:
        if shift_id not in shift_by_id:
            continue
        bucket = by_day.setdefault(shift_day[shift_id], {"litres": Decimal(0), "revenue": Decimal(0)})
        bucket["litres"] += quantity

    return by_day


async def tender_totals_by_category_and_station(
    db: AsyncSession, shifts: list[Shift]
) -> tuple[dict[str, Decimal], dict[uuid.UUID, dict[str, Decimal]]]:
    """
    Returns (by_category, by_station): non-reversed ShiftTender amounts
    for the given shifts, grouped by PaymentMethod.category
    (cash/card/digital/credit - app/models/payment_method.py) and
    separately by station. This is "cash collected" territory, not
    revenue - see app/core/reconciliation.py's own docstring on the same
    distinction; callers must never add this to expected fuel revenue.
    """
    by_category: dict[str, Decimal] = {}
    by_station: dict[uuid.UUID, dict[str, Decimal]] = {}
    if not shifts:
        return by_category, by_station

    shift_station = {s.id: s.station_id for s in shifts}
    rows = (
        await db.execute(
            select(ShiftTender.shift_id, ShiftTender.amount, PaymentMethod.category)
            .join(PaymentMethod, PaymentMethod.id == ShiftTender.payment_method_id)
            .where(ShiftTender.shift_id.in_(list(shift_station.keys())), ShiftTender.reversed_at.is_(None))
        )
    ).all()
    for shift_id, amount, category in rows:
        by_category[category] = by_category.get(category, Decimal(0)) + amount
        station_id = shift_station[shift_id]
        bucket = by_station.setdefault(station_id, {"cash": Decimal(0), "card": Decimal(0), "digital": Decimal(0), "credit": Decimal(0), "total": Decimal(0)})
        bucket[category] = bucket.get(category, Decimal(0)) + amount
        bucket["total"] += amount
    return by_category, by_station


async def fuel_grade_names(db: AsyncSession, grade_ids: set[uuid.UUID]) -> dict[uuid.UUID, FuelGrade]:
    if not grade_ids:
        return {}
    rows = (await db.execute(select(FuelGrade).where(FuelGrade.id.in_(grade_ids)))).scalars().all()
    return {g.id: g for g in rows}


async def station_names(db: AsyncSession, station_ids: list[uuid.UUID]) -> dict[uuid.UUID, Station]:
    if not station_ids:
        return {}
    rows = (await db.execute(select(Station).where(Station.id.in_(station_ids)))).scalars().all()
    return {s.id: s for s in rows}


async def current_tank_stock(
    db: AsyncSession, station_ids: list[uuid.UUID]
) -> list[dict]:
    """
    Per-tank current book stock (app/core/stock.py::get_book_stock - the
    only function allowed to compute it) plus, separately, the most recent
    physical dip reading this tank has on record from any shift
    (ShiftTankReading, either opening or closing) and when it was taken.
    The two are returned as distinct fields and never combined into one
    figure - a physical dip is an observation, book stock is a ledger
    projection, and conflating them is exactly what this phase's brief
    forbids.
    """
    if not station_ids:
        return []
    tanks = (
        await db.execute(select(Tank).where(Tank.station_id.in_(station_ids), Tank.is_active.is_(True)))
    ).scalars().all()
    if not tanks:
        return []

    # Most recent ShiftTankReading per tank, across any shift - one query,
    # not one per tank.
    latest_reading_subq = (
        select(
            ShiftTankReading.tank_id,
            func.max(ShiftTankReading.recorded_at).label("latest_at"),
        )
        .where(ShiftTankReading.tank_id.in_([t.id for t in tanks]))
        .group_by(ShiftTankReading.tank_id)
        .subquery()
    )
    latest_readings = (
        await db.execute(
            select(ShiftTankReading)
            .join(
                latest_reading_subq,
                (ShiftTankReading.tank_id == latest_reading_subq.c.tank_id)
                & (ShiftTankReading.recorded_at == latest_reading_subq.c.latest_at),
            )
        )
    ).scalars().all()
    latest_by_tank: dict[uuid.UUID, ShiftTankReading] = {}
    for r in latest_readings:
        # Two readings (opening/closing) can share the same tank+timestamp
        # only in pathological test data - keep the first seen, deterministic
        # either way since both are "the latest moment we observed this tank".
        latest_by_tank.setdefault(r.tank_id, r)

    rows = []
    for tank in tanks:
        book_stock = await get_book_stock(db, tank.id)
        latest = latest_by_tank.get(tank.id)
        rows.append(
            {
                "tank": tank,
                "book_stock": book_stock,
                "last_physical_dip_reading": latest.dip_reading if latest else None,
                "last_physical_dip_at": latest.recorded_at if latest else None,
            }
        )
    return rows
