import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class FuelGradeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=1, max_length=20)


class FuelGradeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    is_active: bool | None = None


class FuelGradeRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    code: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
