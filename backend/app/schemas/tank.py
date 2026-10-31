import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


class TankCreate(BaseModel):
    fuel_grade_id: uuid.UUID
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=100)
    capacity: Decimal = Field(gt=0)
    safe_fill_limit: Decimal = Field(gt=0)

    @model_validator(mode="after")
    def safe_fill_within_capacity(self) -> "TankCreate":
        if self.safe_fill_limit > self.capacity:
            raise ValueError("safe_fill_limit cannot exceed capacity.")
        return self


class TankUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    safe_fill_limit: Decimal | None = Field(default=None, gt=0)
    is_active: bool | None = None


class TankRead(BaseModel):
    id: uuid.UUID
    station_id: uuid.UUID
    fuel_grade_id: uuid.UUID
    code: str
    name: str
    capacity: Decimal
    safe_fill_limit: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TankStockRead(TankRead):
    book_stock: Decimal
    safe_capacity_available: Decimal
