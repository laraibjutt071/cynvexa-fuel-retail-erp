import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import UUIDPKMixin, utcnow

MONEY = Numeric(14, 2)


class ShiftTender(UUIDPKMixin, Base):
    """
    One amount actually tendered through one payment method during a
    shift. Multiple rows per method are normal (e.g. two card batches, or
    several credit sales to different customers) - "actual tender for a
    method" is always SUM(amount) over its rows, never a single column.

    Reversal (not deletion): a mistaken entry gets reversed_by/at/reason
    set and is excluded from every reconciliation sum from then on, but the
    original row - including who entered what, and who reversed it - is
    never removed. See app/core/reconciliation.py.
    """

    __tablename__ = "shift_tenders"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_shift_tender_amount_positive"),)

    shift_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("shifts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payment_method_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("payment_methods.id", ondelete="RESTRICT"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    # Required (enforced in the API, not the DB, since it only applies to
    # CREDIT-category methods) when payment_method.category == "credit".
    credit_customer_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("credit_customers.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    recorded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    reversed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reversal_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
