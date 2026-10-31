import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import UUIDPKMixin, utcnow

MONEY = Numeric(14, 2)


class CashMovementType(str, enum.Enum):
    OPENING_CASH = "opening_cash"
    EXPENSE = "expense"
    DEPOSIT = "deposit"
    SAFE_TRANSFER_IN = "safe_transfer_in"
    SAFE_TRANSFER_OUT = "safe_transfer_out"
    REFUND = "refund"
    OTHER_INCREASE = "other_increase"
    OTHER_DECREASE = "other_decrease"


# Every movement that takes cash OUT of what the shift is accountable for
# requires approval before it counts toward the reconciliation - "approved
# shift expenses" in the blueprint's own words, extended to every outflow
# for the same reason (deposits/transfers/refunds are just as much a
# control point as expenses). Movements that ADD accountable cash (the
# opening float, a safe transfer in) are lower-risk and don't need it.
INCREASING_CASH_MOVEMENT_TYPES = {
    CashMovementType.OPENING_CASH,
    CashMovementType.SAFE_TRANSFER_IN,
    CashMovementType.OTHER_INCREASE,
}
DECREASING_CASH_MOVEMENT_TYPES = {
    CashMovementType.EXPENSE,
    CashMovementType.DEPOSIT,
    CashMovementType.SAFE_TRANSFER_OUT,
    CashMovementType.REFUND,
    CashMovementType.OTHER_DECREASE,
}
assert INCREASING_CASH_MOVEMENT_TYPES | DECREASING_CASH_MOVEMENT_TYPES == set(CashMovementType)


class ShiftCashMovement(UUIDPKMixin, Base):
    """
    Opening cash, approved expenses, deposits, safe transfers and refunds -
    every one of these is a MOVEMENT OF PHYSICAL CASH, never fuel revenue
    and never netted against anything else. A deposit, in particular, is
    cash leaving the till for the bank, not a reduction of sales - see
    app/core/reconciliation.py for why expected_fuel_revenue never reads
    this table at all.
    """

    __tablename__ = "shift_cash_movements"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_cash_movement_amount_positive"),)

    shift_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("shifts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    movement_type: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    recorded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    reversed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reversal_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
