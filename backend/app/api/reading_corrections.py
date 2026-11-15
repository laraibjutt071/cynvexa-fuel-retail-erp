import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_shift_or_404
from app.api.deps import get_db, require_permission
from app.core.audit import write_audit_log
from app.core.permission_codes import READING_CORRECT, READING_CORRECT_APPROVE, SHIFT_READ
from app.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.models.reading_correction import (
    CORRECTION_WINDOW_HOURS,
    CorrectionStatus,
    ReadingCorrection,
    ReadingType,
)
from app.models.shift_nozzle_reading import ShiftNozzleReading
from app.models.shift_tank_reading import ShiftTankReading
from app.models.user import User
from app.schemas.reading_correction import (
    ReadingCorrectionDecision,
    ReadingCorrectionRead,
    ReadingCorrectionRequest,
)

router = APIRouter(
    prefix="/organizations/{organization_id}/stations/{station_id}/shifts/{shift_id}/reading-corrections",
    tags=["reading-corrections"],
)

ENTITY_TYPE = "ReadingCorrection"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _is_within_correction_window(submitted_at: datetime, now: datetime | None = None) -> bool:
    now = now or _now_utc()
    deadline = submitted_at + timedelta(hours=CORRECTION_WINDOW_HOURS)
    return now < deadline


def _get_original_value_and_timestamp(
    reading_type: ReadingType,
    tank_reading: ShiftTankReading | None,
    nozzle_reading: ShiftNozzleReading | None,
) -> tuple:
    if reading_type == ReadingType.TANK_DIP:
        if tank_reading is None:
            raise ValidationFailedError("tank_reading_id is required for tank_dip corrections.")
        return tank_reading.dip_reading, tank_reading.recorded_at

    if nozzle_reading is None:
        raise ValidationFailedError("nozzle_reading_id is required for nozzle reading corrections.")

    if reading_type == ReadingType.NOZZLE_OPENING:
        return nozzle_reading.opening_totalizer, nozzle_reading.opening_recorded_at
    elif reading_type == ReadingType.NOZZLE_CLOSING:
        if nozzle_reading.closing_totalizer is None:
            raise ValidationFailedError("No closing reading has been recorded yet.")
        return nozzle_reading.closing_totalizer, nozzle_reading.closing_recorded_at
    elif reading_type == ReadingType.METER_EVENT_PRE:
        if nozzle_reading.meter_event_pre_reading is None:
            raise ValidationFailedError("No meter event pre-reading exists.")
        return nozzle_reading.meter_event_pre_reading, nozzle_reading.closing_recorded_at
    elif reading_type == ReadingType.METER_EVENT_POST:
        if nozzle_reading.meter_event_post_reading is None:
            raise ValidationFailedError("No meter event post-reading exists.")
        return nozzle_reading.meter_event_post_reading, nozzle_reading.closing_recorded_at
    raise ValidationFailedError(f"Unknown reading type: {reading_type}")


async def _get_tank_reading_locked(
    db: AsyncSession, reading_id: uuid.UUID, shift_id: uuid.UUID
) -> ShiftTankReading:
    result = await db.execute(
        select(ShiftTankReading)
        .where(ShiftTankReading.id == reading_id, ShiftTankReading.shift_id == shift_id)
        .with_for_update()
    )
    reading = result.scalar_one_or_none()
    if reading is None:
        raise NotFoundError("Tank reading not found on this shift.")
    return reading


async def _get_nozzle_reading_locked(
    db: AsyncSession, reading_id: uuid.UUID, shift_id: uuid.UUID
) -> ShiftNozzleReading:
    result = await db.execute(
        select(ShiftNozzleReading)
        .where(ShiftNozzleReading.id == reading_id, ShiftNozzleReading.shift_id == shift_id)
        .with_for_update()
    )
    reading = result.scalar_one_or_none()
    if reading is None:
        raise NotFoundError("Nozzle reading not found on this shift.")
    return reading


@router.post("", response_model=ReadingCorrectionRead, status_code=201)
async def request_reading_correction(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    shift_id: uuid.UUID,
    payload: ReadingCorrectionRequest,
    request: Request,
    current_user: User = Depends(require_permission(READING_CORRECT)),
    db: AsyncSession = Depends(get_db),
) -> ReadingCorrection:
    shift = await get_shift_or_404(db, station_id, shift_id, for_update=True)

    tank_reading = None
    nozzle_reading = None

    if payload.reading_type == ReadingType.TANK_DIP:
        if payload.tank_reading_id is None:
            raise ValidationFailedError("tank_reading_id is required for tank dip corrections.")
        tank_reading = await _get_tank_reading_locked(db, payload.tank_reading_id, shift_id)
    else:
        if payload.nozzle_reading_id is None:
            raise ValidationFailedError("nozzle_reading_id is required for nozzle corrections.")
        nozzle_reading = await _get_nozzle_reading_locked(db, payload.nozzle_reading_id, shift_id)

    original_value, submitted_at = _get_original_value_and_timestamp(
        payload.reading_type, tank_reading, nozzle_reading
    )

    if original_value == payload.corrected_value:
        raise ValidationFailedError("Corrected value is the same as the original value.")

    now = _now_utc()
    is_post_lock = not _is_within_correction_window(submitted_at, now)

    correction = ReadingCorrection(
        organization_id=organization_id,
        station_id=station_id,
        shift_id=shift_id,
        reading_type=payload.reading_type.value,
        tank_reading_id=payload.tank_reading_id if payload.reading_type == ReadingType.TANK_DIP else None,
        nozzle_reading_id=payload.nozzle_reading_id if payload.reading_type != ReadingType.TANK_DIP else None,
        original_value=original_value,
        corrected_value=payload.corrected_value,
        reason=payload.reason,
        original_submitted_at=submitted_at,
        is_post_lock=is_post_lock,
        status=CorrectionStatus.PENDING.value,
        requested_by_user_id=current_user.id,
        requested_at=now,
    )
    db.add(correction)
    await db.flush()

    await write_audit_log(
        db,
        action="reading_correction.request",
        entity_type=ENTITY_TYPE,
        entity_id=str(correction.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={
            "reading_type": correction.reading_type,
            "original_value": str(original_value),
            "corrected_value": str(payload.corrected_value),
            "is_post_lock": is_post_lock,
            "reason": payload.reason,
        },
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return correction


@router.get("", response_model=list[ReadingCorrectionRead])
async def list_reading_corrections(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    shift_id: uuid.UUID,
    current_user: User = Depends(require_permission(SHIFT_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[ReadingCorrection]:
    await get_shift_or_404(db, station_id, shift_id)
    result = await db.execute(
        select(ReadingCorrection).where(ReadingCorrection.shift_id == shift_id)
    )
    return list(result.scalars().all())


@router.post("/{correction_id}/approve", response_model=ReadingCorrectionRead)
async def approve_reading_correction(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    shift_id: uuid.UUID,
    correction_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_permission(READING_CORRECT_APPROVE)),
    db: AsyncSession = Depends(get_db),
) -> ReadingCorrection:
    correction = await _get_correction_locked(db, correction_id, shift_id)

    if correction.status != CorrectionStatus.PENDING.value:
        raise ConflictError(f"Correction is already '{correction.status}'.")

    now = _now_utc()

    if not correction.is_post_lock:
        within_window = _is_within_correction_window(correction.original_submitted_at, now)
        if not within_window:
            raise ConflictError(
                "The 24-hour correction window has expired since this request was made. "
                "This correction can no longer be applied as a direct edit. "
                "Please submit a new post-lock amendment request."
            )
        await _apply_correction_to_reading(db, correction)

    correction.status = CorrectionStatus.APPROVED.value
    correction.decided_by_user_id = current_user.id
    correction.decided_at = now
    await db.flush()

    await write_audit_log(
        db,
        action="reading_correction.approve",
        entity_type=ENTITY_TYPE,
        entity_id=str(correction.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={
            "is_post_lock": correction.is_post_lock,
            "original_value": str(correction.original_value),
            "corrected_value": str(correction.corrected_value),
        },
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return correction


@router.post("/{correction_id}/reject", response_model=ReadingCorrectionRead)
async def reject_reading_correction(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    shift_id: uuid.UUID,
    correction_id: uuid.UUID,
    payload: ReadingCorrectionDecision,
    request: Request,
    current_user: User = Depends(require_permission(READING_CORRECT_APPROVE)),
    db: AsyncSession = Depends(get_db),
) -> ReadingCorrection:
    correction = await _get_correction_locked(db, correction_id, shift_id)

    if correction.status != CorrectionStatus.PENDING.value:
        raise ConflictError(f"Correction is already '{correction.status}'.")

    now = _now_utc()
    correction.status = CorrectionStatus.REJECTED.value
    correction.decided_by_user_id = current_user.id
    correction.decided_at = now
    correction.rejection_reason = payload.rejection_reason
    await db.flush()

    await write_audit_log(
        db,
        action="reading_correction.reject",
        entity_type=ENTITY_TYPE,
        entity_id=str(correction.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={"rejection_reason": payload.rejection_reason},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return correction


async def _get_correction_locked(
    db: AsyncSession, correction_id: uuid.UUID, shift_id: uuid.UUID
) -> ReadingCorrection:
    result = await db.execute(
        select(ReadingCorrection)
        .where(ReadingCorrection.id == correction_id, ReadingCorrection.shift_id == shift_id)
        .with_for_update()
    )
    correction = result.scalar_one_or_none()
    if correction is None:
        raise NotFoundError("Reading correction not found.")
    return correction


async def _apply_correction_to_reading(db: AsyncSession, correction: ReadingCorrection) -> None:
    if correction.reading_type == ReadingType.TANK_DIP.value:
        reading = await _get_tank_reading_locked(db, correction.tank_reading_id, correction.shift_id)
        reading.dip_reading = correction.corrected_value

    elif correction.reading_type == ReadingType.NOZZLE_OPENING.value:
        reading = await _get_nozzle_reading_locked(db, correction.nozzle_reading_id, correction.shift_id)
        reading.opening_totalizer = correction.corrected_value

    elif correction.reading_type == ReadingType.NOZZLE_CLOSING.value:
        reading = await _get_nozzle_reading_locked(db, correction.nozzle_reading_id, correction.shift_id)
        reading.closing_totalizer = correction.corrected_value
        if reading.meter_event_type is None:
            reading.dispensed_litres = reading.closing_totalizer - reading.opening_totalizer
        else:
            segment_1 = reading.meter_event_pre_reading - reading.opening_totalizer
            segment_2 = reading.closing_totalizer - reading.meter_event_post_reading
            reading.dispensed_litres = segment_1 + segment_2

    elif correction.reading_type == ReadingType.METER_EVENT_PRE.value:
        reading = await _get_nozzle_reading_locked(db, correction.nozzle_reading_id, correction.shift_id)
        reading.meter_event_pre_reading = correction.corrected_value
        if reading.closing_totalizer is not None:
            segment_1 = correction.corrected_value - reading.opening_totalizer
            segment_2 = reading.closing_totalizer - reading.meter_event_post_reading
            reading.dispensed_litres = segment_1 + segment_2

    elif correction.reading_type == ReadingType.METER_EVENT_POST.value:
        reading = await _get_nozzle_reading_locked(db, correction.nozzle_reading_id, correction.shift_id)
        reading.meter_event_post_reading = correction.corrected_value
        if reading.closing_totalizer is not None:
            segment_1 = reading.meter_event_pre_reading - reading.opening_totalizer
            segment_2 = reading.closing_totalizer - correction.corrected_value
            reading.dispensed_litres = segment_1 + segment_2

    await db.flush()
