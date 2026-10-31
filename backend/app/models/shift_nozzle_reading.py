import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin, utcnow

TOTALIZER = Numeric(14, 3)


class MeterEventType(str, enum.Enum):
    REPLACEMENT = "replacement"  # physical meter swapped mid-shift
    RESET = "reset"  # meter deliberately zeroed (maintenance)
    ROLLOVER = "rollover"  # meter wrapped past its maximum digit count


class ShiftNozzleReading(UUIDPKMixin, TimestampMixin, Base):
    """
    Opening and closing totalizer for one nozzle in one shift.

    dispensed_litres is NEVER simply closing - opening when a meter event is
    flagged: a replacement/reset/rollover means the totalizer sequence is
    discontinuous mid-shift, so the true dispensed quantity is the sum of two
    segments either side of the event - (meter_event_pre_reading -
    opening_totalizer) + (closing_totalizer - meter_event_post_reading). Both
    segments must independently be >= 0; computed and stored once at shift
    close (app/api/shifts.py), never recomputed afterward.

    A flagged meter event must be explicitly approved (meter_event_approved_*)
    before the shift itself can be approved - the "approved meter
    rollover/replacement/reset workflow" ARCHITECTURE.md commits to.
    """

    __tablename__ = "shift_nozzle_readings"
    __table_args__ = (
        UniqueConstraint("shift_id", "nozzle_id", name="uq_shift_nozzle_reading"),
        CheckConstraint("opening_totalizer >= 0", name="ck_snr_opening_nonnegative"),
        CheckConstraint(
            "closing_totalizer IS NULL OR closing_totalizer >= 0", name="ck_snr_closing_nonnegative"
        ),
        CheckConstraint(
            "dispensed_litres IS NULL OR dispensed_litres >= 0", name="ck_snr_dispensed_nonnegative"
        ),
    )

    shift_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("shifts.id", ondelete="CASCADE"), nullable=False
    )
    nozzle_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("nozzles.id", ondelete="RESTRICT"), nullable=False
    )

    opening_totalizer: Mapped[Decimal] = mapped_column(TOTALIZER, nullable=False)
    opening_recorded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    opening_recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    closing_totalizer: Mapped[Decimal | None] = mapped_column(TOTALIZER, nullable=True)
    closing_recorded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    closing_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    dispensed_litres: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)

    meter_event_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    meter_event_pre_reading: Mapped[Decimal | None] = mapped_column(TOTALIZER, nullable=True)
    meter_event_post_reading: Mapped[Decimal | None] = mapped_column(TOTALIZER, nullable=True)
    meter_event_notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    meter_event_approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    meter_event_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
