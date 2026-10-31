import uuid
from datetime import date, datetime, time, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import (
    get_nozzle_in_station_or_404,
    get_shift_or_404,
    get_station_or_404,
    get_tank_or_404,
)
from app.api.deps import get_db, require_permission
from app.core.audit import write_audit_log
from app.core.permission_codes import SHIFT_APPROVE, SHIFT_CLOSE, SHIFT_OPEN, SHIFT_READ
from app.core.stock import get_book_stock
from app.core.variance import compute_shift_tank_variance
from app.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.models.dispenser import Dispenser
from app.models.fuel_price import FuelPrice
from app.models.nozzle import Nozzle
from app.models.shift import Shift, ShiftStatus
from app.models.shift_exceptional_event import ShiftExceptionalEvent
from app.models.shift_nozzle_reading import ShiftNozzleReading
from app.models.shift_price_change import ShiftPriceChange, ShiftPriceChangeReading
from app.models.shift_reconciliation import ShiftReconciliation
from app.models.shift_tank_reading import ShiftTankReading, TankReadingType
from app.models.stock_ledger_entry import StockLedgerEntry, StockMovementType
from app.models.tank import Tank
from app.models.user import User
from app.schemas.shift import (
    ShiftApproveMeterEvent,
    ShiftCreate,
    ShiftExceptionalEventCreate,
    ShiftExceptionalEventRead,
    ShiftNozzleReadingClose,
    ShiftNozzleReadingOpen,
    ShiftNozzleReadingRead,
    ShiftPriceChangeCreate,
    ShiftPriceChangeRead,
    ShiftPriceChangeReadingCreate,
    ShiftPriceChangeReadingRead,
    ShiftRead,
    ShiftTankReadingCreate,
    ShiftTankReadingRead,
    ShiftVarianceReport,
    TankVarianceRead,
)

router = APIRouter(
    prefix="/organizations/{organization_id}/stations/{station_id}/shifts", tags=["shifts"]
)

ENTITY_TYPE = "Shift"


def _decimal_fields(obj, fields: list[str]) -> dict:
    return {f: (str(v) if isinstance(v := getattr(obj, f), Decimal) else v) for f in fields}


def _require_open(shift: Shift) -> None:
    if shift.status != ShiftStatus.OPEN.value:
        raise ConflictError(
            f"Shift is '{shift.status}', not '{ShiftStatus.OPEN.value}' - this action is no longer allowed."
        )


def _require_closed(shift: Shift) -> None:
    if shift.status != ShiftStatus.CLOSED.value:
        raise ConflictError(
            f"Shift is '{shift.status}', not '{ShiftStatus.CLOSED.value}' - this action requires a closed shift."
        )


# ---------------------------------------------------------------------------
# Shift lifecycle
# ---------------------------------------------------------------------------


@router.post("", response_model=ShiftRead, status_code=201)
async def open_shift(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    payload: ShiftCreate,
    request: Request,
    current_user: User = Depends(require_permission(SHIFT_OPEN)),
    db: AsyncSession = Depends(get_db),
) -> Shift:
    await get_station_or_404(db, organization_id, station_id)

    shift = Shift(
        organization_id=organization_id,
        station_id=station_id,
        label=payload.label,
        opened_by_user_id=current_user.id,
        status=ShiftStatus.OPEN.value,
    )
    db.add(shift)
    await db.flush()

    await write_audit_log(
        db,
        action="shift.open",
        entity_type=ENTITY_TYPE,
        entity_id=str(shift.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={"label": shift.label},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return shift


@router.get("", response_model=list[ShiftRead])
async def list_shifts(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    status: str | None = None,
    business_date: date | None = None,
    current_user: User = Depends(require_permission(SHIFT_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[Shift]:
    """
    `business_date` filters to shifts whose opened_at falls on that
    calendar date **in the station's own configured timezone**, not UTC -
    used by the frontend's Daily Entry workspace to find "today's shift"
    under this app's one-shift-per-business-day convention (see
    docs/ASSUMPTIONS.md) without inventing a separate "business day"
    entity server-side. Station.timezone defaults to "UTC" but is meant
    to hold a real IANA zone (e.g. "Asia/Karachi") - a station a few hours
    ahead of UTC would otherwise have a shift opened just after local
    midnight filed under the *previous* UTC calendar day, confusing an
    operator who picked "today" in their own local date picker.
    """
    stmt = select(Shift).where(Shift.station_id == station_id)
    if status is not None:
        stmt = stmt.where(Shift.status == status)
    if business_date is not None:
        station = await get_station_or_404(db, organization_id, station_id)
        try:
            station_tz = ZoneInfo(station.timezone)
        except ZoneInfoNotFoundError:
            station_tz = timezone.utc
        start_local = datetime.combine(business_date, time.min, tzinfo=station_tz)
        end_local = datetime.combine(business_date, time.max, tzinfo=station_tz)
        start = start_local.astimezone(timezone.utc)
        end = end_local.astimezone(timezone.utc)
        stmt = stmt.where(Shift.opened_at >= start, Shift.opened_at <= end)
    stmt = stmt.order_by(Shift.opened_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{shift_id}", response_model=ShiftRead)
async def get_shift(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    shift_id: uuid.UUID,
    current_user: User = Depends(require_permission(SHIFT_READ)),
    db: AsyncSession = Depends(get_db),
) -> Shift:
    return await get_shift_or_404(db, station_id, shift_id)


@router.get("/{shift_id}/tank-readings", response_model=list[ShiftTankReadingRead])
async def list_shift_tank_readings(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    shift_id: uuid.UUID,
    current_user: User = Depends(require_permission(SHIFT_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[ShiftTankReading]:
    await get_shift_or_404(db, station_id, shift_id)
    result = await db.execute(select(ShiftTankReading).where(ShiftTankReading.shift_id == shift_id))
    return list(result.scalars().all())


@router.get("/{shift_id}/nozzle-readings", response_model=list[ShiftNozzleReadingRead])
async def list_shift_nozzle_readings(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    shift_id: uuid.UUID,
    current_user: User = Depends(require_permission(SHIFT_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[ShiftNozzleReading]:
    await get_shift_or_404(db, station_id, shift_id)
    result = await db.execute(select(ShiftNozzleReading).where(ShiftNozzleReading.shift_id == shift_id))
    return list(result.scalars().all())


@router.get("/{shift_id}/exceptional-events", response_model=list[ShiftExceptionalEventRead])
async def list_shift_exceptional_events(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    shift_id: uuid.UUID,
    current_user: User = Depends(require_permission(SHIFT_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[ShiftExceptionalEvent]:
    await get_shift_or_404(db, station_id, shift_id)
    result = await db.execute(
        select(ShiftExceptionalEvent).where(ShiftExceptionalEvent.shift_id == shift_id)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Tank readings (opening / closing physical dip observations)
# ---------------------------------------------------------------------------


@router.post("/{shift_id}/tank-readings/opening", response_model=ShiftTankReadingRead, status_code=201)
async def record_opening_tank_reading(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    shift_id: uuid.UUID,
    payload: ShiftTankReadingCreate,
    request: Request,
    current_user: User = Depends(require_permission(SHIFT_OPEN)),
    db: AsyncSession = Depends(get_db),
) -> ShiftTankReading:
    return await _record_tank_reading(
        db, request, organization_id, station_id, shift_id, payload, TankReadingType.OPENING, current_user
    )


@router.post("/{shift_id}/tank-readings/closing", response_model=ShiftTankReadingRead, status_code=201)
async def record_closing_tank_reading(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    shift_id: uuid.UUID,
    payload: ShiftTankReadingCreate,
    request: Request,
    current_user: User = Depends(require_permission(SHIFT_CLOSE)),
    db: AsyncSession = Depends(get_db),
) -> ShiftTankReading:
    return await _record_tank_reading(
        db, request, organization_id, station_id, shift_id, payload, TankReadingType.CLOSING, current_user
    )


async def _record_tank_reading(
    db: AsyncSession,
    request: Request,
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    shift_id: uuid.UUID,
    payload: ShiftTankReadingCreate,
    reading_type: TankReadingType,
    current_user: User,
) -> ShiftTankReading:
    shift = await get_shift_or_404(db, station_id, shift_id, for_update=True)
    _require_open(shift)
    await get_tank_or_404(db, station_id, payload.tank_id)

    reading = ShiftTankReading(
        shift_id=shift_id,
        tank_id=payload.tank_id,
        reading_type=reading_type.value,
        dip_reading=payload.dip_reading,
        recorded_by_user_id=current_user.id,
    )
    db.add(reading)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ConflictError(f"A {reading_type.value} reading for this tank already exists on this shift.")

    await write_audit_log(
        db,
        action=f"shift.tank_reading.{reading_type.value}",
        entity_type=ENTITY_TYPE,
        entity_id=str(shift_id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={"tank_id": str(payload.tank_id), **_decimal_fields(reading, ["dip_reading"])},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return reading


# ---------------------------------------------------------------------------
# Nozzle totalizer readings
# ---------------------------------------------------------------------------


@router.post("/{shift_id}/nozzle-readings", response_model=ShiftNozzleReadingRead, status_code=201)
async def open_nozzle_reading(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    shift_id: uuid.UUID,
    payload: ShiftNozzleReadingOpen,
    request: Request,
    current_user: User = Depends(require_permission(SHIFT_OPEN)),
    db: AsyncSession = Depends(get_db),
) -> ShiftNozzleReading:
    shift = await get_shift_or_404(db, station_id, shift_id, for_update=True)
    _require_open(shift)
    await get_nozzle_in_station_or_404(db, station_id, payload.nozzle_id)

    reading = ShiftNozzleReading(
        shift_id=shift_id,
        nozzle_id=payload.nozzle_id,
        opening_totalizer=payload.opening_totalizer,
        opening_recorded_by_user_id=current_user.id,
    )
    db.add(reading)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ConflictError("An opening reading for this nozzle already exists on this shift.")

    await write_audit_log(
        db,
        action="shift.nozzle_reading.open",
        entity_type=ENTITY_TYPE,
        entity_id=str(shift_id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={
            "nozzle_id": str(payload.nozzle_id),
            **_decimal_fields(reading, ["opening_totalizer"]),
        },
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return reading


@router.patch(
    "/{shift_id}/nozzle-readings/{reading_id}/close", response_model=ShiftNozzleReadingRead
)
async def close_nozzle_reading(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    shift_id: uuid.UUID,
    reading_id: uuid.UUID,
    payload: ShiftNozzleReadingClose,
    request: Request,
    current_user: User = Depends(require_permission(SHIFT_CLOSE)),
    db: AsyncSession = Depends(get_db),
) -> ShiftNozzleReading:
    shift = await get_shift_or_404(db, station_id, shift_id, for_update=True)
    _require_open(shift)

    reading = (
        await db.execute(
            select(ShiftNozzleReading).where(
                ShiftNozzleReading.id == reading_id, ShiftNozzleReading.shift_id == shift_id
            )
        )
    ).scalar_one_or_none()
    if reading is None:
        raise NotFoundError("Nozzle reading not found on this shift.")
    if reading.closing_totalizer is not None:
        raise ConflictError("A closing reading has already been recorded for this nozzle.")

    if payload.meter_event_type is None:
        if payload.closing_totalizer < reading.opening_totalizer:
            raise ValidationFailedError(
                "closing_totalizer cannot be lower than opening_totalizer without an approved "
                "meter replacement, reset or rollover event - dispensed litres cannot be negative."
            )
        dispensed = payload.closing_totalizer - reading.opening_totalizer
    else:
        segment_1 = payload.meter_event_pre_reading - reading.opening_totalizer
        segment_2 = payload.closing_totalizer - payload.meter_event_post_reading
        if segment_1 < 0 or segment_2 < 0:
            raise ValidationFailedError(
                "Invalid meter event readings: both the pre-event segment "
                f"({segment_1}) and the post-event segment ({segment_2}) must be >= 0."
            )
        dispensed = segment_1 + segment_2

    reading.closing_totalizer = payload.closing_totalizer
    reading.closing_recorded_by_user_id = current_user.id
    reading.closing_recorded_at = datetime.now(timezone.utc)
    reading.dispensed_litres = dispensed
    reading.meter_event_type = payload.meter_event_type.value if payload.meter_event_type else None
    reading.meter_event_pre_reading = payload.meter_event_pre_reading
    reading.meter_event_post_reading = payload.meter_event_post_reading
    reading.meter_event_notes = payload.meter_event_notes
    await db.flush()

    await write_audit_log(
        db,
        action="shift.nozzle_reading.close",
        entity_type=ENTITY_TYPE,
        entity_id=str(shift_id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={
            "nozzle_reading_id": str(reading.id),
            "meter_event_type": reading.meter_event_type,
            **_decimal_fields(reading, ["closing_totalizer", "dispensed_litres"]),
        },
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return reading


@router.patch(
    "/{shift_id}/nozzle-readings/{reading_id}/approve-meter-event", response_model=ShiftNozzleReadingRead
)
async def approve_meter_event(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    shift_id: uuid.UUID,
    reading_id: uuid.UUID,
    payload: ShiftApproveMeterEvent,
    request: Request,
    current_user: User = Depends(require_permission(SHIFT_APPROVE)),
    db: AsyncSession = Depends(get_db),
) -> ShiftNozzleReading:
    await get_shift_or_404(db, station_id, shift_id)
    reading = (
        await db.execute(
            select(ShiftNozzleReading).where(
                ShiftNozzleReading.id == reading_id, ShiftNozzleReading.shift_id == shift_id
            )
        )
    ).scalar_one_or_none()
    if reading is None:
        raise NotFoundError("Nozzle reading not found on this shift.")
    if reading.meter_event_type is None:
        raise ValidationFailedError("This nozzle reading has no meter event to approve.")
    if reading.meter_event_approved_by_user_id is not None:
        raise ConflictError("This meter event has already been approved.")

    reading.meter_event_approved_by_user_id = current_user.id
    reading.meter_event_approved_at = datetime.now(timezone.utc)
    await db.flush()

    await write_audit_log(
        db,
        action="shift.nozzle_reading.approve_meter_event",
        entity_type=ENTITY_TYPE,
        entity_id=str(shift_id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={"nozzle_reading_id": str(reading.id), "meter_event_type": reading.meter_event_type},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return reading


# ---------------------------------------------------------------------------
# Exceptional litres (test draws / calibration)
# ---------------------------------------------------------------------------


@router.post("/{shift_id}/exceptional-events", response_model=ShiftExceptionalEventRead, status_code=201)
async def record_exceptional_event(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    shift_id: uuid.UUID,
    payload: ShiftExceptionalEventCreate,
    request: Request,
    current_user: User = Depends(require_permission(SHIFT_CLOSE)),
    db: AsyncSession = Depends(get_db),
) -> ShiftExceptionalEvent:
    shift = await get_shift_or_404(db, station_id, shift_id, for_update=True)
    _require_open(shift)
    await get_nozzle_in_station_or_404(db, station_id, payload.nozzle_id)

    event = ShiftExceptionalEvent(
        shift_id=shift_id,
        nozzle_id=payload.nozzle_id,
        event_type=payload.event_type.value,
        litres=payload.litres,
        reason=payload.reason,
        recorded_by_user_id=current_user.id,
    )
    db.add(event)
    await db.flush()

    await write_audit_log(
        db,
        action="shift.exceptional_event.create",
        entity_type=ENTITY_TYPE,
        entity_id=str(shift_id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={
            "nozzle_id": str(payload.nozzle_id),
            "event_type": event.event_type,
            **_decimal_fields(event, ["litres"]),
        },
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return event


# ---------------------------------------------------------------------------
# Mid-shift price changes + boundary readings
# ---------------------------------------------------------------------------


@router.post("/{shift_id}/price-changes", response_model=ShiftPriceChangeRead, status_code=201)
async def record_price_change(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    shift_id: uuid.UUID,
    payload: ShiftPriceChangeCreate,
    request: Request,
    current_user: User = Depends(require_permission(SHIFT_CLOSE)),
    db: AsyncSession = Depends(get_db),
) -> ShiftPriceChange:
    shift = await get_shift_or_404(db, station_id, shift_id, for_update=True)
    _require_open(shift)

    new_price = (
        await db.execute(
            select(FuelPrice).where(
                FuelPrice.id == payload.new_price_id,
                FuelPrice.station_id == station_id,
                FuelPrice.fuel_grade_id == payload.fuel_grade_id,
            )
        )
    ).scalar_one_or_none()
    if new_price is None:
        raise ValidationFailedError("new_price_id does not reference a price for this station and grade.")

    if payload.effective_at < shift.opened_at or payload.effective_at > datetime.now(timezone.utc):
        raise ValidationFailedError("effective_at must be within the shift's open period.")

    old_price = (
        await db.execute(
            select(FuelPrice)
            .where(
                FuelPrice.station_id == station_id,
                FuelPrice.fuel_grade_id == payload.fuel_grade_id,
                FuelPrice.effective_from < new_price.effective_from,
            )
            .order_by(FuelPrice.effective_from.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    price_change = ShiftPriceChange(
        shift_id=shift_id,
        fuel_grade_id=payload.fuel_grade_id,
        old_price_id=old_price.id if old_price else None,
        new_price_id=new_price.id,
        effective_at=payload.effective_at,
        recorded_by_user_id=current_user.id,
    )
    db.add(price_change)
    await db.flush()

    await write_audit_log(
        db,
        action="shift.price_change.create",
        entity_type=ENTITY_TYPE,
        entity_id=str(shift_id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={
            "fuel_grade_id": str(payload.fuel_grade_id),
            "old_price_id": str(old_price.id) if old_price else None,
            "new_price_id": str(new_price.id),
        },
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return price_change


@router.post(
    "/{shift_id}/price-changes/{price_change_id}/readings",
    response_model=ShiftPriceChangeReadingRead,
    status_code=201,
)
async def record_price_change_reading(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    shift_id: uuid.UUID,
    price_change_id: uuid.UUID,
    payload: ShiftPriceChangeReadingCreate,
    request: Request,
    current_user: User = Depends(require_permission(SHIFT_CLOSE)),
    db: AsyncSession = Depends(get_db),
) -> ShiftPriceChangeReading:
    shift = await get_shift_or_404(db, station_id, shift_id, for_update=True)
    _require_open(shift)

    price_change = (
        await db.execute(
            select(ShiftPriceChange).where(
                ShiftPriceChange.id == price_change_id, ShiftPriceChange.shift_id == shift_id
            )
        )
    ).scalar_one_or_none()
    if price_change is None:
        raise NotFoundError("Price change not found on this shift.")
    await get_nozzle_in_station_or_404(db, station_id, payload.nozzle_id)

    reading = ShiftPriceChangeReading(
        shift_price_change_id=price_change_id,
        nozzle_id=payload.nozzle_id,
        totalizer_reading=payload.totalizer_reading,
        recorded_by_user_id=current_user.id,
    )
    db.add(reading)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ConflictError("A boundary reading for this nozzle already exists for this price change.")

    await write_audit_log(
        db,
        action="shift.price_change_reading.create",
        entity_type=ENTITY_TYPE,
        entity_id=str(shift_id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={
            "price_change_id": str(price_change_id),
            "nozzle_id": str(payload.nozzle_id),
            **_decimal_fields(reading, ["totalizer_reading"]),
        },
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return reading


# ---------------------------------------------------------------------------
# Close / Approve
# ---------------------------------------------------------------------------


async def _active_station_tanks(db: AsyncSession, station_id: uuid.UUID) -> list[Tank]:
    result = await db.execute(
        select(Tank).where(Tank.station_id == station_id, Tank.is_active.is_(True))
    )
    return list(result.scalars().all())


async def _active_station_nozzles(db: AsyncSession, station_id: uuid.UUID) -> list[Nozzle]:
    result = await db.execute(
        select(Nozzle)
        .join(Dispenser, Dispenser.id == Nozzle.dispenser_id)
        .where(Dispenser.station_id == station_id, Nozzle.is_active.is_(True))
    )
    return list(result.scalars().all())


@router.patch("/{shift_id}/close", response_model=ShiftRead)
async def close_shift(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    shift_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_permission(SHIFT_CLOSE)),
    db: AsyncSession = Depends(get_db),
) -> Shift:
    shift = await get_shift_or_404(db, station_id, shift_id, for_update=True)
    _require_open(shift)
    station = await get_station_or_404(db, organization_id, station_id)

    active_tanks = await _active_station_tanks(db, station_id)
    tank_readings = (
        await db.execute(select(ShiftTankReading).where(ShiftTankReading.shift_id == shift_id))
    ).scalars().all()
    readings_by_tank: dict[uuid.UUID, set[str]] = {}
    for r in tank_readings:
        readings_by_tank.setdefault(r.tank_id, set()).add(r.reading_type)

    missing_tank_readings = [
        tank.code
        for tank in active_tanks
        if {TankReadingType.OPENING.value, TankReadingType.CLOSING.value}
        - readings_by_tank.get(tank.id, set())
    ]
    if missing_tank_readings:
        raise ValidationFailedError(
            "Missing opening and/or closing tank readings for: " + ", ".join(sorted(missing_tank_readings))
        )

    active_nozzles = await _active_station_nozzles(db, station_id)
    nozzle_readings = (
        await db.execute(select(ShiftNozzleReading).where(ShiftNozzleReading.shift_id == shift_id))
    ).scalars().all()
    readings_by_nozzle = {r.nozzle_id: r for r in nozzle_readings}

    missing_nozzle_readings = [
        str(nozzle.code)
        for nozzle in active_nozzles
        if nozzle.id not in readings_by_nozzle or readings_by_nozzle[nozzle.id].closing_totalizer is None
    ]
    if missing_nozzle_readings:
        raise ValidationFailedError(
            "Missing opening and/or closing totalizer readings for nozzles: "
            + ", ".join(sorted(missing_nozzle_readings))
        )

    if station.require_price_change_reading:
        price_changes = (
            await db.execute(select(ShiftPriceChange).where(ShiftPriceChange.shift_id == shift_id))
        ).scalars().all()
        for pc in price_changes:
            affected_tank_ids = {
                tank.id for tank in active_tanks if tank.fuel_grade_id == pc.fuel_grade_id
            }
            affected_nozzle_ids = {
                nozzle.id for nozzle in active_nozzles if nozzle.tank_id in affected_tank_ids
            }
            existing_readings = (
                await db.execute(
                    select(ShiftPriceChangeReading.nozzle_id).where(
                        ShiftPriceChangeReading.shift_price_change_id == pc.id
                    )
                )
            ).scalars().all()
            missing = affected_nozzle_ids - set(existing_readings)
            if missing:
                raise ValidationFailedError(
                    f"Price change {pc.id} is missing boundary totalizer readings for "
                    f"{len(missing)} nozzle(s) serving fuel grade {pc.fuel_grade_id}."
                )

    shift.status = ShiftStatus.CLOSED.value
    shift.closed_by_user_id = current_user.id
    shift.closed_at = datetime.now(timezone.utc)
    await db.flush()

    await write_audit_log(
        db,
        action="shift.close",
        entity_type=ENTITY_TYPE,
        entity_id=str(shift_id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={"status": shift.status},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return shift


@router.patch("/{shift_id}/approve", response_model=ShiftRead)
async def approve_shift(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    shift_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_permission(SHIFT_APPROVE)),
    db: AsyncSession = Depends(get_db),
) -> Shift:
    shift = await get_shift_or_404(db, station_id, shift_id, for_update=True)
    _require_closed(shift)

    nozzle_readings = (
        await db.execute(select(ShiftNozzleReading).where(ShiftNozzleReading.shift_id == shift_id))
    ).scalars().all()
    unapproved_meter_events = [
        r.id
        for r in nozzle_readings
        if r.meter_event_type is not None and r.meter_event_approved_by_user_id is None
    ]
    if unapproved_meter_events:
        raise ValidationFailedError(
            f"{len(unapproved_meter_events)} flagged meter event(s) must be approved before this "
            "shift can be approved."
        )

    # Financial reconciliation (Phase D) must be resolved before the shift's
    # final approval - per the blueprint's own phase ordering ("9. Tender
    # reconciliation" precedes "11. Approval and posting"). Checked after the
    # operational (meter-event) precondition above, so a shift with both
    # problems is told about the operational one first - it's the earlier
    # step in the real-world sequence.
    reconciliation = (
        await db.execute(select(ShiftReconciliation).where(ShiftReconciliation.shift_id == shift_id))
    ).scalar_one_or_none()
    if reconciliation is None:
        raise ValidationFailedError(
            "This shift has no financial reconciliation yet - record tenders, cash movements and "
            "the reconciliation itself before approving the shift."
        )
    if reconciliation.requires_authorization and reconciliation.authorized_by_user_id is None:
        raise ValidationFailedError(
            "This shift's reconciliation has a material discrepancy that has not yet been "
            "authorized."
        )

    nozzles = (
        await db.execute(select(Nozzle).where(Nozzle.id.in_([r.nozzle_id for r in nozzle_readings])))
    ).scalars().all()
    tank_by_nozzle = {n.id: n.tank_id for n in nozzles}

    exceptional_events = (
        await db.execute(select(ShiftExceptionalEvent).where(ShiftExceptionalEvent.shift_id == shift_id))
    ).scalars().all()

    dispensed_by_tank: dict[uuid.UUID, Decimal] = {}
    for r in nozzle_readings:
        tank_id = tank_by_nozzle[r.nozzle_id]
        dispensed_by_tank[tank_id] = dispensed_by_tank.get(tank_id, Decimal(0)) + (r.dispensed_litres or Decimal(0))

    exceptional_by_tank: dict[uuid.UUID, Decimal] = {}
    for e in exceptional_events:
        tank_id = tank_by_nozzle.get(e.nozzle_id)
        if tank_id is None:
            continue
        exceptional_by_tank[tank_id] = exceptional_by_tank.get(tank_id, Decimal(0)) + e.litres

    ledger_entries = []
    for tank_id, total_dispensed in dispensed_by_tank.items():
        exceptional_qty = exceptional_by_tank.get(tank_id, Decimal(0))
        if exceptional_qty > total_dispensed:
            raise ValidationFailedError(
                f"Exceptional litres ({exceptional_qty}) exceed total dispensed litres "
                f"({total_dispensed}) for tank {tank_id} - cannot post a negative sale quantity."
            )
        sale_qty = total_dispensed - exceptional_qty

        tank = await get_tank_or_404(db, station_id, tank_id, for_update=True)
        book_stock = await get_book_stock(db, tank.id)
        if total_dispensed > book_stock:
            raise ConflictError(
                f"Insufficient book stock in tank '{tank.code}': {book_stock} litres available, "
                f"but {total_dispensed} litres were dispensed this shift."
            )

        if sale_qty > 0:
            ledger_entries.append(
                StockLedgerEntry(
                    tank_id=tank_id,
                    movement_type=StockMovementType.SALE.value,
                    quantity=sale_qty,
                    reference_type=ENTITY_TYPE,
                    reference_id=shift.id,
                    created_by_user_id=current_user.id,
                )
            )
        if exceptional_qty > 0:
            ledger_entries.append(
                StockLedgerEntry(
                    tank_id=tank_id,
                    movement_type=StockMovementType.TEST_CALIBRATION.value,
                    quantity=exceptional_qty,
                    reference_type=ENTITY_TYPE,
                    reference_id=shift.id,
                    created_by_user_id=current_user.id,
                )
            )

    for entry in ledger_entries:
        db.add(entry)

    shift.status = ShiftStatus.APPROVED.value
    shift.approved_by_user_id = current_user.id
    shift.approved_at = datetime.now(timezone.utc)
    await db.flush()

    await write_audit_log(
        db,
        action="shift.approve",
        entity_type=ENTITY_TYPE,
        entity_id=str(shift_id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={
            "status": shift.status,
            "tanks_posted": [str(t) for t in dispensed_by_tank.keys()],
        },
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return shift


# ---------------------------------------------------------------------------
# Variance report
# ---------------------------------------------------------------------------


@router.get("/{shift_id}/variance", response_model=ShiftVarianceReport)
async def get_shift_variance(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    shift_id: uuid.UUID,
    current_user: User = Depends(require_permission(SHIFT_READ)),
    db: AsyncSession = Depends(get_db),
) -> ShiftVarianceReport:
    shift = await get_shift_or_404(db, station_id, shift_id)
    station = await get_station_or_404(db, organization_id, station_id)
    results = await compute_shift_tank_variance(db, shift, station)
    return ShiftVarianceReport(shift_id=shift_id, tanks=results)
