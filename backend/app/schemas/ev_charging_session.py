import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class EVChargingSessionCreate(BaseModel):
    port_id: uuid.UUID
    tariff_id: uuid.UUID
    start_meter_kwh: Decimal = Field(ge=0)
    start_time: datetime | None = Field(default=None, description="Defaults to now if omitted.")
    session_reference: str | None = Field(default=None, max_length=50)
    vehicle_reference: str | None = Field(default=None, max_length=50)
    credit_customer_id: uuid.UUID | None = None


class EVChargingSessionClose(BaseModel):
    end_meter_kwh: Decimal = Field(ge=0)
    end_time: datetime | None = Field(default=None, description="Defaults to now if omitted.")
    payment_method_id: uuid.UUID | None = None


class EVChargingSessionFail(BaseModel):
    """Marks a session as interrupted/failed/cancelled instead of completed - no energy/amount is computed."""

    status: str = Field(pattern="^(interrupted|failed|cancelled)$")
    fault_reason: str = Field(min_length=1, max_length=500)


class EVChargingSessionReverse(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class EVChargingSessionRead(BaseModel):
    id: uuid.UUID
    port_id: uuid.UUID
    tariff_id: uuid.UUID
    session_reference: str | None
    status: str
    start_time: datetime
    end_time: datetime | None
    start_meter_kwh: Decimal
    end_meter_kwh: Decimal | None
    delivered_kwh: Decimal | None
    gross_amount: Decimal | None
    payment_method_id: uuid.UUID | None
    credit_customer_id: uuid.UUID | None
    vehicle_reference: str | None
    fault_reason: str | None
    notes: str | None
    created_by_user_id: uuid.UUID
    reversed_by_user_id: uuid.UUID | None
    reversed_at: datetime | None
    reversal_reason: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
