import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_shift_or_404
from app.api.deps import get_db, require_permission
from app.core.audit import write_audit_log
from app.core.permission_codes import SHIFT_READ, SHIFT_RECONCILE_APPROVE, SHIFT_RECONCILE_RECORD
from app.exceptions import ConflictError, NotFoundError
from app.models.shift import ShiftStatus
from app.models.shift_cash_movement import ShiftCashMovement
from app.models.user import User
from app.schemas.shift_cash_movement import (
    ShiftCashMovementCreate,
    ShiftCashMovementRead,
    ShiftCashMovementReverse,
)

router = APIRouter(
    prefix="/organizations/{organization_id}/stations/{station_id}/shifts/{shift_id}/cash-movements",
    tags=["shift-cash-movements"],
)


def _decimal_fields(obj, fields: list[str]) -> dict:
    return {f: (str(v) if isinstance(v := getattr(obj, f), Decimal) else v) for f in fields}


@router.post("", response_model=ShiftCashMovementRead, status_code=201)
async def record_cash_movement(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    shift_id: uuid.UUID,
    payload: ShiftCashMovementCreate,
    request: Request,
    current_user: User = Depends(require_permission(SHIFT_RECONCILE_RECORD)),
    db: AsyncSession = Depends(get_db),
) -> ShiftCashMovement:
    shift = await get_shift_or_404(db, station_id, shift_id)
    if shift.status == ShiftStatus.APPROVED.value:
        raise ConflictError("Shift is already approved - cash movements can no longer be recorded.")

    movement = ShiftCashMovement(
        shift_id=shift_id,
        movement_type=payload.movement_type.value,
        amount=payload.amount,
        reason=payload.reason,
        recorded_by_user_id=current_user.id,
    )
    db.add(movement)
    await db.flush()

    await write_audit_log(
        db,
        action="shift_cash_movement.create",
        entity_type="Shift",
        entity_id=str(shift_id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={
            "movement_id": str(movement.id),
            "movement_type": movement.movement_type,
            "reason": movement.reason,
            **_decimal_fields(movement, ["amount"]),
        },
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return movement


@router.get("", response_model=list[ShiftCashMovementRead])
async def list_cash_movements(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    shift_id: uuid.UUID,
    current_user: User = Depends(require_permission(SHIFT_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[ShiftCashMovement]:
    await get_shift_or_404(db, station_id, shift_id)
    result = await db.execute(select(ShiftCashMovement).where(ShiftCashMovement.shift_id == shift_id))
    return list(result.scalars().all())


@router.patch("/{movement_id}/approve", response_model=ShiftCashMovementRead)
async def approve_cash_movement(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    shift_id: uuid.UUID,
    movement_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_permission(SHIFT_RECONCILE_APPROVE)),
    db: AsyncSession = Depends(get_db),
) -> ShiftCashMovement:
    await get_shift_or_404(db, station_id, shift_id)
    movement = (
        await db.execute(
            select(ShiftCashMovement).where(
                ShiftCashMovement.id == movement_id, ShiftCashMovement.shift_id == shift_id
            )
        )
    ).scalar_one_or_none()
    if movement is None:
        raise NotFoundError("Cash movement not found on this shift.")
    if movement.approved_by_user_id is not None:
        raise ConflictError("This cash movement has already been approved.")
    if movement.reversed_at is not None:
        raise ConflictError("This cash movement has been reversed and can no longer be approved.")

    movement.approved_by_user_id = current_user.id
    movement.approved_at = datetime.now(timezone.utc)
    await db.flush()

    await write_audit_log(
        db,
        action="shift_cash_movement.approve",
        entity_type="Shift",
        entity_id=str(shift_id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={"movement_id": str(movement.id)},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return movement


@router.patch("/{movement_id}/reverse", response_model=ShiftCashMovementRead)
async def reverse_cash_movement(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    shift_id: uuid.UUID,
    movement_id: uuid.UUID,
    payload: ShiftCashMovementReverse,
    request: Request,
    current_user: User = Depends(require_permission(SHIFT_RECONCILE_APPROVE)),
    db: AsyncSession = Depends(get_db),
) -> ShiftCashMovement:
    """Allowed regardless of shift status - see shift_tenders.reverse_tender's
    docstring for why; the same reasoning applies here."""
    await get_shift_or_404(db, station_id, shift_id)
    movement = (
        await db.execute(
            select(ShiftCashMovement).where(
                ShiftCashMovement.id == movement_id, ShiftCashMovement.shift_id == shift_id
            )
        )
    ).scalar_one_or_none()
    if movement is None:
        raise NotFoundError("Cash movement not found on this shift.")
    if movement.reversed_at is not None:
        raise ConflictError("This cash movement has already been reversed.")

    movement.reversed_by_user_id = current_user.id
    movement.reversed_at = datetime.now(timezone.utc)
    movement.reversal_reason = payload.reason
    await db.flush()

    await write_audit_log(
        db,
        action="shift_cash_movement.reverse",
        entity_type="Shift",
        entity_id=str(shift_id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={"movement_id": str(movement.id), "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return movement
