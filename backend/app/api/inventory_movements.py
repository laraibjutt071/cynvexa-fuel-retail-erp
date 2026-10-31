import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_inventory_item_or_404, get_station_or_404
from app.api.deps import get_db, require_permission
from app.core.audit import write_audit_log
from app.core.inventory import get_inventory_stock
from app.core.permission_codes import INVENTORY_MOVEMENT_ADJUST, INVENTORY_MOVEMENT_READ, INVENTORY_MOVEMENT_RECORD
from app.core.permissions import user_has_permission
from app.exceptions import PermissionDeniedError, ValidationFailedError
from app.models.inventory_movement import DECREASING_INVENTORY_MOVEMENT_TYPES, InventoryMovement, InventoryMovementType
from app.models.user import User
from app.schemas.inventory import InventoryMovementCreate, InventoryMovementRead

router = APIRouter(
    prefix="/organizations/{organization_id}/stations/{station_id}/inventory-movements", tags=["inventory"]
)

ADJUSTMENT_TYPES = {InventoryMovementType.ADJUSTMENT_INCREASE, InventoryMovementType.ADJUSTMENT_DECREASE}


@router.post("", response_model=InventoryMovementRead, status_code=201)
async def record_inventory_movement(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    payload: InventoryMovementCreate,
    request: Request,
    current_user: User = Depends(require_permission(INVENTORY_MOVEMENT_RECORD)),
    db: AsyncSession = Depends(get_db),
) -> InventoryMovement:
    await get_station_or_404(db, organization_id, station_id)

    if payload.movement_type in ADJUSTMENT_TYPES:
        allowed = current_user.is_superuser or await user_has_permission(
            db,
            user_id=current_user.id,
            organization_id=organization_id,
            station_id=station_id,
            permission_code=INVENTORY_MOVEMENT_ADJUST,
        )
        if not allowed:
            raise PermissionDeniedError("Recording a stock adjustment requires the inventory adjust permission.")
        if not payload.reason:
            raise ValidationFailedError("An adjustment movement requires a reason.")

    item = await get_inventory_item_or_404(db, station_id, payload.inventory_item_id, for_update=True)

    if payload.movement_type in DECREASING_INVENTORY_MOVEMENT_TYPES:
        on_hand = await get_inventory_stock(db, item.id)
        if payload.quantity > on_hand:
            raise ValidationFailedError(
                f"Insufficient stock for '{item.name}': {on_hand} {item.unit} on hand, "
                f"but {payload.quantity} {item.unit} were requested."
            )

    movement = InventoryMovement(
        organization_id=organization_id,
        station_id=station_id,
        created_by_user_id=current_user.id,
        **payload.model_dump(exclude={"movement_type"}),
        movement_type=payload.movement_type.value,
    )
    db.add(movement)
    await db.flush()

    await write_audit_log(
        db,
        action="inventory_movement.create",
        entity_type="InventoryItem",
        entity_id=str(item.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={
            "movement_id": str(movement.id),
            "movement_type": movement.movement_type,
            "quantity": str(movement.quantity),
        },
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return movement


@router.get("", response_model=list[InventoryMovementRead])
async def list_inventory_movements(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    inventory_item_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(require_permission(INVENTORY_MOVEMENT_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[InventoryMovement]:
    stmt = select(InventoryMovement).where(InventoryMovement.station_id == station_id)
    if inventory_item_id is not None:
        stmt = stmt.where(InventoryMovement.inventory_item_id == inventory_item_id)
    stmt = stmt.order_by(InventoryMovement.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())
