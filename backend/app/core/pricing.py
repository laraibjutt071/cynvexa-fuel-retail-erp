import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fuel_price import FuelPrice


async def get_current_price(
    db: AsyncSession,
    *,
    station_id: uuid.UUID,
    fuel_grade_id: uuid.UUID,
    as_of: datetime | None = None,
) -> FuelPrice | None:
    """
    The price in effect at `as_of` (default: now) is the row with the latest
    effective_from that is <= as_of. Returns None if no price has ever been
    set for this station+grade at or before that time - callers must decide
    what that means for them (e.g. block a receipt/shift that depends on a
    price that doesn't exist yet), never silently assume a default price.
    """
    as_of = as_of or datetime.now(timezone.utc)
    stmt = (
        select(FuelPrice)
        .where(
            FuelPrice.station_id == station_id,
            FuelPrice.fuel_grade_id == fuel_grade_id,
            FuelPrice.effective_from <= as_of,
        )
        .order_by(FuelPrice.effective_from.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()
