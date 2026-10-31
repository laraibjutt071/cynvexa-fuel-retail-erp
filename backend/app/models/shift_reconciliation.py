import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin, utcnow

MONEY = Numeric(14, 2)


class ShiftReconciliation(UUIDPKMixin, TimestampMixin, Base):
    """
    One per shift (unique). Computed once, at creation, from the shift's
    own nozzle readings (expected_fuel_revenue), tenders (total_tender_amount)
    and cash movements (expected_physical_cash) - see
    app/core/reconciliation.py, the only module that may compute these
    figures. actual_physical_cash is the one number a human provides (the
    till count); everything else is derived.

    Immutable once approved (Shift.approve() checks this record and its
    authorization status before allowing final approval - see
    app/api/shifts.py). A correction after that point is a
    ShiftReconciliationAmendment, never an edit to this row.
    """

    __tablename__ = "shift_reconciliations"
    __table_args__ = (
        CheckConstraint("expected_fuel_revenue >= 0", name="ck_recon_expected_revenue_nonnegative"),
        CheckConstraint("total_tender_amount >= 0", name="ck_recon_total_tender_nonnegative"),
        CheckConstraint("actual_physical_cash >= 0", name="ck_recon_actual_cash_nonnegative"),
    )

    shift_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("shifts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    expected_fuel_revenue: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    total_tender_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    revenue_variance: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    revenue_variance_percent: Mapped[Decimal] = mapped_column(Numeric(7, 3), nullable=False)
    revenue_within_tolerance: Mapped[bool] = mapped_column(nullable=False)

    expected_physical_cash: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    actual_physical_cash: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    cash_shortage_excess: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    cash_within_tolerance: Mapped[bool] = mapped_column(nullable=False)

    requires_authorization: Mapped[bool] = mapped_column(nullable=False)
    explanation: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    authorized_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    authorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )


class AmendmentStatus:
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ShiftReconciliationAmendment(UUIDPKMixin, Base):
    """
    A requested correction to one field of an already-approved
    ShiftReconciliation. The original row is NEVER edited - this is a new,
    separately-approved row that references it, preserving the before/after
    values, the reason, and both actors (requested_by, approved_by), exactly
    like AuditLog but as its own first-class, queryable, approval-gated
    record rather than a log line. See docs/ASSUMPTIONS.md #18/#23.
    """

    __tablename__ = "shift_reconciliation_amendments"

    reconciliation_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("shift_reconciliations.id", ondelete="CASCADE"), nullable=False
    )
    field_name: Mapped[str] = mapped_column(String(50), nullable=False)
    previous_value: Mapped[str] = mapped_column(String(200), nullable=False)
    new_value: Mapped[str] = mapped_column(String(200), nullable=False)
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default=AmendmentStatus.PENDING)

    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
