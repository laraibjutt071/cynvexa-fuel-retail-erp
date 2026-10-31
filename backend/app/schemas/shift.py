import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.models.shift_nozzle_reading import MeterEventType
from app.models.shift_exceptional_event import ExceptionalEventType


class ShiftCreate(BaseModel):
    label: str | None = Field(default=None, max_length=100)


class ShiftRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    station_id: uuid.UUID
    label: str | None
    status: str
    opened_by_user_id: uuid.UUID
    opened_at: datetime
    closed_by_user_id: uuid.UUID | None
    closed_at: datetime | None
    approved_by_user_id: uuid.UUID | None
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ShiftTankReadingCreate(BaseModel):
    """reading_type is NOT a field here - it's implied by which of the two
    endpoints (/tank-readings/opening or /tank-readings/closing) is called,
    so permission resolution never depends on request-body content."""

    tank_id: uuid.UUID
    dip_reading: Decimal = Field(ge=0)


class ShiftTankReadingRead(BaseModel):
    id: uuid.UUID
    shift_id: uuid.UUID
    tank_id: uuid.UUID
    reading_type: str
    dip_reading: Decimal
    recorded_by_user_id: uuid.UUID
    recorded_at: datetime

    model_config = {"from_attributes": True}


class ShiftNozzleReadingOpen(BaseModel):
    nozzle_id: uuid.UUID
    opening_totalizer: Decimal = Field(ge=0)


class ShiftNozzleReadingClose(BaseModel):
    closing_totalizer: Decimal = Field(ge=0)
    meter_event_type: MeterEventType | None = None
    meter_event_pre_reading: Decimal | None = Field(default=None, ge=0)
    meter_event_post_reading: Decimal | None = Field(default=None, ge=0)
    meter_event_notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def meter_event_fields_consistent(self) -> "ShiftNozzleReadingClose":
        if self.meter_event_type is not None:
            if self.meter_event_pre_reading is None or self.meter_event_post_reading is None:
                raise ValueError(
                    "meter_event_pre_reading and meter_event_post_reading are both required "
                    "when meter_event_type is set."
                )
        return self


class ShiftNozzleReadingRead(BaseModel):
    id: uuid.UUID
    shift_id: uuid.UUID
    nozzle_id: uuid.UUID
    opening_totalizer: Decimal
    opening_recorded_by_user_id: uuid.UUID
    opening_recorded_at: datetime
    closing_totalizer: Decimal | None
    closing_recorded_by_user_id: uuid.UUID | None
    closing_recorded_at: datetime | None
    dispensed_litres: Decimal | None
    meter_event_type: str | None
    meter_event_pre_reading: Decimal | None
    meter_event_post_reading: Decimal | None
    meter_event_notes: str | None
    meter_event_approved_by_user_id: uuid.UUID | None
    meter_event_approved_at: datetime | None

    model_config = {"from_attributes": True}


class ShiftExceptionalEventCreate(BaseModel):
    nozzle_id: uuid.UUID
    event_type: ExceptionalEventType
    litres: Decimal = Field(gt=0)
    reason: str = Field(min_length=1, max_length=500)


class ShiftExceptionalEventRead(BaseModel):
    id: uuid.UUID
    shift_id: uuid.UUID
    nozzle_id: uuid.UUID
    event_type: str
    litres: Decimal
    reason: str
    recorded_by_user_id: uuid.UUID
    recorded_at: datetime

    model_config = {"from_attributes": True}


class ShiftPriceChangeCreate(BaseModel):
    fuel_grade_id: uuid.UUID
    new_price_id: uuid.UUID
    effective_at: datetime


class ShiftPriceChangeRead(BaseModel):
    id: uuid.UUID
    shift_id: uuid.UUID
    fuel_grade_id: uuid.UUID
    old_price_id: uuid.UUID | None
    new_price_id: uuid.UUID
    effective_at: datetime
    recorded_by_user_id: uuid.UUID
    recorded_at: datetime

    model_config = {"from_attributes": True}


class ShiftPriceChangeReadingCreate(BaseModel):
    nozzle_id: uuid.UUID
    totalizer_reading: Decimal = Field(ge=0)


class ShiftPriceChangeReadingRead(BaseModel):
    id: uuid.UUID
    shift_price_change_id: uuid.UUID
    nozzle_id: uuid.UUID
    totalizer_reading: Decimal
    recorded_by_user_id: uuid.UUID
    recorded_at: datetime

    model_config = {"from_attributes": True}


class ShiftApproveMeterEvent(BaseModel):
    """Empty body - the action itself (who, when) is the approval."""

    pass


class TankVarianceRead(BaseModel):
    tank_id: uuid.UUID
    tank_code: str
    opening_book_stock: Decimal
    closing_book_stock: Decimal
    physical_opening_reading: Decimal | None
    physical_closing_reading: Decimal | None
    opening_variance: Decimal | None
    closing_variance: Decimal | None
    closing_variance_percent: Decimal | None
    within_tolerance: bool | None


class ShiftVarianceReport(BaseModel):
    shift_id: uuid.UUID
    tanks: list[TankVarianceRead]
