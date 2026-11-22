import enum
import uuid
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin

KW = Numeric(8, 2)


class ChargerType(str, enum.Enum):
    AC = "ac"
    DC = "dc"


class PortStatus(str, enum.Enum):
    AVAILABLE = "available"
    OCCUPIED = "occupied"
    CHARGING = "charging"
    OUT_OF_SERVICE = "out_of_service"
    FAULTED = "faulted"
    OFFLINE = "offline"


class EVCharger(UUIDPKMixin, TimestampMixin, Base):
    """
    An EV charging unit at a station - entirely separate from the fuel
    tank/dispenser/nozzle hierarchy (blueprint §14A: electricity in kWh is
    never fuel in litres, and an EV charger never has a tank_id). Mirrors
    Dispenser's own station-scoped master-data shape.
    """

    __tablename__ = "ev_chargers"
    __table_args__ = (UniqueConstraint("station_id", "code", name="uq_ev_charger_station_code"),)

    station_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("stations.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    manufacturer: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    charger_type: Mapped[str] = mapped_column(String(10), nullable=False)
    rated_power_kw: Mapped[Decimal | None] = mapped_column(KW, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class EVChargerPort(UUIDPKMixin, TimestampMixin, Base):
    """
    One connector on a charger. A charging session always happens against a
    port, not the charger as a whole (a DC charger commonly has 2 ports that
    can charge independently) - mirrors Nozzle belonging to a Dispenser.
    """

    __tablename__ = "ev_charger_ports"
    __table_args__ = (UniqueConstraint("charger_id", "port_code", name="uq_ev_port_charger_code"),)

    charger_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("ev_chargers.id", ondelete="CASCADE"), nullable=False
    )
    port_code: Mapped[str] = mapped_column(String(20), nullable=False)
    # Free text, not an enum: the blueprint lists CCS2/Type2/CHAdeMO as
    # examples, not an exhaustive set, and a new connector standard should
    # never require a migration to record.
    connector_standard: Mapped[str] = mapped_column(String(30), nullable=False)
    rated_power_kw: Mapped[Decimal | None] = mapped_column(KW, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=PortStatus.AVAILABLE.value, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
