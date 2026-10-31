import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock_ledger_entry import (
    DECREASING_MOVEMENT_TYPES,
    INCREASING_MOVEMENT_TYPES,
    StockLedgerEntry,
)

THREE_PLACES = Decimal("0.001")


async def get_book_stock(
    db: AsyncSession, tank_id: uuid.UUID, *, as_of: datetime | None = None
) -> Decimal:
    """
    The ONLY function that should compute a tank's book stock. It is always
    derived from the ledger, never read from a mutable column - see
    StockLedgerEntry's docstring. A physical dip/ATG reading is a separate
    fact (recorded on whatever entity observed it) and must never be
    substituted for this.

    as_of restricts the sum to ledger entries created at or before that
    timestamp - used for point-in-time reporting (e.g. "book stock at the
    moment this shift opened"), never for the live/current figure used in a
    capacity or variance decision, which must always omit it.
    """
    increasing_stmt = (
        select(func.coalesce(func.sum(StockLedgerEntry.quantity), 0))
        .where(StockLedgerEntry.tank_id == tank_id)
        .where(StockLedgerEntry.movement_type.in_([t.value for t in INCREASING_MOVEMENT_TYPES]))
    )
    decreasing_stmt = (
        select(func.coalesce(func.sum(StockLedgerEntry.quantity), 0))
        .where(StockLedgerEntry.tank_id == tank_id)
        .where(StockLedgerEntry.movement_type.in_([t.value for t in DECREASING_MOVEMENT_TYPES]))
    )
    if as_of is not None:
        increasing_stmt = increasing_stmt.where(StockLedgerEntry.created_at <= as_of)
        decreasing_stmt = decreasing_stmt.where(StockLedgerEntry.created_at <= as_of)

    increasing_total = (await db.execute(increasing_stmt)).scalar_one()
    decreasing_total = (await db.execute(decreasing_stmt)).scalar_one()
    # coalesce(sum(...), 0) over zero rows returns a bare integer-scale
    # Decimal('0'), not the column's Numeric(12,3) scale a real sum would
    # carry - quantize explicitly so a tank with no ledger entries yet
    # reports "0.000", the same shape every other figure here has, not a
    # differently-formatted "0".
    return (Decimal(increasing_total) - Decimal(decreasing_total)).quantize(THREE_PLACES)
