import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.inventory_movement import InventoryMovementType


class InventoryItemCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=200)
    unit: str = Field(min_length=1, max_length=20)
    reorder_level: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=3)


class InventoryItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    unit: str | None = Field(default=None, min_length=1, max_length=20)
    reorder_level: Decimal | None = Field(default=None, ge=0, decimal_places=3)
    is_active: bool | None = None


class InventoryItemRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    station_id: uuid.UUID
    sku: str
    name: str
    unit: str
    reorder_level: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class InventoryItemWithStockRead(InventoryItemRead):
    on_hand: Decimal
    below_reorder_level: bool


class InventoryMovementCreate(BaseModel):
    inventory_item_id: uuid.UUID
    movement_type: InventoryMovementType
    quantity: Decimal = Field(gt=0, decimal_places=3)
    amount: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    reference: str | None = Field(default=None, max_length=100)
    reason: str | None = Field(default=None, max_length=500)


class InventoryMovementRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    station_id: uuid.UUID
    inventory_item_id: uuid.UUID
    movement_type: str
    quantity: Decimal
    amount: Decimal | None
    reference: str | None
    reason: str | None
    created_by_user_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}
