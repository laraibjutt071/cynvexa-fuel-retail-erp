import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class EVPricingBasis(str, enum.Enum):
    PER_KWH = "per_kwh"
    TIME_BASED = "time_based"
    SESSION_FEE = "session_fee"


class EVTariff(UUIDPKMixin, TimestampMixin, Base):
    """
    Append-only, exactly like FuelPrice (see that model's docstring): there
    is no update endpoint and nothing ever mutates rate/effective_from - a
    tariff change is always a new row, so a session closed last week is
    still reproducible against the tariff that was actually in force then.

    `rate`'s unit depends on pricing_basis and is never reinterpreted
    elsewhere: currency per kWh for PER_KWH, currency per minute for
    TIME_BASED, or a flat currency amount per session for SESSION_FEE.

    charger_id is nullable: a null charger_id is a station-wide default
    tariff; a set one overrides it for that specific charger. Deliberately
    no port-level override for this MVP - the blueprint allows it but does
    not require it, and charger-level is the finer granularity this
    project's own "confirm the simplest authoritative rule first"
    philosophy calls for (see tanker receipt's payable-quantity-basis
    choice for the same spirit).
    """

    __tablename__ = "ev_tariffs"
    __table_args__ = (
        UniqueConstraint(
            "station_id", "charger_id", "effective_from", name="uq_ev_tariff_station_charger_effective"
        ),
        CheckConstraint("rate > 0", name="ck_ev_tariff_rate_positive"),
    )

    station_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("stations.id", ondelete="CASCADE"), nullable=False
    )
    charger_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("ev_chargers.id", ondelete="CASCADE"), nullable=True
    )
    pricing_basis: Mapped[str] = mapped_column(String(20), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
