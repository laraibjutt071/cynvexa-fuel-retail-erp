import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import UUIDPKMixin, utcnow

MONEY = Numeric(14, 2)
QTY = Numeric(12, 3)


class InventoryMovementType(str, enum.Enum):
    RECEIPT = "receipt"
    ISSUE = "issue"
    SALE = "sale"
    ADJUSTMENT_INCREASE = "adjustment_increase"
    ADJUSTMENT_DECREASE = "adjustment_decrease"


INCREASING_INVENTORY_MOVEMENT_TYPES = {
    InventoryMovementType.RECEIPT,
    InventoryMovementType.ADJUSTMENT_INCREASE,
}
DECREASING_INVENTORY_MOVEMENT_TYPES = {
    InventoryMovementType.ISSUE,
    InventoryMovementType.SALE,
    InventoryMovementType.ADJUSTMENT_DECREASE,
}
assert INCREASING_INVENTORY_MOVEMENT_TYPES | DECREASING_INVENTORY_MOVEMENT_TYPES == set(
    InventoryMovementType
)


class InventoryMovement(UUIDPKMixin, Base):
    """
    Append-only ledger entry for shop/lubricant stock - the same pattern
    as StockLedgerEntry for fuel: never updated or deleted, only ever
    added to. On-hand quantity is always the sum of this ledger
    (app/core/inventory.py::get_inventory_stock), never a mutable column.
    `amount` is the movement's money value where one applies (cost for a
    RECEIPT, revenue for a SALE) - optional, since an ISSUE (internal use)
    or ADJUSTMENT may carry no money value at all.
    """

    __tablename__ = "inventory_movements"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_inventory_movement_quantity_positive"),
        # get_inventory_stock always filters by (inventory_item_id,
        # movement_type) - same reasoning as StockLedgerEntry's own
        # composite index.
        Index("ix_inventory_movements_item_movement_type", "inventory_item_id", "movement_type"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    station_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("stations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    inventory_item_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("inventory_items.id", ondelete="RESTRICT"), nullable=False
    )
    movement_type: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(QTY, nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
