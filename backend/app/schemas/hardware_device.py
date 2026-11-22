import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.hardware_device import HardwareConnectionType, HardwareDeviceType


class HardwareDeviceCreate(BaseModel):
    device_type: HardwareDeviceType
    label: str = Field(min_length=1, max_length=100)
    brand: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=100)
    serial_number: str | None = Field(default=None, max_length=100)

    connection_type: HardwareConnectionType
    ip_address: str | None = Field(default=None, max_length=100)
    port: int | None = Field(default=None, gt=0, le=65535)
    com_port: str | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def connection_fields_match_type(self) -> "HardwareDeviceCreate":
        if self.connection_type == HardwareConnectionType.TCP_IP:
            if not self.ip_address or not self.port:
                raise ValueError("ip_address and port are required for a tcp_ip connection.")
        elif self.connection_type == HardwareConnectionType.SERIAL:
            if not self.com_port:
                raise ValueError("com_port is required for a serial connection.")
        return self


class HardwareDeviceRead(BaseModel):
    id: uuid.UUID
    station_id: uuid.UUID
    device_type: str
    label: str
    brand: str | None
    model: str | None
    serial_number: str | None
    connection_type: str
    ip_address: str | None
    port: int | None
    com_port: str | None
    status: str
    last_test_message: str | None
    created_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class HardwareDeviceTestResult(BaseModel):
    status: str
    message: str
    device: HardwareDeviceRead
