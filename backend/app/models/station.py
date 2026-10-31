import uuid
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class Station(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "stations"
    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_station_org_code"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    timezone: Mapped[str] = mapped_column(String(50), default="UTC", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # --- Tanker receipt configuration (docs/ASSUMPTIONS.md #2-#4) ---
    # Every one of these is an owner/accountant decision this implementation
    # could not make for the station, so each gets a conservative, documented
    # default rather than a guess with no record of it being a guess.
    receipt_tolerance_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0.5"), nullable=False
    )
    require_density: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    require_temperature: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    require_water_check: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    require_receipt_evidence: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # --- Shift configuration (docs/ASSUMPTIONS.md #6, #17) ---
    # Default True: the blueprint's §18 flags un-split mid-shift price
    # changes as a correctness risk, so the stricter default is "require
    # the boundary reading" rather than "assume it doesn't matter".
    require_price_change_reading: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    shift_variance_tolerance_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0.5"), nullable=False
    )

    # --- Financial reconciliation configuration (docs/ASSUMPTIONS.md #19-#21) ---
    # Cash tolerance is an absolute amount, not a percentage: a fixed "a few
    # units of currency" miscount is the real-world risk threshold station
    # staff work to, not a percentage of a number that varies wildly shift
    # to shift. Revenue tolerance (expected fuel revenue vs. total tender)
    # stays percentage-based, consistent with the receipt/shift tolerances
    # above. EITHER breach makes the reconciliation require authorization.
    cash_variance_tolerance_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("50.00"), nullable=False
    )
    revenue_variance_tolerance_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("1.0"), nullable=False
    )

    organization: Mapped["Organization"] = relationship(back_populates="stations")
