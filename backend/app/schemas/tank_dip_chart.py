import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class TankDipChartEntryCreate(BaseModel):
    dip_mm: Decimal = Field(ge=0, decimal_places=1, description="Physical dip-stick reading, in millimetres.")
    volume_litres: Decimal = Field(ge=0, decimal_places=3)


class TankDipChartEntryRead(BaseModel):
    id: uuid.UUID
    tank_id: uuid.UUID
    dip_mm: Decimal
    volume_litres: Decimal
    created_by_user_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TankDipChartLookupResult(BaseModel):
    dip_mm: Decimal
    volume_litres: Decimal
    # True only when dip_mm landed exactly on a recorded calibration point -
    # otherwise the result is linearly interpolated between the two
    # nearest points, same as reading between two rows of a paper chart.
    exact_match: bool
