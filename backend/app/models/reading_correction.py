import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import UUIDPKMixin, utcnow


class ReadingType(str, enum.Enum):
    TANK_DIP = "tank_dip"
    NOZZLE_OPENING = "nozzle_opening"
    NOZZLE_CLOSING = "nozzle_closing"
    METER_EVENT_PRE = "meter_event_pre"
    METER_EVENT_POST = "meter_event_post"


class CorrectionStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


READING_VALUE = Numeric(14, 3)

CORRECTION_WINDOW_HOURS = 24


class ReadingCorrection(UUIDPKMixin, Base):
    """
    A correction to an official reading value. Two modes depending on timing:

    Phase 1 (within 24h of original submission):
      The original reading row is updated in-place with the corrected value.
      This record preserves the original value and full audit trail.
      is_post_lock = False.

    Phase 2 (at or after 24h):
      The original reading row is NEVER modified. This record is a standalone
      amendment that references the original. Any downstream recalculation
      must read this record.
      is_post_lock = True.

    In both cases: original_value is permanently preserved, the correction
    requires approval, and the full audit chain (requester, approver,
    timestamps, reason) is recorded.
    """

    __tablename__ = "reading_corrections"
    __table_args__ = (
        CheckConstraint("original_value >= 0", name="ck_reading_correction_original_nonneg"),
        CheckConstraint("corrected_value >= 0", name="ck_reading_correction_corrected_nonneg"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    station_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("stations.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    shift_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("shifts.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )

    reading_type: Mapped[str] = mapped_column(String(30), nullable=False)

    tank_reading_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("shift_tank_readings.id", ondelete="RESTRICT"),
        nullable=True,
    )
    nozzle_reading_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("shift_nozzle_readings.id", ondelete="RESTRICT"),
        nullable=True,
    )

    original_value: Mapped[Decimal] = mapped_column(READING_VALUE, nullable=False)
    corrected_value: Mapped[Decimal] = mapped_column(READING_VALUE, nullable=False)
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)

    original_submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )

    is_post_lock: Mapped[bool] = mapped_column(nullable=False, default=False)

    status: Mapped[str] = mapped_column(
        String(10), nullable=False, default=CorrectionStatus.PENDING.value,
    )

    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False,
    )

    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
