import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class SupplierInvoiceCreate(BaseModel):
    tanker_receipt_id: uuid.UUID | None = None
    reference: str | None = Field(default=None, max_length=100)
    amount: Decimal = Field(gt=0, decimal_places=2)
    invoice_date: date
    description: str | None = Field(default=None, max_length=500)


class SupplierInvoiceRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    supplier_id: uuid.UUID
    tanker_receipt_id: uuid.UUID | None
    reference: str | None
    amount: Decimal
    invoice_date: date
    description: str | None
    created_by_user_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class SupplierPaymentCreate(BaseModel):
    amount: Decimal = Field(gt=0, decimal_places=2)
    payment_date: date
    reference: str | None = Field(default=None, max_length=100)


class SupplierPaymentReverse(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class SupplierPaymentRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    supplier_id: uuid.UUID
    amount: Decimal
    payment_date: date
    reference: str | None
    recorded_by_user_id: uuid.UUID
    recorded_at: datetime
    approved_by_user_id: uuid.UUID | None
    approved_at: datetime | None
    reversed_by_user_id: uuid.UUID | None
    reversed_at: datetime | None
    reversal_reason: str | None

    model_config = {"from_attributes": True}


class SupplierBalanceRead(BaseModel):
    supplier_id: uuid.UUID
    supplier_name: str
    balance: Decimal
