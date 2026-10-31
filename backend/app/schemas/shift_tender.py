import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ShiftTenderCreate(BaseModel):
    payment_method_id: uuid.UUID
    amount: Decimal = Field(gt=0, decimal_places=2)
    credit_customer_id: uuid.UUID | None = None
    reference: str | None = Field(default=None, max_length=100)


class ShiftTenderReverse(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class ShiftTenderRead(BaseModel):
    id: uuid.UUID
    shift_id: uuid.UUID
    payment_method_id: uuid.UUID
    amount: Decimal
    credit_customer_id: uuid.UUID | None
    reference: str | None
    recorded_by_user_id: uuid.UUID
    recorded_at: datetime
    reversed_by_user_id: uuid.UUID | None
    reversed_at: datetime | None
    reversal_reason: str | None

    model_config = {"from_attributes": True}
