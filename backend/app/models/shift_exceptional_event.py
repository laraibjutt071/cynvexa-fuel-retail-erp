import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import UUIDPKMixin, utcnow


class ExceptionalEventType(str, enum.Enum):
    TEST_DRAW = "test_draw"
    CALIBRATION = "calibration"
    OTHER = "other"


class ShiftExceptionalEvent(UUIDPKMixin, Base):
    """
    Litres dispensed through a nozzle that are NOT a retail sale (test
    draws, calibration checks). These reduce the "sale" portion of a tank's
    dispensed total at shift approval time, posted to the ledger as their
    own StockMovementType.TEST_CALIBRATION entry - kept visibly separate
    from StockMovementType.SALE rather than silently netted out of it.
    """

    __tablename__ = "shift_exceptional_events"
    __table_args__ = (CheckConstraint("litres > 0", name="ck_exceptional_event_litres_positive"),)

    shift_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("shifts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nozzle_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("nozzles.id", ondelete="RESTRICT"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    litres: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    recorded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
