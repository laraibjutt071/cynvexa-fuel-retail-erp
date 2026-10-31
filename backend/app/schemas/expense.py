import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ExpenseCreate(BaseModel):
    station_id: uuid.UUID | None = None
    category: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=500)
    amount: Decimal = Field(gt=0, decimal_places=2)
    expense_date: date


class ExpenseReject(BaseModel):
    rejection_reason: str = Field(min_length=1, max_length=500)


class ExpenseReverse(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class ExpenseRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    station_id: uuid.UUID | None
    category: str
    description: str
    amount: Decimal
    expense_date: date
    status: str
    created_by_user_id: uuid.UUID
    created_at: datetime
    decided_by_user_id: uuid.UUID | None
    decided_at: datetime | None
    rejection_reason: str | None
    reversed_by_user_id: uuid.UUID | None
    reversed_at: datetime | None
    reversal_reason: str | None

    model_config = {"from_attributes": True}
