import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class StationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=1, max_length=50)
    address: str | None = Field(default=None, max_length=500)
    timezone: str = Field(default="UTC", max_length=50)


class StationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    address: str | None = Field(default=None, max_length=500)
    timezone: str | None = Field(default=None, max_length=50)
    is_active: bool | None = None
    receipt_tolerance_percent: Decimal | None = Field(default=None, ge=0, le=100)
    require_density: bool | None = None
    require_temperature: bool | None = None
    require_water_check: bool | None = None
    require_receipt_evidence: bool | None = None
    require_price_change_reading: bool | None = None
    shift_variance_tolerance_percent: Decimal | None = Field(default=None, ge=0, le=100)
    cash_variance_tolerance_amount: Decimal | None = Field(default=None, ge=0)
    revenue_variance_tolerance_percent: Decimal | None = Field(default=None, ge=0, le=100)


class StationRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    code: str
    address: str | None
    timezone: str
    is_active: bool
    receipt_tolerance_percent: Decimal
    require_density: bool
    require_temperature: bool
    require_water_check: bool
    require_receipt_evidence: bool
    require_price_change_reading: bool
    shift_variance_tolerance_percent: Decimal
    cash_variance_tolerance_amount: Decimal
    revenue_variance_tolerance_percent: Decimal
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
