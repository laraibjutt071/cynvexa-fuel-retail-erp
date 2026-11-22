import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_credit_customer_or_404, get_credit_customer_payment_or_404, get_organization_or_404
from app.api.deps import get_db, require_permission
from app.core.audit import write_audit_log
from app.core.credit_ledger import get_credit_customer_balance
from app.core.csv_export import csv_response
from app.core.permission_codes import CREDIT_COLLECTION_READ, CREDIT_COLLECTION_RECORD
from app.exceptions import ConflictError
from app.core.revenue import round_money
from app.models.credit_customer import CreditCustomer
from app.models.credit_customer_payment import CreditCustomerPayment
from app.models.shift_tender import ShiftTender
from app.models.user import User
from app.schemas.credit_collection import (
    CreditCustomerAgeingEntry,
    CreditCustomerBalanceRead,
    CreditCustomerPaymentCreate,
    CreditCustomerPaymentRead,
    CreditCustomerPaymentReverse,
    CreditCustomerStatement,
    CreditCustomerStatementEntry,
)

router = APIRouter(
    prefix="/organizations/{organization_id}/credit-customers/{credit_customer_id}", tags=["credit-collections"]
)
balances_router = APIRouter(prefix="/organizations/{organization_id}/credit-customers", tags=["credit-collections"])


@router.post("/payments", response_model=CreditCustomerPaymentRead, status_code=201)
async def record_credit_customer_payment(
    organization_id: uuid.UUID,
    credit_customer_id: uuid.UUID,
    payload: CreditCustomerPaymentCreate,
    request: Request,
    current_user: User = Depends(require_permission(CREDIT_COLLECTION_RECORD)),
    db: AsyncSession = Depends(get_db),
) -> CreditCustomerPayment:
    await get_credit_customer_or_404(db, organization_id, credit_customer_id)

    payment = CreditCustomerPayment(
        organization_id=organization_id,
        credit_customer_id=credit_customer_id,
        recorded_by_user_id=current_user.id,
        **payload.model_dump(),
    )
    db.add(payment)
    await db.flush()

    await write_audit_log(
        db,
        action="credit_customer_payment.create",
        entity_type="CreditCustomer",
        entity_id=str(credit_customer_id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        after={"payment_id": str(payment.id), "amount": str(payment.amount)},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return payment


@router.get("/payments", response_model=list[CreditCustomerPaymentRead])
async def list_credit_customer_payments(
    organization_id: uuid.UUID,
    credit_customer_id: uuid.UUID,
    current_user: User = Depends(require_permission(CREDIT_COLLECTION_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[CreditCustomerPayment]:
    await get_credit_customer_or_404(db, organization_id, credit_customer_id)
    result = await db.execute(
        select(CreditCustomerPayment)
        .where(CreditCustomerPayment.credit_customer_id == credit_customer_id)
        .order_by(CreditCustomerPayment.payment_date.desc())
    )
    return list(result.scalars().all())


@router.patch("/payments/{payment_id}/reverse", response_model=CreditCustomerPaymentRead)
async def reverse_credit_customer_payment(
    organization_id: uuid.UUID,
    credit_customer_id: uuid.UUID,
    payment_id: uuid.UUID,
    payload: CreditCustomerPaymentReverse,
    request: Request,
    current_user: User = Depends(require_permission(CREDIT_COLLECTION_RECORD)),
    db: AsyncSession = Depends(get_db),
) -> CreditCustomerPayment:
    payment = await get_credit_customer_payment_or_404(db, organization_id, payment_id, for_update=True)
    if payment.credit_customer_id != credit_customer_id:
        raise ConflictError("Payment does not belong to this credit customer.")
    if payment.reversed_at is not None:
        raise ConflictError("This payment has already been reversed.")

    payment.reversed_by_user_id = current_user.id
    payment.reversed_at = datetime.now(timezone.utc)
    payment.reversal_reason = payload.reason
    await db.flush()

    await write_audit_log(
        db,
        action="credit_customer_payment.reverse",
        entity_type="CreditCustomer",
        entity_id=str(credit_customer_id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        after={"payment_id": str(payment.id), "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return payment


@router.get("/balance", response_model=CreditCustomerBalanceRead)
async def get_credit_customer_balance_endpoint(
    organization_id: uuid.UUID,
    credit_customer_id: uuid.UUID,
    current_user: User = Depends(require_permission(CREDIT_COLLECTION_READ)),
    db: AsyncSession = Depends(get_db),
) -> CreditCustomerBalanceRead:
    customer = await get_credit_customer_or_404(db, organization_id, credit_customer_id)
    balance = await get_credit_customer_balance(db, credit_customer_id)
    return CreditCustomerBalanceRead(
        credit_customer_id=customer.id, credit_customer_name=customer.name,
        balance=balance, credit_limit=customer.credit_limit,
    )


@balances_router.get("/balances", response_model=list[CreditCustomerBalanceRead])
async def list_credit_customer_balances(
    organization_id: uuid.UUID,
    current_user: User = Depends(require_permission(CREDIT_COLLECTION_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[CreditCustomerBalanceRead]:
    await get_organization_or_404(db, organization_id)
    customers = (
        await db.execute(select(CreditCustomer).where(CreditCustomer.organization_id == organization_id))
    ).scalars().all()
    return [
        CreditCustomerBalanceRead(
            credit_customer_id=c.id, credit_customer_name=c.name,
            balance=await get_credit_customer_balance(db, c.id),
            credit_limit=c.credit_limit,
        )
        for c in customers
    ]


@balances_router.get("/balances/export")
async def export_credit_customer_balances(
    organization_id: uuid.UUID,
    current_user: User = Depends(require_permission(CREDIT_COLLECTION_READ)),
    db: AsyncSession = Depends(get_db),
):
    balances = await list_credit_customer_balances(organization_id, current_user=current_user, db=db)
    rows = [{"credit_customer_name": b.credit_customer_name, "balance": str(b.balance)} for b in balances]
    return csv_response("credit-customer-balances.csv", ["credit_customer_name", "balance"], rows)


@router.get("/statement", response_model=CreditCustomerStatement)
async def get_credit_customer_statement(
    organization_id: uuid.UUID,
    credit_customer_id: uuid.UUID,
    start_date: date = Query(...),
    end_date: date = Query(...),
    current_user: User = Depends(require_permission(CREDIT_COLLECTION_READ)),
    db: AsyncSession = Depends(get_db),
) -> CreditCustomerStatement:
    customer = await get_credit_customer_or_404(db, organization_id, credit_customer_id)

    sales = (
        await db.execute(
            select(ShiftTender)
            .where(
                ShiftTender.credit_customer_id == credit_customer_id,
                ShiftTender.reversed_at.is_(None),
            )
            .order_by(ShiftTender.recorded_at)
        )
    ).scalars().all()

    payments = (
        await db.execute(
            select(CreditCustomerPayment)
            .where(
                CreditCustomerPayment.credit_customer_id == credit_customer_id,
                CreditCustomerPayment.reversed_at.is_(None),
            )
            .order_by(CreditCustomerPayment.payment_date)
        )
    ).scalars().all()

    events: list[tuple[date, str, Decimal, Decimal]] = []
    for s in sales:
        sale_date = s.recorded_at.date()
        if start_date <= sale_date <= end_date:
            events.append((sale_date, f"Credit sale (ref: {s.reference or 'N/A'})", s.amount, Decimal(0)))
    for p in payments:
        if start_date <= p.payment_date <= end_date:
            events.append((p.payment_date, f"Payment received (ref: {p.reference or 'N/A'})", Decimal(0), p.amount))

    events.sort(key=lambda e: e[0])

    opening_balance = Decimal(0)
    for s in sales:
        if s.recorded_at.date() < start_date:
            opening_balance += s.amount
    for p in payments:
        if p.payment_date < start_date:
            opening_balance -= p.amount
    opening_balance = round_money(opening_balance)

    entries = []
    running = opening_balance
    for d, desc, debit, credit in events:
        running = round_money(running + debit - credit)
        entries.append(CreditCustomerStatementEntry(
            date=d, description=desc, debit=debit, credit=credit, running_balance=running,
        ))

    return CreditCustomerStatement(
        credit_customer_id=customer.id,
        credit_customer_name=customer.name,
        opening_balance=opening_balance,
        entries=entries,
        closing_balance=running,
    )


@balances_router.get("/ageing", response_model=list[CreditCustomerAgeingEntry])
async def list_credit_customer_ageing(
    organization_id: uuid.UUID,
    current_user: User = Depends(require_permission(CREDIT_COLLECTION_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[CreditCustomerAgeingEntry]:
    await get_organization_or_404(db, organization_id)
    customers = (
        await db.execute(
            select(CreditCustomer).where(
                CreditCustomer.organization_id == organization_id,
                CreditCustomer.is_active.is_(True),
            )
        )
    ).scalars().all()

    today = datetime.now(timezone.utc).date()
    result = []

    for customer in customers:
        tenders = (
            await db.execute(
                select(ShiftTender)
                .where(
                    ShiftTender.credit_customer_id == customer.id,
                    ShiftTender.reversed_at.is_(None),
                )
            )
        ).scalars().all()

        collections_total = (
            await db.execute(
                select(CreditCustomerPayment)
                .where(
                    CreditCustomerPayment.credit_customer_id == customer.id,
                    CreditCustomerPayment.reversed_at.is_(None),
                )
            )
        ).scalars().all()
        paid = sum(p.amount for p in collections_total)

        buckets = {
            "current": Decimal(0),
            "days_30": Decimal(0),
            "days_60": Decimal(0),
            "days_90": Decimal(0),
            "over_90": Decimal(0),
        }

        remaining_paid = paid
        sorted_tenders = sorted(tenders, key=lambda t: t.recorded_at)

        for tender in sorted_tenders:
            if remaining_paid >= tender.amount:
                remaining_paid -= tender.amount
                continue
            unpaid = tender.amount - remaining_paid
            remaining_paid = Decimal(0)

            age = (today - tender.recorded_at.date()).days
            if age <= 30:
                buckets["current"] += unpaid
            elif age <= 60:
                buckets["days_30"] += unpaid
            elif age <= 90:
                buckets["days_60"] += unpaid
            elif age <= 120:
                buckets["days_90"] += unpaid
            else:
                buckets["over_90"] += unpaid

        total = sum(buckets.values())
        if total > 0:
            result.append(CreditCustomerAgeingEntry(
                credit_customer_id=customer.id,
                credit_customer_name=customer.name,
                current=round_money(buckets["current"]),
                days_30=round_money(buckets["days_30"]),
                days_60=round_money(buckets["days_60"]),
                days_90=round_money(buckets["days_90"]),
                over_90=round_money(buckets["over_90"]),
                total=round_money(total),
            ))

    return result
