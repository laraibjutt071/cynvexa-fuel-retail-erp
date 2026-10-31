import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class FuelPriceCreate(BaseModel):
    fuel_grade_id: uuid.UUID
    price_per_litre: Decimal = Field(gt=0, decimal_places=4)
    effective_from: datetime


class FuelPriceRead(BaseModel):
    id: uuid.UUID
    station_id: uuid.UUID
    fuel_grade_id: uuid.UUID
    price_per_litre: Decimal
    effective_from: datetime
    created_by_user_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
