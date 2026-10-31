import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_station_or_404, get_supplier_or_404, get_tank_or_404
from app.api.deps import get_db, require_permission
from app.core.audit import write_audit_log
from app.core.permission_codes import FUEL_RECEIPT_APPROVE, FUEL_RECEIPT_CREATE, FUEL_RECEIPT_READ
from app.core.stock import get_book_stock
from app.core.storage import save_evidence_upload
from app.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.models.attachment import Attachment
from app.models.stock_ledger_entry import StockLedgerEntry, StockMovementType
from app.models.tanker_receipt import ReceiptStatus, TankerReceipt
from app.models.user import User
from app.schemas.attachment import AttachmentRead
from app.schemas.tanker_receipt import (
    TankerReceiptApprove,
    TankerReceiptCreate,
    TankerReceiptRead,
    TankerReceiptRecordUnload,
    TankerReceiptReject,
)

router = APIRouter(
    prefix="/organizations/{organization_id}/stations/{station_id}/tanker-receipts",
    tags=["tanker-receipts"],
)

ENTITY_TYPE = "TankerReceipt"


def _decimal_fields(obj, fields: list[str]) -> dict:
    return {f: (str(v) if isinstance(v := getattr(obj, f), Decimal) else v) for f in fields}


async def _get_receipt_or_404(
    db: AsyncSession, station_id: uuid.UUID, receipt_id: uuid.UUID, *, for_update: bool = False
) -> TankerReceipt:
    stmt = select(TankerReceipt).where(
        TankerReceipt.id == receipt_id, TankerReceipt.station_id == station_id
    )
    if for_update:
        stmt = stmt.with_for_update()
    receipt = (await db.execute(stmt)).scalar_one_or_none()
    if receipt is None:
        raise NotFoundError("Tanker receipt not found.")
    return receipt


@router.post("", response_model=TankerReceiptRead, status_code=201)
async def create_tanker_receipt(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    payload: TankerReceiptCreate,
    request: Request,
    current_user: User = Depends(require_permission(FUEL_RECEIPT_CREATE)),
    db: AsyncSession = Depends(get_db),
) -> TankerReceipt:
    station = await get_station_or_404(db, organization_id, station_id)
    await get_supplier_or_404(db, organization_id, payload.supplier_id)
    # Locked even at creation (not just approval) so the capacity figure
    # shown to the person creating the receipt is never stale relative to a
    # concurrently-approving receipt on the same tank.
    tank = await get_tank_or_404(db, station_id, payload.tank_id, for_update=True)

    if station.require_density and payload.pre_receipt_density is None:
        raise ValidationFailedError("This station requires density to be recorded on receipt.")
    if station.require_temperature and payload.pre_receipt_temperature_celsius is None:
        raise ValidationFailedError("This station requires temperature to be recorded on receipt.")
    if station.require_water_check and payload.pre_receipt_water_level_cm is None:
        raise ValidationFailedError("This station requires a water level check to be recorded on receipt.")

    book_stock = await get_book_stock(db, tank.id)
    safe_capacity_available = tank.safe_fill_limit - book_stock

    declared_quantities = [
        q
        for q in (payload.invoice_quantity, payload.dispatched_quantity, payload.calibrated_quantity)
        if q is not None
    ]
    expected_quantity = max(declared_quantities)
    if expected_quantity > safe_capacity_available:
        raise ConflictError(
            f"Insufficient tank capacity: {safe_capacity_available} litres available in tank "
            f"'{tank.code}', but the declared quantity is {expected_quantity} litres."
        )

    receipt = TankerReceipt(
        organization_id=organization_id,
        station_id=station_id,
        fuel_grade_id=tank.fuel_grade_id,
        created_by_user_id=current_user.id,
        status=ReceiptStatus.PENDING_UNLOAD.value,
        safe_capacity_available_at_creation=safe_capacity_available,
        **payload.model_dump(),
    )
    db.add(receipt)
    await db.flush()

    await write_audit_log(
        db,
        action="tanker_receipt.create",
        entity_type=ENTITY_TYPE,
        entity_id=str(receipt.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={
            "tank_id": str(receipt.tank_id),
            "tanker_registration": receipt.tanker_registration,
            **_decimal_fields(
                receipt, ["invoice_quantity", "dispatched_quantity", "calibrated_quantity"]
            ),
        },
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return receipt


@router.get("", response_model=list[TankerReceiptRead])
async def list_tanker_receipts(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    status: str | None = None,
    current_user: User = Depends(require_permission(FUEL_RECEIPT_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[TankerReceipt]:
    stmt = select(TankerReceipt).where(TankerReceipt.station_id == station_id)
    if status is not None:
        stmt = stmt.where(TankerReceipt.status == status)
    stmt = stmt.order_by(TankerReceipt.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{receipt_id}", response_model=TankerReceiptRead)
async def get_tanker_receipt(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    receipt_id: uuid.UUID,
    current_user: User = Depends(require_permission(FUEL_RECEIPT_READ)),
    db: AsyncSession = Depends(get_db),
) -> TankerReceipt:
    return await _get_receipt_or_404(db, station_id, receipt_id)


@router.patch("/{receipt_id}/record-unload", response_model=TankerReceiptRead)
async def record_unload(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    receipt_id: uuid.UUID,
    payload: TankerReceiptRecordUnload,
    request: Request,
    current_user: User = Depends(require_permission(FUEL_RECEIPT_CREATE)),
    db: AsyncSession = Depends(get_db),
) -> TankerReceipt:
    receipt = await _get_receipt_or_404(db, station_id, receipt_id, for_update=True)
    if receipt.status != ReceiptStatus.PENDING_UNLOAD.value:
        raise ConflictError(
            f"Receipt is '{receipt.status}', not '{ReceiptStatus.PENDING_UNLOAD.value}' - "
            "the unload reading cannot be (re)recorded."
        )

    if payload.post_receipt_tank_reading < receipt.pre_receipt_tank_reading:
        raise ValidationFailedError(
            "post_receipt_tank_reading cannot be lower than pre_receipt_tank_reading - "
            "a tanker receipt cannot result in a negative tank gain."
        )

    before = {"status": receipt.status}
    receipt.post_receipt_tank_reading = payload.post_receipt_tank_reading
    receipt.tank_gain_quantity = payload.post_receipt_tank_reading - receipt.pre_receipt_tank_reading
    receipt.unload_recorded_by_user_id = current_user.id
    receipt.unload_recorded_at = datetime.now(timezone.utc)
    receipt.status = ReceiptStatus.AWAITING_APPROVAL.value
    await db.flush()

    await write_audit_log(
        db,
        action="tanker_receipt.record_unload",
        entity_type=ENTITY_TYPE,
        entity_id=str(receipt.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        before=before,
        after={
            "status": receipt.status,
            **_decimal_fields(receipt, ["post_receipt_tank_reading", "tank_gain_quantity"]),
        },
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return receipt


@router.patch("/{receipt_id}/approve", response_model=TankerReceiptRead)
async def approve_receipt(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    receipt_id: uuid.UUID,
    payload: TankerReceiptApprove,
    request: Request,
    current_user: User = Depends(require_permission(FUEL_RECEIPT_APPROVE)),
    db: AsyncSession = Depends(get_db),
) -> TankerReceipt:
    receipt = await _get_receipt_or_404(db, station_id, receipt_id, for_update=True)
    if receipt.status != ReceiptStatus.AWAITING_APPROVAL.value:
        # Covers both "approve a receipt twice" (duplicate/replayed approval)
        # and "approve one that was never unloaded" - both are a conflict
        # with the receipt's current state, not a fresh business decision.
        raise ConflictError(
            f"Receipt is '{receipt.status}', not '{ReceiptStatus.AWAITING_APPROVAL.value}' - it "
            "cannot be approved from this state."
        )

    station = await get_station_or_404(db, organization_id, station_id)
    if station.require_receipt_evidence:
        has_evidence = (
            await db.execute(
                select(Attachment.id).where(
                    Attachment.entity_type == ENTITY_TYPE, Attachment.entity_id == receipt.id
                )
            )
        ).first()
        if has_evidence is None:
            raise ValidationFailedError(
                "This station requires at least one evidence attachment before a receipt can be approved."
            )

    basis_field = payload.payable_quantity_basis.value
    basis_value = getattr(receipt, basis_field)
    if basis_value is None:
        raise ValidationFailedError(
            f"Cannot use '{basis_field}' as the payable basis - it was never recorded on this receipt."
        )

    # Re-lock and re-check capacity against the CURRENT ledger, not the
    # snapshot taken at creation time - another receipt on this tank may
    # have been approved in between. with_for_update() on the tank row
    # serializes this against any other approval for the same tank.
    tank = await get_tank_or_404(db, station_id, receipt.tank_id, for_update=True)
    book_stock = await get_book_stock(db, tank.id)
    safe_capacity_available = tank.safe_fill_limit - book_stock
    if payload.accepted_quantity > safe_capacity_available:
        raise ConflictError(
            f"Insufficient tank capacity: {safe_capacity_available} litres available in tank "
            f"'{tank.code}', but accepting {payload.accepted_quantity} litres was requested."
        )

    payable_quantity = payload.payable_quantity if payload.payable_quantity is not None else basis_value
    variance_quantity = payload.accepted_quantity - basis_value
    variance_percent = (
        (variance_quantity / basis_value * 100) if basis_value != 0 else Decimal(0)
    )
    within_tolerance = abs(variance_percent) <= station.receipt_tolerance_percent

    receipt.accepted_quantity = payload.accepted_quantity
    receipt.payable_quantity_basis = basis_field
    receipt.payable_quantity = payable_quantity
    receipt.variance_quantity = variance_quantity
    receipt.variance_percent = variance_percent
    receipt.within_tolerance = within_tolerance
    receipt.decided_by_user_id = current_user.id
    receipt.decided_at = datetime.now(timezone.utc)
    receipt.status = ReceiptStatus.APPROVED.value

    db.add(
        StockLedgerEntry(
            tank_id=receipt.tank_id,
            movement_type=StockMovementType.RECEIPT.value,
            quantity=payload.accepted_quantity,
            reference_type=ENTITY_TYPE,
            reference_id=receipt.id,
            created_by_user_id=current_user.id,
        )
    )
    await db.flush()

    await write_audit_log(
        db,
        action="tanker_receipt.approve",
        entity_type=ENTITY_TYPE,
        entity_id=str(receipt.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={
            "status": receipt.status,
            "payable_quantity_basis": basis_field,
            "within_tolerance": within_tolerance,
            **_decimal_fields(
                receipt,
                ["accepted_quantity", "payable_quantity", "variance_quantity", "variance_percent"],
            ),
        },
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return receipt


@router.patch("/{receipt_id}/reject", response_model=TankerReceiptRead)
async def reject_receipt(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    receipt_id: uuid.UUID,
    payload: TankerReceiptReject,
    request: Request,
    current_user: User = Depends(require_permission(FUEL_RECEIPT_APPROVE)),
    db: AsyncSession = Depends(get_db),
) -> TankerReceipt:
    receipt = await _get_receipt_or_404(db, station_id, receipt_id, for_update=True)
    if receipt.status not in (ReceiptStatus.PENDING_UNLOAD.value, ReceiptStatus.AWAITING_APPROVAL.value):
        raise ConflictError(f"Receipt is already '{receipt.status}' and cannot be rejected.")

    before = {"status": receipt.status}
    receipt.status = ReceiptStatus.REJECTED.value
    receipt.rejection_reason = payload.rejection_reason
    receipt.decided_by_user_id = current_user.id
    receipt.decided_at = datetime.now(timezone.utc)
    await db.flush()

    await write_audit_log(
        db,
        action="tanker_receipt.reject",
        entity_type=ENTITY_TYPE,
        entity_id=str(receipt.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        before=before,
        after={"status": receipt.status, "rejection_reason": receipt.rejection_reason},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return receipt


# --- Evidence attachments ---


@router.post("/{receipt_id}/attachments", response_model=AttachmentRead, status_code=201)
async def upload_receipt_attachment(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    receipt_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(require_permission(FUEL_RECEIPT_CREATE)),
    db: AsyncSession = Depends(get_db),
) -> Attachment:
    receipt = await _get_receipt_or_404(db, station_id, receipt_id)

    storage_key, size_bytes = await save_evidence_upload(
        file, organization_id=organization_id, entity_type=ENTITY_TYPE, entity_id=receipt.id
    )
    attachment = Attachment(
        organization_id=organization_id,
        entity_type=ENTITY_TYPE,
        entity_id=receipt.id,
        original_filename=file.filename or "file",
        content_type=file.content_type or "application/octet-stream",
        size_bytes=size_bytes,
        storage_backend="local",
        storage_key=storage_key,
        uploaded_by_user_id=current_user.id,
    )
    db.add(attachment)
    await db.flush()

    await write_audit_log(
        db,
        action="tanker_receipt.attach_evidence",
        entity_type=ENTITY_TYPE,
        entity_id=str(receipt.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={"attachment_id": str(attachment.id), "filename": attachment.original_filename},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return attachment


@router.get("/{receipt_id}/attachments", response_model=list[AttachmentRead])
async def list_receipt_attachments(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    receipt_id: uuid.UUID,
    current_user: User = Depends(require_permission(FUEL_RECEIPT_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[Attachment]:
    receipt = await _get_receipt_or_404(db, station_id, receipt_id)
    result = await db.execute(
        select(Attachment).where(
            Attachment.entity_type == ENTITY_TYPE, Attachment.entity_id == receipt.id
        )
    )
    return list(result.scalars().all())
