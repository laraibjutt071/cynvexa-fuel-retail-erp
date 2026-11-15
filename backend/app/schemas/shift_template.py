import uuid
from datetime import datetime, time

from pydantic import BaseModel, Field


class ShiftTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    start_time: time
    end_time: time
    grace_period_minutes: int = Field(default=15, ge=0)


class ShiftTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    start_time: time | None = None
    end_time: time | None = None
    grace_period_minutes: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class ShiftTemplateRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    station_id: uuid.UUID
    name: str
    start_time: time
    end_time: time
    grace_period_minutes: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
