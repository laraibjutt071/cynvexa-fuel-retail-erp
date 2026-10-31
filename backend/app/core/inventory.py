import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory_movement import (
    DECREASING_INVENTORY_MOVEMENT_TYPES,
    INCREASING_INVENTORY_MOVEMENT_TYPES,
    InventoryMovement,
)

THREE_PLACES = Decimal("0.001")


async def get_inventory_stock(db: AsyncSession, inventory_item_id: uuid.UUID) -> Decimal:
    """
    The ONLY function that should compute an inventory item's on-hand
    quantity - always derived from the ledger, never from a mutable
    column, mirroring app/core/stock.py::get_book_stock for fuel tanks.
    """
    increasing = (
        await db.execute(
            select(func.coalesce(func.sum(InventoryMovement.quantity), 0)).where(
                InventoryMovement.inventory_item_id == inventory_item_id,
                InventoryMovement.movement_type.in_(
                    [t.value for t in INCREASING_INVENTORY_MOVEMENT_TYPES]
                ),
            )
        )
    ).scalar_one()
    decreasing = (
        await db.execute(
            select(func.coalesce(func.sum(InventoryMovement.quantity), 0)).where(
                InventoryMovement.inventory_item_id == inventory_item_id,
                InventoryMovement.movement_type.in_(
                    [t.value for t in DECREASING_INVENTORY_MOVEMENT_TYPES]
                ),
            )
        )
    ).scalar_one()
    # coalesce(sum(...), 0) over zero rows returns a bare integer-scale
    # Decimal('0'), not the column's Numeric(12,3) scale a real sum would
    # have - quantize explicitly so a brand-new item with no movements
    # yet reports "0.000", not "0", the same shape every other figure
    # here has.
    return (Decimal(increasing) - Decimal(decreasing)).quantize(THREE_PLACES)
