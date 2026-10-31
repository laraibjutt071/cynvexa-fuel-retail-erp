import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ShiftReconciliationCreate(BaseModel):
    actual_physical_cash: Decimal = Field(ge=0, decimal_places=2)
    # Required by the API (not here) only when the computed variance turns
    # out to be material - see app/api/shift_reconciliation.py.
    explanation: str | None = Field(default=None, max_length=1000)


class ShiftReconciliationAuthorize(BaseModel):
    """Empty body - the action itself is the authorization."""

    pass


class ShiftReconciliationRead(BaseModel):
    id: uuid.UUID
    shift_id: uuid.UUID
    expected_fuel_revenue: Decimal
    total_tender_amount: Decimal
    revenue_variance: Decimal
    revenue_variance_percent: Decimal
    revenue_within_tolerance: bool
    expected_physical_cash: Decimal
    actual_physical_cash: Decimal
    cash_shortage_excess: Decimal
    cash_within_tolerance: bool
    requires_authorization: bool
    explanation: str | None
    authorized_by_user_id: uuid.UUID | None
    authorized_at: datetime | None
    created_by_user_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class ShiftReconciliationAmendmentCreate(BaseModel):
    field_name: str = Field(min_length=1, max_length=50)
    new_value: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=1000)


class ShiftReconciliationAmendmentDecide(BaseModel):
    rejection_reason: str | None = Field(default=None, max_length=500)


class ShiftReconciliationAmendmentRead(BaseModel):
    id: uuid.UUID
    reconciliation_id: uuid.UUID
    field_name: str
    previous_value: str
    new_value: str
    reason: str
    status: str
    requested_by_user_id: uuid.UUID
    requested_at: datetime
    decided_by_user_id: uuid.UUID | None
    decided_at: datetime | None
    rejection_reason: str | None

    model_config = {"from_attributes": True}
