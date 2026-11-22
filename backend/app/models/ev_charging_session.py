import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin, utcnow

KWH = Numeric(12, 3)
MONEY = Numeric(14, 2)


class EVSessionStatus(str, enum.Enum):
    INITIATED = "initiated"
    CHARGING = "charging"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class EVChargingSession(UUIDPKMixin, TimestampMixin, Base):
    """
    One EV charging session on one port. Manual-entry only for this MVP
    (blueprint §14A-F: "begin with manual session entry... if automatic
    integration is not yet verified" - no OCPP/CPMS protocol driver exists
    in this project, same posture as fuel dispensers having no protocol
    driver either, see app/models/hardware_device.py).

    delivered_kwh and gross_amount are computed once at close() (see
    app/api/ev_charging_sessions.py) and never recomputed afterward - same
    "computed once, immutable from there" rule as
    ShiftNozzleReading.dispensed_litres. A session's energy is NEVER
    posted anywhere in the fuel tank/stock ledger (StockLedgerEntry) - EV
    and liquid fuel are deliberately disjoint ledgers.

    Reversal (not deletion), mirroring ShiftTender: a mistaken or disputed
    session gets reversed_by/at/reason set - the original row is never
    removed, and a completed session being reversed also moves to
    REFUNDED so it reads correctly without being excluded from history.
    """

    __tablename__ = "ev_charging_sessions"
    __table_args__ = (
        CheckConstraint("start_meter_kwh >= 0", name="ck_ev_session_start_kwh_nonnegative"),
        CheckConstraint(
            "end_meter_kwh IS NULL OR end_meter_kwh >= 0", name="ck_ev_session_end_kwh_nonnegative"
        ),
        CheckConstraint(
            "delivered_kwh IS NULL OR delivered_kwh >= 0", name="ck_ev_session_delivered_kwh_nonnegative"
        ),
        CheckConstraint(
            "gross_amount IS NULL OR gross_amount >= 0", name="ck_ev_session_gross_amount_nonnegative"
        ),
    )

    port_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("ev_charger_ports.id", ondelete="RESTRICT"), nullable=False
    )
    tariff_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("ev_tariffs.id", ondelete="RESTRICT"), nullable=False
    )
    session_reference: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=EVSessionStatus.CHARGING.value, nullable=False)

    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    start_meter_kwh: Mapped[Decimal] = mapped_column(KWH, nullable=False)
    end_meter_kwh: Mapped[Decimal | None] = mapped_column(KWH, nullable=True)
    delivered_kwh: Mapped[Decimal | None] = mapped_column(KWH, nullable=True)
    gross_amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)

    payment_method_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("payment_methods.id", ondelete="RESTRICT"), nullable=True
    )
    credit_customer_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("credit_customers.id", ondelete="RESTRICT"), nullable=True
    )
    vehicle_reference: Mapped[str | None] = mapped_column(String(50), nullable=True)
    fault_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    reversed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reversal_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
