import uuid
from decimal import Decimal

from pydantic import BaseModel


class NozzleOverviewRead(BaseModel):
    """
    Everything the Daily Entry workspace needs to pre-fill and label one
    nozzle's reading row in a single call, rather than the frontend
    stitching this together from several nested list endpoints
    (dispensers -> nozzles -> shift history) on every page load.
    """

    nozzle_id: uuid.UUID
    nozzle_code: str
    dispenser_id: uuid.UUID
    dispenser_code: str
    tank_id: uuid.UUID
    tank_code: str
    fuel_grade_id: uuid.UUID
    fuel_grade_name: str
    # The most recent closed nozzle reading's closing_totalizer across any
    # shift - this IS "today's opening reading" under the append-only
    # reading model; never stored redundantly, always looked up fresh.
    last_closing_totalizer: Decimal | None
    current_price_per_litre: Decimal | None
