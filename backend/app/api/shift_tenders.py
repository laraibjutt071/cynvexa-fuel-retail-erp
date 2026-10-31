import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import (
    get_credit_customer_or_404,
    get_payment_method_or_404,
    get_shift_or_404,
)
from app.api.deps import get_db, require_permission
from app.core.audit import write_audit_log
from app.core.permission_codes import SHIFT_READ, SHIFT_RECONCILE_APPROVE, SHIFT_RECONCILE_RECORD
from app.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.models.payment_method import PaymentMethodCategory
from app.models.shift import ShiftStatus
from app.models.shift_tender import ShiftTender
from app.models.user import User
from app.schemas.shift_tender import ShiftTenderCreate, ShiftTenderRead, ShiftTenderReverse

router = APIRouter(
    prefix="/organizations/{organization_id}/stations/{station_id}/shifts/{shift_id}/tenders",
    tags=["shift-tenders"],
)


def _decimal_fields(obj, fields: list[str]) -> dict:
    from decimal import Decimal

    return {f: (str(v) if isinstance(v := getattr(obj, f), Decimal) else v) for f in fields}


@router.post("", response_model=ShiftTenderRead, status_code=201)
async def record_tender(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    shift_id: uuid.UUID,
    payload: ShiftTenderCreate,
    request: Request,
    current_user: User = Depends(require_permission(SHIFT_RECONCILE_RECORD)),
    db: AsyncSession = Depends(get_db),
) -> ShiftTender:
    shift = await get_shift_or_404(db, station_id, shift_id)
    if shift.status == ShiftStatus.APPROVED.value:
        raise ConflictError("Shift is already approved - tenders can no longer be recorded.")

    method = await get_payment_method_or_404(db, organization_id, payload.payment_method_id)

    is_credit = method.category == PaymentMethodCategory.CREDIT.value
    if is_credit and payload.credit_customer_id is None:
        raise ValidationFailedError("credit_customer_id is required for a credit-category payment method.")
    if not is_credit and payload.credit_customer_id is not None:
        raise ValidationFailedError("credit_customer_id is only valid for a credit-category payment method.")
    if payload.credit_customer_id is not None:
        await get_credit_customer_or_404(db, organization_id, payload.credit_customer_id)

    tender = ShiftTender(
        shift_id=shift_id,
        payment_method_id=payload.payment_method_id,
        amount=payload.amount,
        credit_customer_id=payload.credit_customer_id,
        reference=payload.reference,
        recorded_by_user_id=current_user.id,
    )
    db.add(tender)
    await db.flush()

    await write_audit_log(
        db,
        action="shift_tender.create",
        entity_type="Shift",
        entity_id=str(shift_id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={
            "tender_id": str(tender.id),
            "payment_method_id": str(payload.payment_method_id),
            "category": method.category,
            **_decimal_fields(tender, ["amount"]),
        },
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return tender


@router.get("", response_model=list[ShiftTenderRead])
async def list_tenders(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    shift_id: uuid.UUID,
    current_user: User = Depends(require_permission(SHIFT_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[ShiftTender]:
    await get_shift_or_404(db, station_id, shift_id)
    result = await db.execute(select(ShiftTender).where(ShiftTender.shift_id == shift_id))
    return list(result.scalars().all())


@router.patch("/{tender_id}/reverse", response_model=ShiftTenderRead)
async def reverse_tender(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    shift_id: uuid.UUID,
    tender_id: uuid.UUID,
    payload: ShiftTenderReverse,
    request: Request,
    current_user: User = Depends(require_permission(SHIFT_RECONCILE_APPROVE)),
    db: AsyncSession = Depends(get_db),
) -> ShiftTender:
    """
    Reversal is intentionally allowed regardless of shift status - including
    after approval - per the "auditable amendments and reversals" requirement.
    The original row, and who recorded it, are never erased; a shift that is
    already approved is not automatically re-reconciled by this - if the
    correction is material, file a ShiftReconciliationAmendment referencing
    the new total. See docs/ASSUMPTIONS.md #23.
    """
    await get_shift_or_404(db, station_id, shift_id)
    tender = (
        await db.execute(select(ShiftTender).where(ShiftTender.id == tender_id, ShiftTender.shift_id == shift_id))
    ).scalar_one_or_none()
    if tender is None:
        raise NotFoundError("Tender not found on this shift.")
    if tender.reversed_at is not None:
        raise ConflictError("This tender has already been reversed.")

    tender.reversed_by_user_id = current_user.id
    tender.reversed_at = datetime.now(timezone.utc)
    tender.reversal_reason = payload.reason
    await db.flush()

    await write_audit_log(
        db,
        action="shift_tender.reverse",
        entity_type="Shift",
        entity_id=str(shift_id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={"tender_id": str(tender.id), "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return tender
