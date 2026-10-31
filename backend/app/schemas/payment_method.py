import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.payment_method import PaymentMethodCategory


class PaymentMethodCreate(BaseModel):
    code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=100)
    category: PaymentMethodCategory


class PaymentMethodUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    is_active: bool | None = None


class PaymentMethodRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    code: str
    name: str
    category: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
