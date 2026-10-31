import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import UUIDPKMixin, utcnow


class ShiftPriceChange(UUIDPKMixin, Base):
    """
    Records that a fuel grade's effective price changed during a shift.
    Phase C does not compute split revenue (that is Phase D's "expected
    revenue" concern) - this exists so the boundary totalizer readings
    below are captured now, while they're still physically readable,
    rather than needing to be reconstructed later.
    """

    __tablename__ = "shift_price_changes"

    shift_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("shifts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fuel_grade_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("fuel_grades.id", ondelete="RESTRICT"), nullable=False
    )
    old_price_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("fuel_prices.id", ondelete="SET NULL"), nullable=True
    )
    new_price_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("fuel_prices.id", ondelete="RESTRICT"), nullable=False
    )
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ShiftPriceChangeReading(UUIDPKMixin, Base):
    """
    The totalizer reading for one affected nozzle at the moment of a
    ShiftPriceChange - the "boundary reading" docs/ASSUMPTIONS.md #6 commits
    to requiring (per-station, via Station.require_price_change_reading)
    before the shift can be closed.
    """

    __tablename__ = "shift_price_change_readings"
    __table_args__ = (
        UniqueConstraint("shift_price_change_id", "nozzle_id", name="uq_price_change_reading_nozzle"),
    )

    shift_price_change_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("shift_price_changes.id", ondelete="CASCADE"), nullable=False
    )
    nozzle_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("nozzles.id", ondelete="RESTRICT"), nullable=False
    )
    totalizer_reading: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    recorded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
