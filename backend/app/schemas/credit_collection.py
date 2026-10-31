import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class CreditCustomerPaymentCreate(BaseModel):
    amount: Decimal = Field(gt=0, decimal_places=2)
    payment_date: date
    reference: str | None = Field(default=None, max_length=100)


class CreditCustomerPaymentReverse(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class CreditCustomerPaymentRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    credit_customer_id: uuid.UUID
    amount: Decimal
    payment_date: date
    reference: str | None
    recorded_by_user_id: uuid.UUID
    recorded_at: datetime
    reversed_by_user_id: uuid.UUID | None
    reversed_at: datetime | None
    reversal_reason: str | None

    model_config = {"from_attributes": True}


class CreditCustomerBalanceRead(BaseModel):
    credit_customer_id: uuid.UUID
    credit_customer_name: str
    balance: Decimal
