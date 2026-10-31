import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class FuelPrice(UUIDPKMixin, TimestampMixin, Base):
    """
    Append-only: there is deliberately no update endpoint and no model
    method that mutates price_per_litre or effective_from. A price change is
    always a NEW row; the "current" price for a station+grade at a point in
    time is the row with the latest effective_from <= that time (see
    app/core/pricing.py::get_current_price). Historical prices are never
    overwritten, so a shift computed against last week's price is still
    reproducible.
    """

    __tablename__ = "fuel_prices"
    __table_args__ = (
        UniqueConstraint(
            "station_id", "fuel_grade_id", "effective_from", name="uq_fuel_price_station_grade_effective"
        ),
        CheckConstraint("price_per_litre > 0", name="ck_fuel_price_positive"),
    )

    station_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("stations.id", ondelete="CASCADE"), nullable=False
    )
    fuel_grade_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("fuel_grades.id", ondelete="RESTRICT"), nullable=False
    )
    price_per_litre: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
