import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class SupplierCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    contact_phone: str | None = Field(default=None, max_length=50)
    contact_email: EmailStr | None = None


class SupplierUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    contact_phone: str | None = Field(default=None, max_length=50)
    contact_email: EmailStr | None = None
    is_active: bool | None = None


class SupplierRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    contact_phone: str | None
    contact_email: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
