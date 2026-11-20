import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class MeterEventRow(BaseModel):
    """
    One flagged meter rollover/reset/replacement, with the station/tank/
    nozzle/shift context needed to show it in a history list without a
    second round-trip - read-only, reuses exactly the same
    ShiftNozzleReading fields app/api/shifts.py's close/approve endpoints
    already write, never a separate calculation.
    """

    nozzle_reading_id: uuid.UUID
    shift_id: uuid.UUID
    shift_label: str | None
    shift_opened_at: datetime
    shift_status: str
    station_id: uuid.UUID
    nozzle_id: uuid.UUID
    nozzle_code: str
    dispenser_code: str
    tank_code: str
    fuel_grade_name: str
    event_type: str
    opening_totalizer: Decimal
    meter_event_pre_reading: Decimal
    meter_event_post_reading: Decimal
    closing_totalizer: Decimal
    dispensed_litres: Decimal | None
    notes: str | None
    recorded_by_user_id: uuid.UUID | None
    recorded_at: datetime | None
    approved_by_user_id: uuid.UUID | None
    approved_at: datetime | None
