import enum
import uuid

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin, UUIDPKMixin


class HardwareDeviceType(str, enum.Enum):
    DISPENSER_CONTROLLER = "dispenser_controller"
    FORECOURT_CONTROLLER = "forecourt_controller"
    ATG = "atg"
    EXISTING_POS = "existing_pos"
    BIOMETRIC_ATTENDANCE = "biometric_attendance"


class HardwareConnectionType(str, enum.Enum):
    TCP_IP = "tcp_ip"
    SERIAL = "serial"


class HardwareDeviceStatus(str, enum.Enum):
    DRAFT = "draft"  # wizard step 1-2: device identified, connection not attempted yet
    TESTING = "testing"  # a connection test is in progress (set just before the attempt)
    CONNECTED = "connected"  # last test reached the device
    FAILED = "failed"  # last test could not reach the device


class HardwareDevice(UUIDPKMixin, TimestampMixin, Base):
    """
    A station's record of one piece of hardware - forecourt equipment or a
    biometric attendance device - going through the connection wizard
    (app/api/hardware_devices.py). This project has no protocol driver for
    any real dispenser/ATG/POS/biometric device - creating a row here
    never makes nozzle/tank readings flow automatically. What IS real: the
    TCP reachability test in test_connection() actually opens a socket to
    the given host/port from this backend's network, so "connected" here
    means "this server could open a TCP connection to that address", not
    "the vendor protocol handshake succeeded".
    """

    __tablename__ = "hardware_devices"

    station_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("stations.id", ondelete="CASCADE"), nullable=False
    )
    device_type: Mapped[str] = mapped_column(String(30), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(100), nullable=True)

    connection_type: Mapped[str] = mapped_column(String(10), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(100), nullable=True)
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    com_port: Mapped[str | None] = mapped_column(String(50), nullable=True)

    status: Mapped[str] = mapped_column(String(20), default=HardwareDeviceStatus.DRAFT.value, nullable=False)
    last_test_message: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
