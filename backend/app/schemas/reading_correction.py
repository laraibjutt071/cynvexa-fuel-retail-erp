import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.reading_correction import ReadingType


class ReadingCorrectionRequest(BaseModel):
    reading_type: ReadingType
    tank_reading_id: uuid.UUID | None = None
    nozzle_reading_id: uuid.UUID | None = None
    corrected_value: Decimal = Field(ge=0)
    reason: str = Field(min_length=1, max_length=1000)


class ReadingCorrectionDecision(BaseModel):
    rejection_reason: str | None = Field(default=None, max_length=500)


class ReadingCorrectionRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    station_id: uuid.UUID
    shift_id: uuid.UUID
    reading_type: str
    tank_reading_id: uuid.UUID | None
    nozzle_reading_id: uuid.UUID | None
    original_value: Decimal
    corrected_value: Decimal
    reason: str
    original_submitted_at: datetime
    is_post_lock: bool
    status: str
    requested_by_user_id: uuid.UUID
    requested_at: datetime
    decided_by_user_id: uuid.UUID | None
    decided_at: datetime | None
    rejection_reason: str | None

    model_config = {"from_attributes": True}
