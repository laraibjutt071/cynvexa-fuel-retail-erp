"""
Phase 10a: a read-only, cross-shift history of flagged meter
rollover/reset/replacement events for a station. Every write path this
feeds from already existed (app/api/shifts.py's close_nozzle_reading and
approve_meter_event) - this is the one capability that genuinely didn't
exist yet (per the Phase 9 audit): there was no way to list meter events
across shifts, only within one shift's own nozzle-readings call.
"""

import uuid
from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_station_or_404
from app.api.deps import get_db, require_permission
from app.core.permission_codes import SHIFT_READ
from app.exceptions import ValidationFailedError
from app.models.dispenser import Dispenser
from app.models.fuel_grade import FuelGrade
from app.models.nozzle import Nozzle
from app.models.shift import Shift
from app.models.shift_nozzle_reading import MeterEventType, ShiftNozzleReading
from app.models.tank import Tank
from app.models.user import User
from app.schemas.meter_event import MeterEventRow

router = APIRouter(
    prefix="/organizations/{organization_id}/stations/{station_id}/meter-events", tags=["meter-events"]
)

MAX_HISTORY_DAYS = 366


@router.get("", response_model=list[MeterEventRow])
async def list_meter_events(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    event_type: MeterEventType | None = Query(default=None),
    approved: bool | None = Query(default=None, description="true = approved only, false = pending only, omit = both"),
    current_user: User = Depends(require_permission(SHIFT_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[MeterEventRow]:
    await get_station_or_404(db, organization_id, station_id)

    if date_from is not None and date_to is not None:
        if date_to < date_from:
            raise ValidationFailedError("date_to must not be before date_from.")
        if (date_to - date_from).days > MAX_HISTORY_DAYS:
            raise ValidationFailedError(f"Date range must not exceed {MAX_HISTORY_DAYS} days.")

    stmt = (
        select(ShiftNozzleReading, Shift, Nozzle, Dispenser, Tank, FuelGrade)
        .join(Shift, Shift.id == ShiftNozzleReading.shift_id)
        .join(Nozzle, Nozzle.id == ShiftNozzleReading.nozzle_id)
        .join(Dispenser, Dispenser.id == Nozzle.dispenser_id)
        .join(Tank, Tank.id == Nozzle.tank_id)
        .join(FuelGrade, FuelGrade.id == Tank.fuel_grade_id)
        .where(Shift.station_id == station_id, ShiftNozzleReading.meter_event_type.is_not(None))
        .order_by(Shift.opened_at.desc())
    )
    if date_from is not None:
        stmt = stmt.where(Shift.opened_at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
    if date_to is not None:
        stmt = stmt.where(Shift.opened_at <= datetime.combine(date_to, time.max, tzinfo=timezone.utc))
    if event_type is not None:
        stmt = stmt.where(ShiftNozzleReading.meter_event_type == event_type.value)
    if approved is True:
        stmt = stmt.where(ShiftNozzleReading.meter_event_approved_by_user_id.is_not(None))
    elif approved is False:
        stmt = stmt.where(ShiftNozzleReading.meter_event_approved_by_user_id.is_(None))

    rows = (await db.execute(stmt)).all()
    return [
        MeterEventRow(
            nozzle_reading_id=reading.id,
            shift_id=shift.id,
            shift_label=shift.label,
            shift_opened_at=shift.opened_at,
            shift_status=shift.status,
            station_id=station_id,
            nozzle_id=nozzle.id,
            nozzle_code=nozzle.code,
            dispenser_code=dispenser.code,
            tank_code=tank.code,
            fuel_grade_name=fuel_grade.name,
            event_type=reading.meter_event_type,
            opening_totalizer=reading.opening_totalizer,
            meter_event_pre_reading=reading.meter_event_pre_reading,
            meter_event_post_reading=reading.meter_event_post_reading,
            closing_totalizer=reading.closing_totalizer,
            dispensed_litres=reading.dispensed_litres,
            notes=reading.meter_event_notes,
            recorded_by_user_id=reading.closing_recorded_by_user_id,
            recorded_at=reading.closing_recorded_at,
            approved_by_user_id=reading.meter_event_approved_by_user_id,
            approved_at=reading.meter_event_approved_at,
        )
        for reading, shift, nozzle, dispenser, tank, fuel_grade in rows
    ]
