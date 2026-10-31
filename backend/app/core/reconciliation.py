import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.revenue import round_money
from app.models.payment_method import PaymentMethod, PaymentMethodCategory
from app.models.shift_cash_movement import (
    DECREASING_CASH_MOVEMENT_TYPES,
    INCREASING_CASH_MOVEMENT_TYPES,
    ShiftCashMovement,
)
from app.models.shift_tender import ShiftTender


async def get_total_tender_amount(db: AsyncSession, shift_id: uuid.UUID) -> Decimal:
    """
    SUM of every non-reversed ShiftTender for the shift, across every
    payment method including credit. This is "accounted for" against
    expected fuel revenue - it never includes a ShiftCashMovement amount
    (opening cash, expenses, deposits, ...), which are physical-cash
    bookkeeping facts, not sales.
    """
    tenders = (
        await db.execute(
            select(ShiftTender).where(
                ShiftTender.shift_id == shift_id, ShiftTender.reversed_at.is_(None)
            )
        )
    ).scalars().all()
    return round_money(sum((t.amount for t in tenders), Decimal(0)))


async def get_cash_tender_amount(db: AsyncSession, shift_id: uuid.UUID) -> Decimal:
    """SUM of non-reversed tenders through CASH-category payment methods only -
    the portion of total tender that becomes physical cash in the till."""
    result = await db.execute(
        select(ShiftTender)
        .join(PaymentMethod, PaymentMethod.id == ShiftTender.payment_method_id)
        .where(
            ShiftTender.shift_id == shift_id,
            ShiftTender.reversed_at.is_(None),
            PaymentMethod.category == PaymentMethodCategory.CASH.value,
        )
    )
    tenders = result.scalars().all()
    return round_money(sum((t.amount for t in tenders), Decimal(0)))


async def get_unapproved_decreasing_movements(
    db: AsyncSession, shift_id: uuid.UUID
) -> list[ShiftCashMovement]:
    """Movements that take cash OUT of the shift's accountability and have
    not yet been approved - these must be resolved before a reconciliation
    can be computed, never silently excluded from it."""
    movements = (
        await db.execute(
            select(ShiftCashMovement).where(
                ShiftCashMovement.shift_id == shift_id, ShiftCashMovement.reversed_at.is_(None)
            )
        )
    ).scalars().all()
    return [
        m
        for m in movements
        if m.movement_type in {t.value for t in DECREASING_CASH_MOVEMENT_TYPES}
        and m.approved_by_user_id is None
    ]


async def compute_expected_physical_cash(db: AsyncSession, shift_id: uuid.UUID) -> Decimal:
    """
    opening cash + cash tender + increasing movements - decreasing
    movements. Callers must have already confirmed there are no unapproved
    decreasing movements (get_unapproved_decreasing_movements) - this
    function still defensively excludes them from the sum rather than
    crash, but the API layer is what actually blocks reconciliation
    creation until they're resolved, so an operator is never left guessing
    why a number doesn't match.
    """
    cash_tender = await get_cash_tender_amount(db, shift_id)

    movements = (
        await db.execute(
            select(ShiftCashMovement).where(
                ShiftCashMovement.shift_id == shift_id, ShiftCashMovement.reversed_at.is_(None)
            )
        )
    ).scalars().all()

    increasing_types = {t.value for t in INCREASING_CASH_MOVEMENT_TYPES}
    decreasing_types = {t.value for t in DECREASING_CASH_MOVEMENT_TYPES}

    total = cash_tender
    for m in movements:
        if m.movement_type in increasing_types:
            total += m.amount
        elif m.movement_type in decreasing_types and m.approved_by_user_id is not None:
            total -= m.amount
    return round_money(total)
