import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class CreditCustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    contact_person: str | None = Field(default=None, max_length=200)
    credit_limit: Decimal | None = Field(default=None, ge=0)
    payment_terms_days: int | None = Field(default=None, gt=0)
    address: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=1000)


class CreditCustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    contact_person: str | None = Field(default=None, max_length=200)
    credit_limit: Decimal | None = Field(default=None, ge=0)
    payment_terms_days: int | None = Field(default=None, gt=0)
    address: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=1000)
    is_active: bool | None = None


class CreditCustomerRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    phone: str | None
    contact_person: str | None
    credit_limit: Decimal | None
    payment_terms_days: int | None
    address: str | None
    notes: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
