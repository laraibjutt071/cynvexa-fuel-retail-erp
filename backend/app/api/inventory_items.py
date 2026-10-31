import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_inventory_item_or_404, get_station_or_404
from app.api.deps import get_db, require_permission
from app.core.audit import write_audit_log
from app.core.inventory import get_inventory_stock
from app.core.permission_codes import INVENTORY_ITEM_MANAGE, INVENTORY_ITEM_READ
from app.exceptions import ConflictError
from app.models.inventory_item import InventoryItem
from app.models.user import User
from app.schemas.inventory import InventoryItemCreate, InventoryItemRead, InventoryItemUpdate, InventoryItemWithStockRead
from sqlalchemy.exc import IntegrityError

router = APIRouter(
    prefix="/organizations/{organization_id}/stations/{station_id}/inventory-items", tags=["inventory"]
)


@router.post("", response_model=InventoryItemRead, status_code=201)
async def create_inventory_item(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    payload: InventoryItemCreate,
    request: Request,
    current_user: User = Depends(require_permission(INVENTORY_ITEM_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> InventoryItem:
    await get_station_or_404(db, organization_id, station_id)

    item = InventoryItem(organization_id=organization_id, station_id=station_id, **payload.model_dump())
    db.add(item)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ConflictError(f"SKU '{payload.sku}' already exists at this station.")

    await write_audit_log(
        db,
        action="inventory_item.create",
        entity_type="InventoryItem",
        entity_id=str(item.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={"sku": item.sku, "name": item.name},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return item


@router.get("", response_model=list[InventoryItemWithStockRead])
async def list_inventory_items(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    current_user: User = Depends(require_permission(INVENTORY_ITEM_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[InventoryItemWithStockRead]:
    await get_station_or_404(db, organization_id, station_id)
    items = (
        await db.execute(select(InventoryItem).where(InventoryItem.station_id == station_id))
    ).scalars().all()
    out = []
    for item in items:
        on_hand = await get_inventory_stock(db, item.id)
        out.append(
            InventoryItemWithStockRead(
                **InventoryItemRead.model_validate(item).model_dump(),
                on_hand=on_hand,
                below_reorder_level=on_hand < item.reorder_level,
            )
        )
    return out


@router.patch("/{inventory_item_id}", response_model=InventoryItemRead)
async def update_inventory_item(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    inventory_item_id: uuid.UUID,
    payload: InventoryItemUpdate,
    request: Request,
    current_user: User = Depends(require_permission(INVENTORY_ITEM_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> InventoryItem:
    item = await get_inventory_item_or_404(db, station_id, inventory_item_id)

    before = {"name": item.name, "unit": item.unit, "reorder_level": str(item.reorder_level), "is_active": item.is_active}
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(item, field, value)
    await db.flush()
    after = {"name": item.name, "unit": item.unit, "reorder_level": str(item.reorder_level), "is_active": item.is_active}

    await write_audit_log(
        db,
        action="inventory_item.update",
        entity_type="InventoryItem",
        entity_id=str(item.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        before=before,
        after=after,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return item
