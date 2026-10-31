import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.models.tanker_receipt import PayableQuantityBasis


class TankerReceiptCreate(BaseModel):
    tank_id: uuid.UUID
    supplier_id: uuid.UUID
    tanker_registration: str = Field(min_length=1, max_length=50)
    driver_name: str | None = Field(default=None, max_length=200)
    supplier_invoice_reference: str | None = Field(default=None, max_length=100)
    challan_reference: str | None = Field(default=None, max_length=100)

    invoice_quantity: Decimal | None = Field(default=None, gt=0)
    dispatched_quantity: Decimal | None = Field(default=None, gt=0)
    calibrated_quantity: Decimal | None = Field(default=None, gt=0)

    pre_receipt_tank_reading: Decimal = Field(ge=0)
    pre_receipt_density: Decimal | None = Field(default=None, gt=0)
    pre_receipt_temperature_celsius: Decimal | None = None
    pre_receipt_water_level_cm: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def at_least_one_declared_quantity(self) -> "TankerReceiptCreate":
        if not any((self.invoice_quantity, self.dispatched_quantity, self.calibrated_quantity)):
            raise ValueError(
                "At least one of invoice_quantity, dispatched_quantity or "
                "calibrated_quantity is required to assess tank capacity."
            )
        return self


class TankerReceiptRecordUnload(BaseModel):
    post_receipt_tank_reading: Decimal = Field(ge=0)


class TankerReceiptApprove(BaseModel):
    accepted_quantity: Decimal = Field(gt=0)
    payable_quantity_basis: PayableQuantityBasis
    # Optional: if omitted, derived server-side from whichever field
    # payable_quantity_basis names. Provided explicitly only when the
    # approver is recording a negotiated figure that isn't exactly any
    # single observed quantity - that deviation is then visible in the
    # audit log, not silently substituted.
    payable_quantity: Decimal | None = Field(default=None, gt=0)


class TankerReceiptReject(BaseModel):
    rejection_reason: str = Field(min_length=1, max_length=500)


class TankerReceiptRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    station_id: uuid.UUID
    tank_id: uuid.UUID
    fuel_grade_id: uuid.UUID
    supplier_id: uuid.UUID
    status: str

    tanker_registration: str
    driver_name: str | None
    supplier_invoice_reference: str | None
    challan_reference: str | None

    invoice_quantity: Decimal | None
    dispatched_quantity: Decimal | None
    calibrated_quantity: Decimal | None

    pre_receipt_tank_reading: Decimal
    pre_receipt_density: Decimal | None
    pre_receipt_temperature_celsius: Decimal | None
    pre_receipt_water_level_cm: Decimal | None
    safe_capacity_available_at_creation: Decimal
    created_by_user_id: uuid.UUID

    post_receipt_tank_reading: Decimal | None
    tank_gain_quantity: Decimal | None
    unload_recorded_by_user_id: uuid.UUID | None
    unload_recorded_at: datetime | None

    accepted_quantity: Decimal | None
    payable_quantity_basis: str | None
    payable_quantity: Decimal | None
    variance_quantity: Decimal | None
    variance_percent: Decimal | None
    within_tolerance: bool | None
    rejection_reason: str | None
    decided_by_user_id: uuid.UUID | None
    decided_at: datetime | None

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
