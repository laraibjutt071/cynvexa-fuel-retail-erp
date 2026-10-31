import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class NozzleCreate(BaseModel):
    tank_id: uuid.UUID
    code: str = Field(min_length=1, max_length=20)


class NozzleUpdate(BaseModel):
    is_active: bool | None = None


class NozzleRead(BaseModel):
    id: uuid.UUID
    dispenser_id: uuid.UUID
    tank_id: uuid.UUID
    code: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
