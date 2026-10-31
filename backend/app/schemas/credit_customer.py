import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CreditCustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class CreditCustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    is_active: bool | None = None


class CreditCustomerRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
