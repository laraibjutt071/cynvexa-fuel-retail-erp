import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.shift_cash_movement import CashMovementType


class ShiftCashMovementCreate(BaseModel):
    movement_type: CashMovementType
    amount: Decimal = Field(gt=0, decimal_places=2)
    reason: str = Field(min_length=1, max_length=500)


class ShiftCashMovementReverse(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class ShiftCashMovementRead(BaseModel):
    id: uuid.UUID
    shift_id: uuid.UUID
    movement_type: str
    amount: Decimal
    reason: str
    recorded_by_user_id: uuid.UUID
    recorded_at: datetime
    approved_by_user_id: uuid.UUID | None
    approved_at: datetime | None
    reversed_by_user_id: uuid.UUID | None
    reversed_at: datetime | None
    reversal_reason: str | None

    model_config = {"from_attributes": True}
