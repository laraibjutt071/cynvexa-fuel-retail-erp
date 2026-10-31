import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_expense_or_404, get_organization_or_404, get_station_or_404
from app.api.deps import get_db, require_permission
from app.core.audit import write_audit_log
from app.core.permission_codes import EXPENSE_APPROVE, EXPENSE_READ, EXPENSE_RECORD
from app.core.permissions import get_station_visibility_scope
from app.exceptions import ConflictError
from app.models.expense import Expense, ExpenseStatus
from app.models.user import User
from app.schemas.expense import ExpenseCreate, ExpenseRead, ExpenseReject, ExpenseReverse

router = APIRouter(prefix="/organizations/{organization_id}/expenses", tags=["expenses"])


@router.post("", response_model=ExpenseRead, status_code=201)
async def create_expense(
    organization_id: uuid.UUID,
    payload: ExpenseCreate,
    request: Request,
    current_user: User = Depends(require_permission(EXPENSE_RECORD)),
    db: AsyncSession = Depends(get_db),
) -> Expense:
    await get_organization_or_404(db, organization_id)
    if payload.station_id is not None:
        await get_station_or_404(db, organization_id, payload.station_id)

    expense = Expense(
        organization_id=organization_id,
        created_by_user_id=current_user.id,
        **payload.model_dump(),
    )
    db.add(expense)
    await db.flush()

    await write_audit_log(
        db,
        action="expense.create",
        entity_type="Expense",
        entity_id=str(expense.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=expense.station_id,
        after={"amount": str(expense.amount), "category": expense.category},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return expense


@router.get("", response_model=list[ExpenseRead])
async def list_expenses(
    organization_id: uuid.UUID,
    status: str | None = Query(default=None),
    station_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(require_permission(EXPENSE_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[Expense]:
    stmt = select(Expense).where(Expense.organization_id == organization_id)
    if status is not None:
        stmt = stmt.where(Expense.status == status)
    if station_id is not None:
        stmt = stmt.where(Expense.station_id == station_id)

    if not current_user.is_superuser:
        visible_station_ids = await get_station_visibility_scope(
            db, user_id=current_user.id, organization_id=organization_id, permission_code=EXPENSE_READ
        )
        if visible_station_ids is not None:
            stmt = stmt.where(
                (Expense.station_id.is_(None)) | (Expense.station_id.in_(visible_station_ids))
            )

    stmt = stmt.order_by(Expense.expense_date.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.patch("/{expense_id}/approve", response_model=ExpenseRead)
async def approve_expense(
    organization_id: uuid.UUID,
    expense_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_permission(EXPENSE_APPROVE)),
    db: AsyncSession = Depends(get_db),
) -> Expense:
    expense = await get_expense_or_404(db, organization_id, expense_id, for_update=True)
    if expense.status != ExpenseStatus.PENDING.value:
        raise ConflictError(f"Expense is '{expense.status}', not '{ExpenseStatus.PENDING.value}'.")

    expense.status = ExpenseStatus.APPROVED.value
    expense.decided_by_user_id = current_user.id
    expense.decided_at = datetime.now(timezone.utc)
    await db.flush()

    await write_audit_log(
        db,
        action="expense.approve",
        entity_type="Expense",
        entity_id=str(expense.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=expense.station_id,
        after={"status": expense.status},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return expense


@router.patch("/{expense_id}/reject", response_model=ExpenseRead)
async def reject_expense(
    organization_id: uuid.UUID,
    expense_id: uuid.UUID,
    payload: ExpenseReject,
    request: Request,
    current_user: User = Depends(require_permission(EXPENSE_APPROVE)),
    db: AsyncSession = Depends(get_db),
) -> Expense:
    expense = await get_expense_or_404(db, organization_id, expense_id, for_update=True)
    if expense.status != ExpenseStatus.PENDING.value:
        raise ConflictError(f"Expense is '{expense.status}', not '{ExpenseStatus.PENDING.value}'.")

    expense.status = ExpenseStatus.REJECTED.value
    expense.decided_by_user_id = current_user.id
    expense.decided_at = datetime.now(timezone.utc)
    expense.rejection_reason = payload.rejection_reason
    await db.flush()

    await write_audit_log(
        db,
        action="expense.reject",
        entity_type="Expense",
        entity_id=str(expense.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=expense.station_id,
        after={"status": expense.status, "rejection_reason": payload.rejection_reason},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return expense


@router.patch("/{expense_id}/reverse", response_model=ExpenseRead)
async def reverse_expense(
    organization_id: uuid.UUID,
    expense_id: uuid.UUID,
    payload: ExpenseReverse,
    request: Request,
    current_user: User = Depends(require_permission(EXPENSE_APPROVE)),
    db: AsyncSession = Depends(get_db),
) -> Expense:
    """
    Reverses an already-approved expense (a correction, not a delete) -
    mirrors ShiftTender/ShiftCashMovement reversal. A still-pending or
    already-rejected expense cannot be "reversed" - it should be rejected
    or simply left as-is instead.
    """
    expense = await get_expense_or_404(db, organization_id, expense_id, for_update=True)
    if expense.status != ExpenseStatus.APPROVED.value:
        raise ConflictError(f"Only an '{ExpenseStatus.APPROVED.value}' expense can be reversed.")
    if expense.reversed_at is not None:
        raise ConflictError("This expense has already been reversed.")

    expense.reversed_by_user_id = current_user.id
    expense.reversed_at = datetime.now(timezone.utc)
    expense.reversal_reason = payload.reason
    await db.flush()

    await write_audit_log(
        db,
        action="expense.reverse",
        entity_type="Expense",
        entity_id=str(expense.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=expense.station_id,
        after={"reason": payload.reason},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return expense
