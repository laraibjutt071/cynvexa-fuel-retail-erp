import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import UUIDPKMixin, utcnow


class StockMovementType(str, enum.Enum):
    RECEIPT = "receipt"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"
    ADJUSTMENT_POSITIVE = "adjustment_positive"
    ADJUSTMENT_NEGATIVE = "adjustment_negative"
    SALE = "sale"
    TEST_CALIBRATION = "test_calibration"
    APPROVED_LOSS = "approved_loss"


# Movement types whose quantity must be stored as a positive number (stock
# increases) vs. a positive number that the ledger reader subtracts (stock
# decreases) - see app/core/stock.py::get_book_stock. Kept here, next to the
# enum, so the two can't drift apart.
INCREASING_MOVEMENT_TYPES = {
    StockMovementType.RECEIPT,
    StockMovementType.TRANSFER_IN,
    StockMovementType.ADJUSTMENT_POSITIVE,
}
DECREASING_MOVEMENT_TYPES = {
    StockMovementType.TRANSFER_OUT,
    StockMovementType.ADJUSTMENT_NEGATIVE,
    StockMovementType.SALE,
    StockMovementType.TEST_CALIBRATION,
    StockMovementType.APPROVED_LOSS,
}
assert INCREASING_MOVEMENT_TYPES | DECREASING_MOVEMENT_TYPES == set(StockMovementType)


class StockLedgerEntry(UUIDPKMixin, Base):
    """
    Append-only book-stock ledger (ARCHITECTURE.md §6). Rows are never
    updated or deleted by application code - a mistaken entry is corrected
    with a compensating entry that references it, never an edit. Closing
    book stock for a tank is SUM(quantity) with increasing/decreasing sign
    applied per `INCREASING_MOVEMENT_TYPES`/`DECREASING_MOVEMENT_TYPES` - see
    app/core/stock.py::get_book_stock, the only function that should ever
    compute it.
    """

    __tablename__ = "stock_ledger_entries"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_stock_ledger_quantity_positive"),
        # get_book_stock - the hottest query in this app, run on every
        # capacity check, shift approval and variance report - always
        # filters by (tank_id, movement_type); this composite index lets
        # Postgres satisfy both the increasing-sum and decreasing-sum
        # queries from an index scan instead of a sequential scan as the
        # ledger grows.
        Index("ix_stock_ledger_entries_tank_movement_type", "tank_id", "movement_type"),
    )

    tank_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tanks.id", ondelete="RESTRICT"), nullable=False
    )
    movement_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # Always stored as a positive magnitude; direction comes from
    # movement_type, not the sign - this keeps "how much fuel physically
    # moved" and "which way" as two separate, equally visible facts.
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    reference_type: Mapped[str] = mapped_column(String(50), nullable=False)
    reference_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
