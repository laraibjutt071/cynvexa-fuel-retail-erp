import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_shift_or_404, get_station_or_404
from app.api.deps import get_db, require_permission
from app.core.audit import write_audit_log
from app.core.permission_codes import SHIFT_READ, SHIFT_RECONCILE_APPROVE, SHIFT_RECONCILE_RECORD
from app.core.reconciliation import compute_expected_physical_cash, get_total_tender_amount, get_unapproved_decreasing_movements
from app.core.revenue import compute_expected_fuel_revenue, round_money
from app.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.models.shift import ShiftStatus
from app.models.shift_reconciliation import (
    AmendmentStatus,
    ShiftReconciliation,
    ShiftReconciliationAmendment,
)
from app.models.user import User
from app.schemas.shift_reconciliation import (
    ShiftReconciliationAmendmentCreate,
    ShiftReconciliationAmendmentDecide,
    ShiftReconciliationAmendmentRead,
    ShiftReconciliationAuthorize,
    ShiftReconciliationCreate,
    ShiftReconciliationRead,
)

router = APIRouter(
    prefix="/organizations/{organization_id}/stations/{station_id}/shifts/{shift_id}/reconciliation",
    tags=["shift-reconciliation"],
)

# Only these fields may ever be amended - the derived/computed facts
# (expected_fuel_revenue, total_tender_amount, expected_physical_cash) are
# never hand-edited; if one of those is wrong, the underlying tender or
# cash movement must be reversed and re-entered instead, which then shows
# up as a NEW reconciliation input, not a retroactive edit of this one.
AMENDABLE_FIELDS = {"actual_physical_cash", "explanation"}


def _decimal_fields(obj, fields: list[str]) -> dict:
    return {f: (str(v) if isinstance(v := getattr(obj, f), Decimal) else v) for f in fields}


async def _get_reconciliation_or_404(db: AsyncSession, shift_id: uuid.UUID) -> ShiftReconciliation:
    recon = (
        await db.execute(select(ShiftReconciliation).where(ShiftReconciliation.shift_id == shift_id))
    ).scalar_one_or_none()
    if recon is None:
        raise NotFoundError("No reconciliation has been recorded for this shift yet.")
    return recon


@router.post("", response_model=ShiftReconciliationRead, status_code=201)
async def create_reconciliation(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    shift_id: uuid.UUID,
    payload: ShiftReconciliationCreate,
    request: Request,
    current_user: User = Depends(require_permission(SHIFT_RECONCILE_RECORD)),
    db: AsyncSession = Depends(get_db),
) -> ShiftReconciliation:
    shift = await get_shift_or_404(db, station_id, shift_id)
    if shift.status != ShiftStatus.CLOSED.value:
        raise ConflictError(
            f"Shift is '{shift.status}', not '{ShiftStatus.CLOSED.value}' - readings must be final "
            "before reconciliation can be computed."
        )

    existing = (
        await db.execute(select(ShiftReconciliation).where(ShiftReconciliation.shift_id == shift_id))
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError("A reconciliation already exists for this shift.")

    pending = await get_unapproved_decreasing_movements(db, shift_id)
    if pending:
        raise ValidationFailedError(
            f"{len(pending)} cash movement(s) (expense/deposit/transfer/refund) are still awaiting "
            "approval - they must be approved or reversed before reconciliation can be computed."
        )

    station = await get_station_or_404(db, organization_id, station_id)

    expected_fuel_revenue = await compute_expected_fuel_revenue(db, shift)
    total_tender_amount = await get_total_tender_amount(db, shift_id)
    revenue_variance = round_money(total_tender_amount - expected_fuel_revenue)
    if expected_fuel_revenue == 0:
        revenue_variance_percent = Decimal("0")
        revenue_within_tolerance = revenue_variance == 0
    else:
        revenue_variance_percent = (revenue_variance / expected_fuel_revenue * 100).quantize(Decimal("0.001"))
        revenue_within_tolerance = abs(revenue_variance_percent) <= station.revenue_variance_tolerance_percent

    expected_physical_cash = await compute_expected_physical_cash(db, shift_id)
    cash_shortage_excess = round_money(payload.actual_physical_cash - expected_physical_cash)
    cash_within_tolerance = abs(cash_shortage_excess) <= station.cash_variance_tolerance_amount

    requires_authorization = not (revenue_within_tolerance and cash_within_tolerance)
    if requires_authorization and not payload.explanation:
        raise ValidationFailedError(
            "An explanation is required: this reconciliation has a material discrepancy "
            f"(revenue variance {revenue_variance_percent}%, cash {cash_shortage_excess})."
        )

    reconciliation = ShiftReconciliation(
        shift_id=shift_id,
        expected_fuel_revenue=expected_fuel_revenue,
        total_tender_amount=total_tender_amount,
        revenue_variance=revenue_variance,
        revenue_variance_percent=revenue_variance_percent,
        revenue_within_tolerance=revenue_within_tolerance,
        expected_physical_cash=expected_physical_cash,
        actual_physical_cash=payload.actual_physical_cash,
        cash_shortage_excess=cash_shortage_excess,
        cash_within_tolerance=cash_within_tolerance,
        requires_authorization=requires_authorization,
        explanation=payload.explanation,
        created_by_user_id=current_user.id,
    )
    db.add(reconciliation)
    await db.flush()

    await write_audit_log(
        db,
        action="shift_reconciliation.create",
        entity_type="Shift",
        entity_id=str(shift_id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={
            "requires_authorization": requires_authorization,
            **_decimal_fields(
                reconciliation,
                [
                    "expected_fuel_revenue",
                    "total_tender_amount",
                    "revenue_variance",
                    "expected_physical_cash",
                    "actual_physical_cash",
                    "cash_shortage_excess",
                ],
            ),
        },
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return reconciliation


@router.get("", response_model=ShiftReconciliationRead)
async def get_reconciliation(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    shift_id: uuid.UUID,
    current_user: User = Depends(require_permission(SHIFT_READ)),
    db: AsyncSession = Depends(get_db),
) -> ShiftReconciliation:
    await get_shift_or_404(db, station_id, shift_id)
    return await _get_reconciliation_or_404(db, shift_id)


@router.patch("/authorize", response_model=ShiftReconciliationRead)
async def authorize_reconciliation(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    shift_id: uuid.UUID,
    payload: ShiftReconciliationAuthorize,
    request: Request,
    current_user: User = Depends(require_permission(SHIFT_RECONCILE_APPROVE)),
    db: AsyncSession = Depends(get_db),
) -> ShiftReconciliation:
    await get_shift_or_404(db, station_id, shift_id)
    reconciliation = await _get_reconciliation_or_404(db, shift_id)
    if not reconciliation.requires_authorization:
        raise ValidationFailedError("This reconciliation is within tolerance and does not need authorization.")
    if reconciliation.authorized_by_user_id is not None:
        raise ConflictError("This reconciliation has already been authorized.")

    reconciliation.authorized_by_user_id = current_user.id
    reconciliation.authorized_at = datetime.now(timezone.utc)
    await db.flush()

    await write_audit_log(
        db,
        action="shift_reconciliation.authorize",
        entity_type="Shift",
        entity_id=str(shift_id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={"reconciliation_id": str(reconciliation.id)},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return reconciliation


# ---------------------------------------------------------------------------
# Amendments - the only way to correct an already-finalized reconciliation
# ---------------------------------------------------------------------------


@router.post("/amendments", response_model=ShiftReconciliationAmendmentRead, status_code=201)
async def request_amendment(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    shift_id: uuid.UUID,
    payload: ShiftReconciliationAmendmentCreate,
    request: Request,
    current_user: User = Depends(require_permission(SHIFT_RECONCILE_RECORD)),
    db: AsyncSession = Depends(get_db),
) -> ShiftReconciliationAmendment:
    await get_shift_or_404(db, station_id, shift_id)
    reconciliation = await _get_reconciliation_or_404(db, shift_id)

    if payload.field_name not in AMENDABLE_FIELDS:
        raise ValidationFailedError(
            f"'{payload.field_name}' cannot be amended. Amendable fields: {sorted(AMENDABLE_FIELDS)}."
        )

    previous_value = getattr(reconciliation, payload.field_name)
    amendment = ShiftReconciliationAmendment(
        reconciliation_id=reconciliation.id,
        field_name=payload.field_name,
        previous_value=str(previous_value) if previous_value is not None else "",
        new_value=payload.new_value,
        reason=payload.reason,
        status=AmendmentStatus.PENDING,
        requested_by_user_id=current_user.id,
    )
    db.add(amendment)
    await db.flush()

    await write_audit_log(
        db,
        action="shift_reconciliation_amendment.request",
        entity_type="Shift",
        entity_id=str(shift_id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        before={payload.field_name: amendment.previous_value},
        after={payload.field_name: amendment.new_value, "reason": amendment.reason},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return amendment


@router.get("/amendments", response_model=list[ShiftReconciliationAmendmentRead])
async def list_amendments(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    shift_id: uuid.UUID,
    current_user: User = Depends(require_permission(SHIFT_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[ShiftReconciliationAmendment]:
    await get_shift_or_404(db, station_id, shift_id)
    reconciliation = await _get_reconciliation_or_404(db, shift_id)
    result = await db.execute(
        select(ShiftReconciliationAmendment).where(
            ShiftReconciliationAmendment.reconciliation_id == reconciliation.id
        )
    )
    return list(result.scalars().all())


def _apply_amendment(reconciliation: ShiftReconciliation, amendment: ShiftReconciliationAmendment, station) -> None:
    if amendment.field_name == "explanation":
        reconciliation.explanation = amendment.new_value
        return

    # actual_physical_cash: recompute every figure that depends on it so the
    # record stays internally consistent. Prior authorization (who/when) is
    # left untouched - it remains a true record of what was approved at
    # that time; see docs/ASSUMPTIONS.md #23 for why this isn't auto-cleared.
    try:
        new_actual = Decimal(amendment.new_value)
    except InvalidOperation:
        raise ValidationFailedError("new_value for actual_physical_cash must be a decimal number.")
    reconciliation.actual_physical_cash = new_actual
    reconciliation.cash_shortage_excess = round_money(new_actual - reconciliation.expected_physical_cash)
    reconciliation.cash_within_tolerance = (
        abs(reconciliation.cash_shortage_excess) <= station.cash_variance_tolerance_amount
    )
    reconciliation.requires_authorization = not (
        reconciliation.revenue_within_tolerance and reconciliation.cash_within_tolerance
    )


@router.patch("/amendments/{amendment_id}/approve", response_model=ShiftReconciliationAmendmentRead)
async def approve_amendment(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    shift_id: uuid.UUID,
    amendment_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_permission(SHIFT_RECONCILE_APPROVE)),
    db: AsyncSession = Depends(get_db),
) -> ShiftReconciliationAmendment:
    await get_shift_or_404(db, station_id, shift_id)
    station = await get_station_or_404(db, organization_id, station_id)
    reconciliation = await _get_reconciliation_or_404(db, shift_id)

    amendment = (
        await db.execute(
            select(ShiftReconciliationAmendment).where(
                ShiftReconciliationAmendment.id == amendment_id,
                ShiftReconciliationAmendment.reconciliation_id == reconciliation.id,
            )
        )
    ).scalar_one_or_none()
    if amendment is None:
        raise NotFoundError("Amendment not found on this reconciliation.")
    if amendment.status != AmendmentStatus.PENDING:
        raise ConflictError(f"This amendment is already '{amendment.status}'.")

    _apply_amendment(reconciliation, amendment, station)
    amendment.status = AmendmentStatus.APPROVED
    amendment.decided_by_user_id = current_user.id
    amendment.decided_at = datetime.now(timezone.utc)
    await db.flush()

    await write_audit_log(
        db,
        action="shift_reconciliation_amendment.approve",
        entity_type="Shift",
        entity_id=str(shift_id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={"amendment_id": str(amendment.id), "field_name": amendment.field_name, "new_value": amendment.new_value},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return amendment


@router.patch("/amendments/{amendment_id}/reject", response_model=ShiftReconciliationAmendmentRead)
async def reject_amendment(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    shift_id: uuid.UUID,
    amendment_id: uuid.UUID,
    payload: ShiftReconciliationAmendmentDecide,
    request: Request,
    current_user: User = Depends(require_permission(SHIFT_RECONCILE_APPROVE)),
    db: AsyncSession = Depends(get_db),
) -> ShiftReconciliationAmendment:
    await get_shift_or_404(db, station_id, shift_id)
    reconciliation = await _get_reconciliation_or_404(db, shift_id)

    amendment = (
        await db.execute(
            select(ShiftReconciliationAmendment).where(
                ShiftReconciliationAmendment.id == amendment_id,
                ShiftReconciliationAmendment.reconciliation_id == reconciliation.id,
            )
        )
    ).scalar_one_or_none()
    if amendment is None:
        raise NotFoundError("Amendment not found on this reconciliation.")
    if amendment.status != AmendmentStatus.PENDING:
        raise ConflictError(f"This amendment is already '{amendment.status}'.")
    if not payload.rejection_reason:
        raise ValidationFailedError("rejection_reason is required to reject an amendment.")

    amendment.status = AmendmentStatus.REJECTED
    amendment.decided_by_user_id = current_user.id
    amendment.decided_at = datetime.now(timezone.utc)
    amendment.rejection_reason = payload.rejection_reason
    await db.flush()

    await write_audit_log(
        db,
        action="shift_reconciliation_amendment.reject",
        entity_type="Shift",
        entity_id=str(shift_id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={"amendment_id": str(amendment.id), "rejection_reason": payload.rejection_reason},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return amendment
