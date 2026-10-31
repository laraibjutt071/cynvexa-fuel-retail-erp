import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.revenue import round_money
from app.models.supplier_invoice import SupplierInvoice
from app.models.supplier_payment import SupplierPayment


async def get_supplier_balance(db: AsyncSession, supplier_id: uuid.UUID) -> Decimal:
    """
    Amount currently owed TO this supplier: sum of every invoice minus sum
    of every APPROVED, non-reversed payment. An unapproved or reversed
    payment does not reduce the balance - the same control point as a
    decreasing ShiftCashMovement not counting toward a shift reconciliation
    until approved.
    """
    invoiced = (
        await db.execute(
            select(func.coalesce(func.sum(SupplierInvoice.amount), 0)).where(
                SupplierInvoice.supplier_id == supplier_id
            )
        )
    ).scalar_one()
    paid = (
        await db.execute(
            select(func.coalesce(func.sum(SupplierPayment.amount), 0)).where(
                SupplierPayment.supplier_id == supplier_id,
                SupplierPayment.approved_by_user_id.is_not(None),
                SupplierPayment.reversed_at.is_(None),
            )
        )
    ).scalar_one()
    # coalesce(sum(...), 0) over zero rows returns a bare Decimal('0'),
    # not the column's 2-decimal money scale a real sum would carry -
    # round_money (this app's one money-rounding rule) makes a supplier
    # with no invoices yet report "0.00" like every other money figure,
    # not a differently-formatted "0".
    return round_money(Decimal(invoiced) - Decimal(paid))
