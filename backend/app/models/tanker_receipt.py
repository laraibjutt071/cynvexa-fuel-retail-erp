import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin

LITRES = Numeric(12, 3)


class ReceiptStatus(str, enum.Enum):
    PENDING_UNLOAD = "pending_unload"  # created, before/after-unload not yet recorded
    AWAITING_APPROVAL = "awaiting_approval"  # unload recorded, waiting on a separate approver
    APPROVED = "approved"  # posted to the stock ledger - terminal, immutable from here
    REJECTED = "rejected"  # terminal, no ledger entry


class PayableQuantityBasis(str, enum.Enum):
    """
    Which captured quantity the supplier is actually paid against. See
    docs/ASSUMPTIONS.md #1 - this is an explicit, per-receipt, owner-visible
    choice, never an assumption baked into code. All four candidate
    quantities stay on the record regardless of which one was used.
    """

    INVOICE_QUANTITY = "invoice_quantity"
    DISPATCHED_QUANTITY = "dispatched_quantity"
    CALIBRATED_QUANTITY = "calibrated_quantity"
    TANK_GAIN_QUANTITY = "tank_gain_quantity"


class TankerReceipt(UUIDPKMixin, TimestampMixin, Base):
    """
    One tanker delivery, from arrival through approval. Deliberately keeps
    document quantity, physically observed quantity, accepted quantity, and
    payable quantity as separate fields (blueprint §4) - none of them is
    assumed equal to another. Approved rows are immutable: see
    app/api/tanker_receipts.py for why every state transition re-fetches the
    row with SELECT ... FOR UPDATE before checking `status`.
    """

    __tablename__ = "tanker_receipts"
    __table_args__ = (
        CheckConstraint(
            "invoice_quantity IS NULL OR invoice_quantity > 0", name="ck_receipt_invoice_qty_positive"
        ),
        CheckConstraint(
            "dispatched_quantity IS NULL OR dispatched_quantity > 0",
            name="ck_receipt_dispatched_qty_positive",
        ),
        CheckConstraint(
            "calibrated_quantity IS NULL OR calibrated_quantity > 0",
            name="ck_receipt_calibrated_qty_positive",
        ),
        CheckConstraint("pre_receipt_tank_reading >= 0", name="ck_receipt_pre_reading_nonnegative"),
        CheckConstraint(
            "post_receipt_tank_reading IS NULL OR post_receipt_tank_reading >= 0",
            name="ck_receipt_post_reading_nonnegative",
        ),
        CheckConstraint(
            "tank_gain_quantity IS NULL OR tank_gain_quantity >= 0", name="ck_receipt_tank_gain_nonnegative"
        ),
        CheckConstraint(
            "accepted_quantity IS NULL OR accepted_quantity > 0", name="ck_receipt_accepted_qty_positive"
        ),
        CheckConstraint(
            "payable_quantity IS NULL OR payable_quantity > 0", name="ck_receipt_payable_qty_positive"
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    station_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("stations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tank_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tanks.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    fuel_grade_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("fuel_grades.id", ondelete="RESTRICT"), nullable=False
    )
    supplier_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ReceiptStatus.PENDING_UNLOAD.value
    )

    # --- Supplier / tanker documents ---
    tanker_registration: Mapped[str] = mapped_column(String(50), nullable=False)
    driver_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    supplier_invoice_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    challan_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # --- Declared quantities (document-side; not assumed equal to each other) ---
    invoice_quantity: Mapped[Decimal | None] = mapped_column(LITRES, nullable=True)
    dispatched_quantity: Mapped[Decimal | None] = mapped_column(LITRES, nullable=True)
    calibrated_quantity: Mapped[Decimal | None] = mapped_column(LITRES, nullable=True)

    # --- Pre-receipt observation (required to create the record at all) ---
    pre_receipt_tank_reading: Mapped[Decimal] = mapped_column(LITRES, nullable=False)
    pre_receipt_density: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    pre_receipt_temperature_celsius: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    pre_receipt_water_level_cm: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    # Snapshot of the safe capacity check performed at creation time, so the
    # decision is reviewable later even if the tank's configured safe fill
    # limit changes afterward.
    safe_capacity_available_at_creation: Mapped[Decimal] = mapped_column(LITRES, nullable=False)

    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    # --- Post-receipt observation (recorded by record_unload) ---
    post_receipt_tank_reading: Mapped[Decimal | None] = mapped_column(LITRES, nullable=True)
    tank_gain_quantity: Mapped[Decimal | None] = mapped_column(LITRES, nullable=True)
    unload_recorded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    unload_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Approval decision (recorded by approve / reject) ---
    accepted_quantity: Mapped[Decimal | None] = mapped_column(LITRES, nullable=True)
    payable_quantity_basis: Mapped[str | None] = mapped_column(String(30), nullable=True)
    payable_quantity: Mapped[Decimal | None] = mapped_column(LITRES, nullable=True)
    variance_quantity: Mapped[Decimal | None] = mapped_column(LITRES, nullable=True)
    variance_percent: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    within_tolerance: Mapped[bool | None] = mapped_column(nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
