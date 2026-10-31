import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    legal_name: str | None = Field(default=None, max_length=300)


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    legal_name: str | None = Field(default=None, max_length=300)
    is_active: bool | None = None
    currency_code: str | None = Field(default=None, min_length=3, max_length=3)


class OrganizationRead(BaseModel):
    id: uuid.UUID
    name: str
    legal_name: str | None
    is_active: bool
    currency_code: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
