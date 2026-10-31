import uuid
from datetime import date, datetime, time, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_organization_or_404, get_station_or_404
from app.api.deps import get_db, require_permission
from app.core.csv_export import csv_response
from app.core.fuel_grade_lookup import get_fuel_grades_by_id
from app.core.inventory import get_inventory_stock
from app.core.permission_codes import REPORT_READ
from app.core.permissions import get_station_visibility_scope
from app.core.reconciliation import get_total_tender_amount
from app.core.revenue import compute_expected_fuel_revenue_by_grade
from app.core.variance import compute_shift_tank_variance
from app.exceptions import ValidationFailedError
from app.models.expense import Expense, ExpenseStatus
from app.models.inventory_item import InventoryItem
from app.models.shift import Shift, ShiftStatus
from app.models.shift_cash_movement import DECREASING_CASH_MOVEMENT_TYPES, ShiftCashMovement
from app.models.shift_nozzle_reading import ShiftNozzleReading
from app.models.shift_reconciliation import ShiftReconciliation
from app.models.stock_ledger_entry import StockLedgerEntry, StockMovementType
from app.models.supplier_payment import SupplierPayment
from app.models.tank import Tank
from app.models.tanker_receipt import ReceiptStatus, TankerReceipt
from app.models.user import User
from app.schemas.reports import (
    DailyFuelSalesDay,
    DailyFuelSalesGradeRow,
    PendingApprovalsReport,
    ShiftReconciliationReportRow,
    TankVarianceReportRow,
)

MAX_REPORT_DAYS = 366

router = APIRouter(prefix="/organizations/{organization_id}/stations/{station_id}/reports", tags=["reports"])
org_router = APIRouter(prefix="/organizations/{organization_id}", tags=["reports"])


def _validate_date_range(date_from: date, date_to: date) -> None:
    if date_to < date_from:
        raise ValidationFailedError("date_to must not be before date_from.")
    if (date_to - date_from).days > MAX_REPORT_DAYS:
        raise ValidationFailedError(f"Date range must not exceed {MAX_REPORT_DAYS} days.")


async def _approved_shifts_in_range(
    db: AsyncSession, station_id: uuid.UUID, date_from: date, date_to: date
) -> list[Shift]:
    start = datetime.combine(date_from, time.min, tzinfo=timezone.utc)
    end = datetime.combine(date_to, time.max, tzinfo=timezone.utc)
    result = await db.execute(
        select(Shift).where(
            Shift.station_id == station_id,
            Shift.status == ShiftStatus.APPROVED.value,
            Shift.opened_at >= start,
            Shift.opened_at <= end,
        )
    )
    return list(result.scalars().all())


async def _build_daily_fuel_sales(
    db: AsyncSession, station_id: uuid.UUID, date_from: date, date_to: date
) -> list[DailyFuelSalesDay]:
    shifts = await _approved_shifts_in_range(db, station_id, date_from, date_to)
    if not shifts:
        return []
    shift_by_id = {s.id: s for s in shifts}

    by_day: dict[date, dict] = {}

    for shift in shifts:
        day = shift.opened_at.date()
        bucket = by_day.setdefault(
            day, {"shift_count": 0, "grades": {}, "total_tender_amount": Decimal(0)}
        )
        bucket["shift_count"] += 1
        bucket["total_tender_amount"] += await get_total_tender_amount(db, shift.id)
        per_grade_revenue = await compute_expected_fuel_revenue_by_grade(db, shift)
        for grade_id, revenue in per_grade_revenue.items():
            g = bucket["grades"].setdefault(grade_id, {"litres": Decimal(0), "revenue": Decimal(0)})
            g["revenue"] += revenue

    # Litres sold come from the stock ledger's own SALE postings (joined
    # through Tank for fuel_grade_id) rather than raw dispensed_litres, so
    # this figure already excludes exceptional test/calibration litres -
    # see docs/ASSUMPTIONS.md #25 for why expected_revenue above still does
    # not.
    ledger_rows = (
        await db.execute(
            select(StockLedgerEntry.reference_id, StockLedgerEntry.quantity, Tank.fuel_grade_id)
            .join(Tank, Tank.id == StockLedgerEntry.tank_id)
            .where(
                StockLedgerEntry.reference_type == "Shift",
                StockLedgerEntry.reference_id.in_(list(shift_by_id.keys())),
                StockLedgerEntry.movement_type == StockMovementType.SALE.value,
            )
        )
    ).all()
    for shift_id, quantity, grade_id in ledger_rows:
        shift = shift_by_id.get(shift_id)
        if shift is None:
            continue
        day = shift.opened_at.date()
        bucket = by_day.setdefault(
            day, {"shift_count": 0, "grades": {}, "total_tender_amount": Decimal(0)}
        )
        g = bucket["grades"].setdefault(grade_id, {"litres": Decimal(0), "revenue": Decimal(0)})
        g["litres"] += quantity

    all_grade_ids = {gid for bucket in by_day.values() for gid in bucket["grades"]}
    grades_by_id = await get_fuel_grades_by_id(db, all_grade_ids)

    days: list[DailyFuelSalesDay] = []
    for day in sorted(by_day.keys()):
        bucket = by_day[day]
        grade_rows = []
        total_litres = Decimal(0)
        total_revenue = Decimal(0)
        for grade_id, figures in bucket["grades"].items():
            grade = grades_by_id.get(grade_id)
            grade_rows.append(
                DailyFuelSalesGradeRow(
                    fuel_grade_id=grade_id,
                    fuel_grade_code=grade.code if grade else "?",
                    fuel_grade_name=grade.name if grade else "Unknown",
                    litres_sold=figures["litres"],
                    expected_revenue=figures["revenue"],
                )
            )
            total_litres += figures["litres"]
            total_revenue += figures["revenue"]
        days.append(
            DailyFuelSalesDay(
                sale_date=day,
                shift_count=bucket["shift_count"],
                grades=grade_rows,
                total_litres_sold=total_litres,
                total_expected_revenue=total_revenue,
                total_tender_amount=bucket["total_tender_amount"],
            )
        )
    return days


@router.get("/daily-fuel-sales", response_model=list[DailyFuelSalesDay])
async def daily_fuel_sales_report(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    date_from: date = Query(...),
    date_to: date = Query(...),
    current_user: User = Depends(require_permission(REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[DailyFuelSalesDay]:
    await get_station_or_404(db, organization_id, station_id)
    _validate_date_range(date_from, date_to)
    return await _build_daily_fuel_sales(db, station_id, date_from, date_to)


@router.get("/daily-fuel-sales/export")
async def export_daily_fuel_sales_report(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    date_from: date = Query(...),
    date_to: date = Query(...),
    current_user: User = Depends(require_permission(REPORT_READ)),
    db: AsyncSession = Depends(get_db),
):
    await get_station_or_404(db, organization_id, station_id)
    _validate_date_range(date_from, date_to)
    days = await _build_daily_fuel_sales(db, station_id, date_from, date_to)
    rows = [
        {
            "date": d.sale_date.isoformat(),
            "fuel_grade": g.fuel_grade_code,
            "litres_sold": str(g.litres_sold),
            "expected_revenue": str(g.expected_revenue),
            "shift_count": d.shift_count,
            "total_tender_amount": str(d.total_tender_amount),
        }
        for d in days
        for g in d.grades
    ]
    return csv_response(
        "daily-fuel-sales.csv",
        ["date", "fuel_grade", "litres_sold", "expected_revenue", "shift_count", "total_tender_amount"],
        rows,
    )


@router.get("/tank-variance", response_model=list[TankVarianceReportRow])
async def tank_variance_report(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    date_from: date = Query(...),
    date_to: date = Query(...),
    current_user: User = Depends(require_permission(REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[TankVarianceReportRow]:
    station = await get_station_or_404(db, organization_id, station_id)
    _validate_date_range(date_from, date_to)
    shifts = await _approved_shifts_in_range(db, station_id, date_from, date_to)

    rows: list[TankVarianceReportRow] = []
    for shift in shifts:
        tank_rows = await compute_shift_tank_variance(db, shift, station)
        for t in tank_rows:
            rows.append(
                TankVarianceReportRow(
                    shift_id=shift.id,
                    shift_date=shift.opened_at.date(),
                    tank_id=t.tank_id,
                    tank_code=t.tank_code,
                    opening_book_stock=t.opening_book_stock,
                    closing_book_stock=t.closing_book_stock,
                    physical_closing_reading=t.physical_closing_reading,
                    closing_variance=t.closing_variance,
                    closing_variance_percent=t.closing_variance_percent,
                    within_tolerance=t.within_tolerance,
                )
            )
    return rows


@router.get("/tank-variance/export")
async def export_tank_variance_report(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    date_from: date = Query(...),
    date_to: date = Query(...),
    current_user: User = Depends(require_permission(REPORT_READ)),
    db: AsyncSession = Depends(get_db),
):
    rows = await tank_variance_report(
        organization_id, station_id, date_from, date_to, current_user=current_user, db=db
    )
    csv_rows = [
        {
            "shift_date": r.shift_date.isoformat(),
            "tank_code": r.tank_code,
            "opening_book_stock": str(r.opening_book_stock),
            "closing_book_stock": str(r.closing_book_stock),
            "physical_closing_reading": str(r.physical_closing_reading) if r.physical_closing_reading is not None else "",
            "closing_variance": str(r.closing_variance) if r.closing_variance is not None else "",
            "closing_variance_percent": str(r.closing_variance_percent) if r.closing_variance_percent is not None else "",
            "within_tolerance": r.within_tolerance,
        }
        for r in rows
    ]
    return csv_response(
        "tank-variance.csv",
        [
            "shift_date",
            "tank_code",
            "opening_book_stock",
            "closing_book_stock",
            "physical_closing_reading",
            "closing_variance",
            "closing_variance_percent",
            "within_tolerance",
        ],
        csv_rows,
    )


async def _build_shift_reconciliation_report(
    db: AsyncSession, station_id: uuid.UUID, date_from: date, date_to: date
) -> list[ShiftReconciliationReportRow]:
    start = datetime.combine(date_from, time.min, tzinfo=timezone.utc)
    end = datetime.combine(date_to, time.max, tzinfo=timezone.utc)
    result = await db.execute(
        select(Shift, ShiftReconciliation)
        .join(ShiftReconciliation, ShiftReconciliation.shift_id == Shift.id)
        .where(Shift.station_id == station_id, Shift.opened_at >= start, Shift.opened_at <= end)
        .order_by(Shift.opened_at.desc())
    )
    rows = []
    for shift, recon in result.all():
        rows.append(
            ShiftReconciliationReportRow(
                shift_id=shift.id,
                shift_label=shift.label,
                opened_at=shift.opened_at,
                status=shift.status,
                expected_fuel_revenue=recon.expected_fuel_revenue,
                total_tender_amount=recon.total_tender_amount,
                revenue_variance=recon.revenue_variance,
                expected_physical_cash=recon.expected_physical_cash,
                actual_physical_cash=recon.actual_physical_cash,
                cash_shortage_excess=recon.cash_shortage_excess,
                requires_authorization=recon.requires_authorization,
                authorized_at=recon.authorized_at,
            )
        )
    return rows


@router.get("/shift-reconciliation", response_model=list[ShiftReconciliationReportRow])
async def shift_reconciliation_report(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    date_from: date = Query(...),
    date_to: date = Query(...),
    current_user: User = Depends(require_permission(REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[ShiftReconciliationReportRow]:
    await get_station_or_404(db, organization_id, station_id)
    _validate_date_range(date_from, date_to)
    return await _build_shift_reconciliation_report(db, station_id, date_from, date_to)


@router.get("/shift-reconciliation/export")
async def export_shift_reconciliation_report(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    date_from: date = Query(...),
    date_to: date = Query(...),
    current_user: User = Depends(require_permission(REPORT_READ)),
    db: AsyncSession = Depends(get_db),
):
    await get_station_or_404(db, organization_id, station_id)
    _validate_date_range(date_from, date_to)
    rows = await _build_shift_reconciliation_report(db, station_id, date_from, date_to)
    csv_rows = [
        {
            "opened_at": r.opened_at.isoformat(),
            "shift_label": r.shift_label or "",
            "status": r.status,
            "expected_fuel_revenue": str(r.expected_fuel_revenue),
            "total_tender_amount": str(r.total_tender_amount),
            "revenue_variance": str(r.revenue_variance),
            "expected_physical_cash": str(r.expected_physical_cash),
            "actual_physical_cash": str(r.actual_physical_cash),
            "cash_shortage_excess": str(r.cash_shortage_excess),
            "requires_authorization": r.requires_authorization,
            "authorized_at": r.authorized_at.isoformat() if r.authorized_at else "",
        }
        for r in rows
    ]
    return csv_response(
        "shift-reconciliation.csv",
        [
            "opened_at",
            "shift_label",
            "status",
            "expected_fuel_revenue",
            "total_tender_amount",
            "revenue_variance",
            "expected_physical_cash",
            "actual_physical_cash",
            "cash_shortage_excess",
            "requires_authorization",
            "authorized_at",
        ],
        csv_rows,
    )


@org_router.get("/reports/pending-approvals", response_model=PendingApprovalsReport)
async def pending_approvals_report(
    organization_id: uuid.UUID,
    current_user: User = Depends(require_permission(REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> PendingApprovalsReport:
    """
    Cross-cutting counts of everything awaiting a decision or outside
    tolerance, across every station the caller can see (scoped the same
    way the audit log is - an org-wide grant sees every station, a
    station-scoped grant sees only its own stations).
    """
    await get_organization_or_404(db, organization_id)

    visible_station_ids: set[uuid.UUID] | None = None
    if not current_user.is_superuser:
        visible_station_ids = await get_station_visibility_scope(
            db, user_id=current_user.id, organization_id=organization_id, permission_code=REPORT_READ
        )

    def _station_filter(column):
        if visible_station_ids is None:
            return None
        return column.in_(visible_station_ids)

    receipt_stmt = select(TankerReceipt).where(
        TankerReceipt.organization_id == organization_id,
        TankerReceipt.status == ReceiptStatus.AWAITING_APPROVAL.value,
    )
    if (f := _station_filter(TankerReceipt.station_id)) is not None:
        receipt_stmt = receipt_stmt.where(f)
    receipts_awaiting = len((await db.execute(receipt_stmt)).scalars().all())

    shift_stmt = select(Shift).where(
        Shift.organization_id == organization_id, Shift.status == ShiftStatus.CLOSED.value
    )
    if (f := _station_filter(Shift.station_id)) is not None:
        shift_stmt = shift_stmt.where(f)
    shifts_closed = (await db.execute(shift_stmt)).scalars().all()
    shifts_awaiting = len(shifts_closed)

    meter_stmt = select(ShiftNozzleReading).where(
        ShiftNozzleReading.meter_event_type.is_not(None),
        ShiftNozzleReading.meter_event_approved_by_user_id.is_(None),
    )
    unapproved_meter_events = len((await db.execute(meter_stmt)).scalars().all())

    recon_stmt = (
        select(ShiftReconciliation)
        .join(Shift, Shift.id == ShiftReconciliation.shift_id)
        .where(
            Shift.organization_id == organization_id,
            ShiftReconciliation.requires_authorization.is_(True),
            ShiftReconciliation.authorized_by_user_id.is_(None),
        )
    )
    if (f := _station_filter(Shift.station_id)) is not None:
        recon_stmt = recon_stmt.where(f)
    recons_requiring_auth = len((await db.execute(recon_stmt)).scalars().all())

    movement_stmt = (
        select(ShiftCashMovement)
        .join(Shift, Shift.id == ShiftCashMovement.shift_id)
        .where(Shift.organization_id == organization_id)
    )
    if (f := _station_filter(Shift.station_id)) is not None:
        movement_stmt = movement_stmt.where(f)
    all_movements = (await db.execute(movement_stmt)).scalars().all()
    unapproved_decreasing = len(
        [
            m
            for m in all_movements
            if m.movement_type in {t.value for t in DECREASING_CASH_MOVEMENT_TYPES}
            and m.approved_by_user_id is None
            and m.reversed_at is None
        ]
    )

    expense_stmt = select(Expense).where(
        Expense.organization_id == organization_id, Expense.status == ExpenseStatus.PENDING.value
    )
    if (f := _station_filter(Expense.station_id)) is not None:
        expense_stmt = expense_stmt.where(f | Expense.station_id.is_(None))
    pending_expenses = len((await db.execute(expense_stmt)).scalars().all())

    payment_stmt = select(SupplierPayment).where(
        SupplierPayment.organization_id == organization_id,
        SupplierPayment.approved_by_user_id.is_(None),
        SupplierPayment.reversed_at.is_(None),
    )
    unapproved_payments = len((await db.execute(payment_stmt)).scalars().all())

    item_stmt = select(InventoryItem).where(InventoryItem.organization_id == organization_id, InventoryItem.is_active.is_(True))
    if (f := _station_filter(InventoryItem.station_id)) is not None:
        item_stmt = item_stmt.where(f)
    items = (await db.execute(item_stmt)).scalars().all()
    low_stock = 0
    for item in items:
        on_hand = await get_inventory_stock(db, item.id)
        if on_hand < item.reorder_level:
            low_stock += 1

    return PendingApprovalsReport(
        tanker_receipts_awaiting_approval=receipts_awaiting,
        shifts_awaiting_approval=shifts_awaiting,
        unapproved_meter_events=unapproved_meter_events,
        reconciliations_requiring_authorization=recons_requiring_auth,
        unapproved_decreasing_cash_movements=unapproved_decreasing,
        pending_expenses=pending_expenses,
        unapproved_supplier_payments=unapproved_payments,
        low_stock_inventory_items=low_stock,
    )
