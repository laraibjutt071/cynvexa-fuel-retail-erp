import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.revenue import round_money
from app.models.credit_customer_payment import CreditCustomerPayment
from app.models.shift_tender import ShiftTender


async def get_credit_customer_balance(db: AsyncSession, credit_customer_id: uuid.UUID) -> Decimal:
    """
    Receivable currently owed BY this customer: sum of every non-reversed
    credit-category ShiftTender referencing them, minus sum of every
    non-reversed collection (CreditCustomerPayment). Reads ShiftTender
    directly rather than duplicating the receivable into a second ledger -
    the same non-duplication principle app/core/reconciliation.py applies
    to cash.
    """
    sold = (
        await db.execute(
            select(func.coalesce(func.sum(ShiftTender.amount), 0)).where(
                ShiftTender.credit_customer_id == credit_customer_id,
                ShiftTender.reversed_at.is_(None),
            )
        )
    ).scalar_one()
    collected = (
        await db.execute(
            select(func.coalesce(func.sum(CreditCustomerPayment.amount), 0)).where(
                CreditCustomerPayment.credit_customer_id == credit_customer_id,
                CreditCustomerPayment.reversed_at.is_(None),
            )
        )
    ).scalar_one()
    # Same formatting-consistency reason as app/core/supplier_ledger.py:
    # round_money makes a customer with no sales yet report "0.00", not a
    # differently-formatted "0".
    return round_money(Decimal(sold) - Decimal(collected))
