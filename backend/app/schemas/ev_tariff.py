import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.ev_tariff import EVPricingBasis


class EVTariffCreate(BaseModel):
    charger_id: uuid.UUID | None = Field(
        default=None, description="Leave null for a station-wide default tariff."
    )
    pricing_basis: EVPricingBasis
    rate: Decimal = Field(gt=0, decimal_places=4)
    effective_from: datetime


class EVTariffRead(BaseModel):
    id: uuid.UUID
    station_id: uuid.UUID
    charger_id: uuid.UUID | None
    pricing_basis: str
    rate: Decimal
    effective_from: datetime
    effective_to: datetime | None
    created_by_user_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
