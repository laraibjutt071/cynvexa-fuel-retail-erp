import uuid
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class InventoryItem(UUIDPKMixin, TimestampMixin, Base):
    """
    Shop/lubricant master data - station-scoped, since the physical stock
    it describes is physically located at one station. `reorder_level` is
    informational only (drives the low-stock exception alert on the
    dashboard); it never blocks a movement from being recorded.
    """

    __tablename__ = "inventory_items"
    __table_args__ = (
        UniqueConstraint("station_id", "sku", name="uq_inventory_item_station_sku"),
        CheckConstraint("reorder_level >= 0", name="ck_inventory_item_reorder_level_nonnegative"),
        CheckConstraint("unit_cost >= 0", name="ck_inventory_item_unit_cost_nonnegative"),
        CheckConstraint("selling_price >= 0", name="ck_inventory_item_selling_price_nonnegative"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    station_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("stations.id", ondelete="CASCADE"), nullable=False
    )
    sku: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Free-text, not a DB enum - the frontend offers common presets
    # (Lubricant, Filter, Battery, Accessory, Other) but a station is
    # never blocked from typing something else.
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="other")
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    reorder_level: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=0)
    # Master-data reference prices only - never read by inventory_movements
    # (a movement's own `amount` is always the real, as-recorded money
    # value for that specific transaction). These exist so the catalogue
    # and the stock-valuation report have something to show before any
    # movement has been recorded, and as the default a movement form can
    # pre-fill and let the operator override.
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    selling_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
