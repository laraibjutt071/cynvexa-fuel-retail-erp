import uuid
from decimal import Decimal

from pydantic import BaseModel, Field


class PlanCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    price_monthly: Decimal = Field(ge=0, decimal_places=2)
    price_annual: Decimal = Field(ge=0, decimal_places=2)
    max_stations: int | None = Field(default=None, gt=0)
    max_users: int | None = Field(default=None, gt=0)


class PlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    price_monthly: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    price_annual: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    max_stations: int | None = Field(default=None, gt=0)
    max_users: int | None = Field(default=None, gt=0)
    is_active: bool | None = None


class PlanRead(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None
    price_monthly: Decimal
    price_annual: Decimal
    max_stations: int | None
    max_users: int | None
    is_active: bool

    model_config = {"from_attributes": True}
