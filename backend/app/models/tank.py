import uuid
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin

# 3 decimal places: fuel receipts/dips are commonly recorded to the litre or
# tenth-of-a-litre; NUMERIC (never FLOAT) so totals never drift.
LITRES = Numeric(12, 3)


class Tank(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "tanks"
    __table_args__ = (
        UniqueConstraint("station_id", "code", name="uq_tank_station_code"),
        CheckConstraint("capacity > 0", name="ck_tank_capacity_positive"),
        CheckConstraint("safe_fill_limit > 0", name="ck_tank_safe_fill_limit_positive"),
        CheckConstraint("safe_fill_limit <= capacity", name="ck_tank_safe_fill_limit_within_capacity"),
    )

    station_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("stations.id", ondelete="CASCADE"), nullable=False
    )
    fuel_grade_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("fuel_grades.id", ondelete="RESTRICT"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    capacity: Mapped[Decimal] = mapped_column(LITRES, nullable=False)
    # The maximum level it is safe to fill to - always <= capacity, leaving
    # headroom for thermal expansion / overfill safety. A receipt must never
    # be accepted if it would push book stock above this, not `capacity`.
    safe_fill_limit: Mapped[Decimal] = mapped_column(LITRES, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
