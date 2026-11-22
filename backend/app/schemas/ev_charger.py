import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.ev_charger import ChargerType, PortStatus


class EVChargerCreate(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    label: str = Field(min_length=1, max_length=100)
    charger_type: ChargerType
    manufacturer: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=100)
    serial_number: str | None = Field(default=None, max_length=100)
    rated_power_kw: Decimal | None = Field(default=None, gt=0)


class EVChargerUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=100)
    manufacturer: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=100)
    serial_number: str | None = Field(default=None, max_length=100)
    rated_power_kw: Decimal | None = Field(default=None, gt=0)
    is_active: bool | None = None


class EVChargerRead(BaseModel):
    id: uuid.UUID
    station_id: uuid.UUID
    code: str
    label: str
    manufacturer: str | None
    model: str | None
    serial_number: str | None
    charger_type: str
    rated_power_kw: Decimal | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EVChargerPortCreate(BaseModel):
    port_code: str = Field(min_length=1, max_length=20)
    connector_standard: str = Field(min_length=1, max_length=30)
    rated_power_kw: Decimal | None = Field(default=None, gt=0)


class EVChargerPortUpdate(BaseModel):
    connector_standard: str | None = Field(default=None, min_length=1, max_length=30)
    rated_power_kw: Decimal | None = Field(default=None, gt=0)
    status: PortStatus | None = None
    is_active: bool | None = None


class EVChargerPortRead(BaseModel):
    id: uuid.UUID
    charger_id: uuid.UUID
    port_code: str
    connector_standard: str
    rated_power_kw: Decimal | None
    status: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
