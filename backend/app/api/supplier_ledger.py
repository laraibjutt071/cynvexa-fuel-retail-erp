import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import (
    get_organization_or_404,
    get_supplier_or_404,
    get_supplier_payment_or_404,
)
from app.api.deps import get_db, require_permission
from app.core.audit import write_audit_log
from app.core.csv_export import csv_response
from app.core.permission_codes import SUPPLIER_LEDGER_APPROVE, SUPPLIER_LEDGER_READ, SUPPLIER_LEDGER_RECORD
from app.core.supplier_ledger import get_supplier_balance
from app.exceptions import ConflictError
from app.models.supplier import Supplier
from app.models.supplier_invoice import SupplierInvoice
from app.models.supplier_payment import SupplierPayment
from app.models.user import User
from app.schemas.supplier_ledger import (
    SupplierBalanceRead,
    SupplierInvoiceCreate,
    SupplierInvoiceRead,
    SupplierPaymentCreate,
    SupplierPaymentRead,
    SupplierPaymentReverse,
)

router = APIRouter(prefix="/organizations/{organization_id}/suppliers/{supplier_id}", tags=["supplier-ledger"])
balances_router = APIRouter(prefix="/organizations/{organization_id}/suppliers", tags=["supplier-ledger"])


@router.post("/invoices", response_model=SupplierInvoiceRead, status_code=201)
async def create_supplier_invoice(
    organization_id: uuid.UUID,
    supplier_id: uuid.UUID,
    payload: SupplierInvoiceCreate,
    request: Request,
    current_user: User = Depends(require_permission(SUPPLIER_LEDGER_RECORD)),
    db: AsyncSession = Depends(get_db),
) -> SupplierInvoice:
    await get_supplier_or_404(db, organization_id, supplier_id)

    invoice = SupplierInvoice(
        organization_id=organization_id,
        supplier_id=supplier_id,
        created_by_user_id=current_user.id,
        **payload.model_dump(),
    )
    db.add(invoice)
    await db.flush()

    await write_audit_log(
        db,
        action="supplier_invoice.create",
        entity_type="Supplier",
        entity_id=str(supplier_id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        after={"invoice_id": str(invoice.id), "amount": str(invoice.amount)},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return invoice


@router.get("/invoices", response_model=list[SupplierInvoiceRead])
async def list_supplier_invoices(
    organization_id: uuid.UUID,
    supplier_id: uuid.UUID,
    current_user: User = Depends(require_permission(SUPPLIER_LEDGER_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[SupplierInvoice]:
    await get_supplier_or_404(db, organization_id, supplier_id)
    result = await db.execute(
        select(SupplierInvoice)
        .where(SupplierInvoice.supplier_id == supplier_id)
        .order_by(SupplierInvoice.invoice_date.desc())
    )
    return list(result.scalars().all())


@router.post("/payments", response_model=SupplierPaymentRead, status_code=201)
async def create_supplier_payment(
    organization_id: uuid.UUID,
    supplier_id: uuid.UUID,
    payload: SupplierPaymentCreate,
    request: Request,
    current_user: User = Depends(require_permission(SUPPLIER_LEDGER_RECORD)),
    db: AsyncSession = Depends(get_db),
) -> SupplierPayment:
    await get_supplier_or_404(db, organization_id, supplier_id)

    payment = SupplierPayment(
        organization_id=organization_id,
        supplier_id=supplier_id,
        recorded_by_user_id=current_user.id,
        **payload.model_dump(),
    )
    db.add(payment)
    await db.flush()

    await write_audit_log(
        db,
        action="supplier_payment.create",
        entity_type="Supplier",
        entity_id=str(supplier_id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        after={"payment_id": str(payment.id), "amount": str(payment.amount)},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return payment


@router.get("/payments", response_model=list[SupplierPaymentRead])
async def list_supplier_payments(
    organization_id: uuid.UUID,
    supplier_id: uuid.UUID,
    current_user: User = Depends(require_permission(SUPPLIER_LEDGER_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[SupplierPayment]:
    await get_supplier_or_404(db, organization_id, supplier_id)
    result = await db.execute(
        select(SupplierPayment)
        .where(SupplierPayment.supplier_id == supplier_id)
        .order_by(SupplierPayment.payment_date.desc())
    )
    return list(result.scalars().all())


@router.patch("/payments/{payment_id}/approve", response_model=SupplierPaymentRead)
async def approve_supplier_payment(
    organization_id: uuid.UUID,
    supplier_id: uuid.UUID,
    payment_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_permission(SUPPLIER_LEDGER_APPROVE)),
    db: AsyncSession = Depends(get_db),
) -> SupplierPayment:
    payment = await get_supplier_payment_or_404(db, organization_id, payment_id, for_update=True)
    if payment.supplier_id != supplier_id:
        raise ConflictError("Payment does not belong to this supplier.")
    if payment.reversed_at is not None:
        raise ConflictError("This payment has been reversed and cannot be approved.")
    if payment.approved_by_user_id is not None:
        raise ConflictError("This payment has already been approved.")

    payment.approved_by_user_id = current_user.id
    payment.approved_at = datetime.now(timezone.utc)
    await db.flush()

    await write_audit_log(
        db,
        action="supplier_payment.approve",
        entity_type="Supplier",
        entity_id=str(supplier_id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        after={"payment_id": str(payment.id)},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return payment


@router.patch("/payments/{payment_id}/reverse", response_model=SupplierPaymentRead)
async def reverse_supplier_payment(
    organization_id: uuid.UUID,
    supplier_id: uuid.UUID,
    payment_id: uuid.UUID,
    payload: SupplierPaymentReverse,
    request: Request,
    current_user: User = Depends(require_permission(SUPPLIER_LEDGER_APPROVE)),
    db: AsyncSession = Depends(get_db),
) -> SupplierPayment:
    payment = await get_supplier_payment_or_404(db, organization_id, payment_id, for_update=True)
    if payment.supplier_id != supplier_id:
        raise ConflictError("Payment does not belong to this supplier.")
    if payment.reversed_at is not None:
        raise ConflictError("This payment has already been reversed.")

    payment.reversed_by_user_id = current_user.id
    payment.reversed_at = datetime.now(timezone.utc)
    payment.reversal_reason = payload.reason
    await db.flush()

    await write_audit_log(
        db,
        action="supplier_payment.reverse",
        entity_type="Supplier",
        entity_id=str(supplier_id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        after={"payment_id": str(payment.id), "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return payment


@router.get("/balance", response_model=SupplierBalanceRead)
async def get_supplier_balance_endpoint(
    organization_id: uuid.UUID,
    supplier_id: uuid.UUID,
    current_user: User = Depends(require_permission(SUPPLIER_LEDGER_READ)),
    db: AsyncSession = Depends(get_db),
) -> SupplierBalanceRead:
    supplier = await get_supplier_or_404(db, organization_id, supplier_id)
    balance = await get_supplier_balance(db, supplier_id)
    return SupplierBalanceRead(supplier_id=supplier.id, supplier_name=supplier.name, balance=balance)


@balances_router.get("/balances", response_model=list[SupplierBalanceRead])
async def list_supplier_balances(
    organization_id: uuid.UUID,
    current_user: User = Depends(require_permission(SUPPLIER_LEDGER_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[SupplierBalanceRead]:
    await get_organization_or_404(db, organization_id)
    suppliers = (
        await db.execute(select(Supplier).where(Supplier.organization_id == organization_id))
    ).scalars().all()
    return [
        SupplierBalanceRead(
            supplier_id=s.id, supplier_name=s.name, balance=await get_supplier_balance(db, s.id)
        )
        for s in suppliers
    ]


@balances_router.get("/balances/export")
async def export_supplier_balances(
    organization_id: uuid.UUID,
    current_user: User = Depends(require_permission(SUPPLIER_LEDGER_READ)),
    db: AsyncSession = Depends(get_db),
):
    balances = await list_supplier_balances(organization_id, current_user=current_user, db=db)
    rows = [{"supplier_name": b.supplier_name, "balance": str(b.balance)} for b in balances]
    return csv_response("supplier-balances.csv", ["supplier_name", "balance"], rows)
