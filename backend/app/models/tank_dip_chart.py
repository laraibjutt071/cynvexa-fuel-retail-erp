import uuid
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class TankDipChartEntry(UUIDPKMixin, TimestampMixin, Base):
    """
    One calibration point from a tank's manufacturer/calibration-certificate
    strapping table: at this physical dip-stick reading, the tank holds
    this many litres. A purely additive reference tool - never read by
    shift-reading, reconciliation, stock-ledger or any other existing
    calculation, all of which continue to take dip_reading as a litres
    value exactly as before (see ShiftTankReading's own docstring). The
    operator looks a stick reading up here themselves (GET .../lookup)
    before typing the resulting litres into the actual shift reading,
    same as they would with a paper dip-chart booklet - this just makes
    that lookup digital and tank-specific instead of a separate physical
    document.
    """

    __tablename__ = "tank_dip_chart_entries"
    __table_args__ = (
        UniqueConstraint("tank_id", "dip_mm", name="uq_tank_dip_chart_tank_dip"),
        CheckConstraint("dip_mm >= 0", name="ck_tank_dip_chart_dip_nonnegative"),
        CheckConstraint("volume_litres >= 0", name="ck_tank_dip_chart_volume_nonnegative"),
    )

    tank_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tanks.id", ondelete="CASCADE"), nullable=False
    )
    dip_mm: Mapped[Decimal] = mapped_column(Numeric(8, 1), nullable=False)
    volume_litres: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
