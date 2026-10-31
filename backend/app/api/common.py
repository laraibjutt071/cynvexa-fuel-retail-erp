import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import NotFoundError, ValidationFailedError
from app.models.credit_customer import CreditCustomer
from app.models.credit_customer_payment import CreditCustomerPayment
from app.models.dispenser import Dispenser
from app.models.expense import Expense
from app.models.fuel_grade import FuelGrade
from app.models.inventory_item import InventoryItem
from app.models.nozzle import Nozzle
from app.models.organization import Organization
from app.models.payment_method import PaymentMethod
from app.models.shift import Shift
from app.models.station import Station
from app.models.supplier import Supplier
from app.models.supplier_invoice import SupplierInvoice
from app.models.supplier_payment import SupplierPayment
from app.models.tank import Tank


async def get_organization_or_404(db: AsyncSession, organization_id: uuid.UUID) -> Organization:
    """
    Shared existence check for every org-scoped mutating endpoint. Without
    this, inserting a row with a non-existent organization_id relies on the
    database's foreign-key constraint to fail - which then gets caught by a
    generic `except IntegrityError` alongside the real unique-constraint
    violations those blocks are meant to catch, producing a misleading error
    (e.g. "code already exists" for an organization that doesn't exist at
    all). Call this first so a bad org id is reported as 404, and any
    IntegrityError caught afterwards can only be the intended unique
    constraint.
    """
    org = (
        await db.execute(select(Organization).where(Organization.id == organization_id))
    ).scalar_one_or_none()
    if org is None:
        raise NotFoundError("Organization not found.")
    return org


async def get_station_or_404(
    db: AsyncSession, organization_id: uuid.UUID, station_id: uuid.UUID
) -> Station:
    station = (
        await db.execute(
            select(Station).where(Station.id == station_id, Station.organization_id == organization_id)
        )
    ).scalar_one_or_none()
    if station is None:
        raise NotFoundError("Station not found.")
    return station


async def get_fuel_grade_or_404(
    db: AsyncSession, organization_id: uuid.UUID, fuel_grade_id: uuid.UUID
) -> FuelGrade:
    grade = (
        await db.execute(
            select(FuelGrade).where(
                FuelGrade.id == fuel_grade_id, FuelGrade.organization_id == organization_id
            )
        )
    ).scalar_one_or_none()
    if grade is None:
        raise ValidationFailedError("Fuel grade does not belong to this organization.")
    return grade


async def get_supplier_or_404(
    db: AsyncSession, organization_id: uuid.UUID, supplier_id: uuid.UUID
) -> Supplier:
    supplier = (
        await db.execute(
            select(Supplier).where(
                Supplier.id == supplier_id, Supplier.organization_id == organization_id
            )
        )
    ).scalar_one_or_none()
    if supplier is None:
        raise ValidationFailedError("Supplier does not belong to this organization.")
    return supplier


async def get_tank_or_404(
    db: AsyncSession, station_id: uuid.UUID, tank_id: uuid.UUID, *, for_update: bool = False
) -> Tank:
    """
    for_update=True takes a row lock (SELECT ... FOR UPDATE) on the tank -
    required whenever a capacity decision (does accepting X litres fit)
    will be acted on afterward in the same transaction, so two concurrent
    receipts for the same tank can't both pass the check against the same
    stale book-stock figure. See app/api/tanker_receipts.py's approve step.
    """
    stmt = select(Tank).where(Tank.id == tank_id, Tank.station_id == station_id)
    if for_update:
        stmt = stmt.with_for_update()
    tank = (await db.execute(stmt)).scalar_one_or_none()
    if tank is None:
        raise ValidationFailedError("Tank does not belong to this station.")
    return tank


async def get_nozzle_in_station_or_404(
    db: AsyncSession, station_id: uuid.UUID, nozzle_id: uuid.UUID
) -> Nozzle:
    """Nozzle has no direct station_id column - it belongs to a station
    through its dispenser, so the check joins through that."""
    nozzle = (
        await db.execute(
            select(Nozzle)
            .join(Dispenser, Dispenser.id == Nozzle.dispenser_id)
            .where(Nozzle.id == nozzle_id, Dispenser.station_id == station_id)
        )
    ).scalar_one_or_none()
    if nozzle is None:
        raise ValidationFailedError("Nozzle does not belong to this station.")
    return nozzle


async def get_shift_or_404(
    db: AsyncSession, station_id: uuid.UUID, shift_id: uuid.UUID, *, for_update: bool = False
) -> Shift:
    """
    for_update=True locks the shift row - required by every state
    transition (record readings, close, approve) so two concurrent
    requests against the same shift serialize instead of racing past the
    same status check. See app/api/shifts.py.
    """
    stmt = select(Shift).where(Shift.id == shift_id, Shift.station_id == station_id)
    if for_update:
        stmt = stmt.with_for_update()
    shift = (await db.execute(stmt)).scalar_one_or_none()
    if shift is None:
        raise NotFoundError("Shift not found.")
    return shift


async def get_payment_method_or_404(
    db: AsyncSession, organization_id: uuid.UUID, payment_method_id: uuid.UUID
) -> PaymentMethod:
    method = (
        await db.execute(
            select(PaymentMethod).where(
                PaymentMethod.id == payment_method_id, PaymentMethod.organization_id == organization_id
            )
        )
    ).scalar_one_or_none()
    if method is None:
        raise ValidationFailedError("Payment method does not belong to this organization.")
    return method


async def get_credit_customer_or_404(
    db: AsyncSession, organization_id: uuid.UUID, credit_customer_id: uuid.UUID
) -> CreditCustomer:
    customer = (
        await db.execute(
            select(CreditCustomer).where(
                CreditCustomer.id == credit_customer_id, CreditCustomer.organization_id == organization_id
            )
        )
    ).scalar_one_or_none()
    if customer is None:
        raise ValidationFailedError("Credit customer does not belong to this organization.")
    return customer


async def get_supplier_invoice_or_404(
    db: AsyncSession, organization_id: uuid.UUID, invoice_id: uuid.UUID
) -> SupplierInvoice:
    invoice = (
        await db.execute(
            select(SupplierInvoice).where(
                SupplierInvoice.id == invoice_id, SupplierInvoice.organization_id == organization_id
            )
        )
    ).scalar_one_or_none()
    if invoice is None:
        raise NotFoundError("Supplier invoice not found.")
    return invoice


async def get_supplier_payment_or_404(
    db: AsyncSession, organization_id: uuid.UUID, payment_id: uuid.UUID, *, for_update: bool = False
) -> SupplierPayment:
    stmt = select(SupplierPayment).where(
        SupplierPayment.id == payment_id, SupplierPayment.organization_id == organization_id
    )
    if for_update:
        stmt = stmt.with_for_update()
    payment = (await db.execute(stmt)).scalar_one_or_none()
    if payment is None:
        raise NotFoundError("Supplier payment not found.")
    return payment


async def get_credit_customer_payment_or_404(
    db: AsyncSession, organization_id: uuid.UUID, payment_id: uuid.UUID, *, for_update: bool = False
) -> CreditCustomerPayment:
    stmt = select(CreditCustomerPayment).where(
        CreditCustomerPayment.id == payment_id, CreditCustomerPayment.organization_id == organization_id
    )
    if for_update:
        stmt = stmt.with_for_update()
    payment = (await db.execute(stmt)).scalar_one_or_none()
    if payment is None:
        raise NotFoundError("Credit customer payment not found.")
    return payment


async def get_expense_or_404(
    db: AsyncSession, organization_id: uuid.UUID, expense_id: uuid.UUID, *, for_update: bool = False
) -> Expense:
    stmt = select(Expense).where(Expense.id == expense_id, Expense.organization_id == organization_id)
    if for_update:
        stmt = stmt.with_for_update()
    expense = (await db.execute(stmt)).scalar_one_or_none()
    if expense is None:
        raise NotFoundError("Expense not found.")
    return expense


async def get_inventory_item_or_404(
    db: AsyncSession, station_id: uuid.UUID, inventory_item_id: uuid.UUID, *, for_update: bool = False
) -> InventoryItem:
    stmt = select(InventoryItem).where(
        InventoryItem.id == inventory_item_id, InventoryItem.station_id == station_id
    )
    if for_update:
        stmt = stmt.with_for_update()
    item = (await db.execute(stmt)).scalar_one_or_none()
    if item is None:
        raise ValidationFailedError("Inventory item does not belong to this station.")
    return item
