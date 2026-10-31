import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import UUIDPKMixin, utcnow


class TankReadingType(str, enum.Enum):
    OPENING = "opening"
    CLOSING = "closing"


class ShiftTankReading(UUIDPKMixin, Base):
    """
    A physical dip/ATG observation of one tank at shift open or close.
    This is a FACT, never a substitute for book stock - see
    app/core/stock.py::get_book_stock. Immutable once recorded; a wrong
    reading on an OPEN shift can still be corrected by the operator before
    closing (see the API's status check), but once the shift is CLOSED or
    APPROVED it is permanent history.
    """

    __tablename__ = "shift_tank_readings"
    __table_args__ = (
        UniqueConstraint("shift_id", "tank_id", "reading_type", name="uq_shift_tank_reading"),
        CheckConstraint("dip_reading >= 0", name="ck_shift_tank_reading_nonnegative"),
    )

    shift_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("shifts.id", ondelete="CASCADE"), nullable=False
    )
    tank_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tanks.id", ondelete="RESTRICT"), nullable=False
    )
    reading_type: Mapped[str] = mapped_column(String(10), nullable=False)
    dip_reading: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    recorded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
