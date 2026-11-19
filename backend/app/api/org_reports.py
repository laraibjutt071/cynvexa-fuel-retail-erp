"""
Phase 8b: organization-wide (multi-station) business reports for a client
that operates more than one petrol station under a single organization.
Every figure here is produced by reusing the exact calculation functions
the existing single-station reports already use (app/core/revenue.py,
app/core/reconciliation.py, app/core/stock.py, app/api/reports.py's own
expense categorizer) - summed or grouped across an authorized set of
stations, never recomputed from scratch. Station authorization is always
resolved server-side (app/core/report_scope.py); a `station_id` query
filter only ever narrows an already-authorized set, never widens it.
"""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_organization_or_404
from app.api.deps import get_db, require_permission
from app.api.reports import _validate_date_range, categorize_expenses
from app.core.org_aggregation import (
    approved_shifts_in_range,
    current_tank_stock,
    fuel_grade_names,
    sales_by_grade_and_station,
    station_names,
    tender_totals_by_category_and_station,
)
from app.core.permission_codes import ATTENDANCE_READ, REPORT_READ
from app.core.report_scope import resolve_authorized_station_ids
from app.models.attendance import AttendanceRecord, AttendanceStatus
from app.models.expense import Expense
from app.models.user import User
from app.models.user_station_role import UserStationRole
from app.schemas.org_reports import (
    OrgAttendanceDay,
    OrgAttendanceReport,
    OrgAttendanceStationRow,
    OrgExpenseReport,
    OrgExpenseStationRow,
    OrgRevenueReport,
    OrgRevenueStationRow,
    OrgSalesGradeRow,
    OrgSalesReport,
    OrgSalesStationRow,
    OrgStationPerformanceReport,
    OrgStockGradeRow,
    OrgStockReport,
    OrgStockTankRow,
    StationPerformanceRow,
)

router = APIRouter(prefix="/organizations/{organization_id}/reports", tags=["org-reports"])


async def _authorized_stations(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    current_user: User,
    permission_code: str,
    station_id: list[uuid.UUID] | None,
) -> list[uuid.UUID]:
    await get_organization_or_404(db, organization_id)
    return await resolve_authorized_station_ids(
        db,
        current_user=current_user,
        organization_id=organization_id,
        permission_code=permission_code,
        requested_station_ids=station_id,
    )


@router.get("/sales", response_model=OrgSalesReport)
async def org_sales_report(
    organization_id: uuid.UUID,
    date_from: date = Query(...),
    date_to: date = Query(...),
    station_id: list[uuid.UUID] | None = Query(default=None),
    current_user: User = Depends(require_permission(REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> OrgSalesReport:
    _validate_date_range(date_from, date_to)
    station_ids = await _authorized_stations(
        db, organization_id=organization_id, current_user=current_user, permission_code=REPORT_READ, station_id=station_id
    )
    shifts = await approved_shifts_in_range(db, station_ids, date_from, date_to)
    by_grade, by_station = await sales_by_grade_and_station(db, shifts)

    grades = await fuel_grade_names(db, set(by_grade.keys()))
    stations = await station_names(db, list(by_station.keys()))

    grade_rows = [
        OrgSalesGradeRow(
            fuel_grade_id=gid,
            fuel_grade_code=grades[gid].code if gid in grades else "?",
            fuel_grade_name=grades[gid].name if gid in grades else "Unknown",
            litres_sold=v["litres"],
            expected_revenue=v["revenue"],
        )
        for gid, v in by_grade.items()
    ]
    station_rows = [
        OrgSalesStationRow(
            station_id=sid,
            station_name=stations[sid].name if sid in stations else "Unknown",
            litres_sold=v["litres"],
            expected_revenue=v["revenue"],
        )
        for sid, v in by_station.items()
    ]
    return OrgSalesReport(
        date_from=date_from,
        date_to=date_to,
        shift_count=len(shifts),
        total_litres_sold=sum((r.litres_sold for r in grade_rows), Decimal(0)),
        total_expected_revenue=sum((r.expected_revenue for r in grade_rows), Decimal(0)),
        by_fuel_grade=grade_rows,
        by_station=station_rows,
    )


@router.get("/revenue", response_model=OrgRevenueReport)
async def org_revenue_report(
    organization_id: uuid.UUID,
    date_from: date = Query(...),
    date_to: date = Query(...),
    station_id: list[uuid.UUID] | None = Query(default=None),
    current_user: User = Depends(require_permission(REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> OrgRevenueReport:
    _validate_date_range(date_from, date_to)
    station_ids = await _authorized_stations(
        db, organization_id=organization_id, current_user=current_user, permission_code=REPORT_READ, station_id=station_id
    )
    shifts = await approved_shifts_in_range(db, station_ids, date_from, date_to)
    by_grade, by_station_sales = await sales_by_grade_and_station(db, shifts)
    by_category, by_station_tender = await tender_totals_by_category_and_station(db, shifts)

    stations = await station_names(db, list({*by_station_sales.keys(), *by_station_tender.keys()}))
    station_rows = []
    for sid in {*by_station_sales.keys(), *by_station_tender.keys()}:
        tender = by_station_tender.get(sid, {"cash": Decimal(0), "card": Decimal(0), "digital": Decimal(0), "credit": Decimal(0), "total": Decimal(0)})
        station_rows.append(
            OrgRevenueStationRow(
                station_id=sid,
                station_name=stations[sid].name if sid in stations else "Unknown",
                expected_revenue=by_station_sales.get(sid, {}).get("revenue", Decimal(0)),
                total_tender_amount=tender["total"],
                cash_amount=tender["cash"],
                card_amount=tender["card"],
                digital_amount=tender["digital"],
                credit_amount=tender["credit"],
            )
        )

    return OrgRevenueReport(
        date_from=date_from,
        date_to=date_to,
        total_recognized_revenue=sum((v["revenue"] for v in by_grade.values()), Decimal(0)),
        total_tender_amount=sum(by_category.values(), Decimal(0)),
        cash_amount=by_category.get("cash", Decimal(0)),
        card_amount=by_category.get("card", Decimal(0)),
        digital_amount=by_category.get("digital", Decimal(0)),
        credit_amount=by_category.get("credit", Decimal(0)),
        by_station=station_rows,
    )


@router.get("/expenses", response_model=OrgExpenseReport)
async def org_expense_report(
    organization_id: uuid.UUID,
    date_from: date = Query(...),
    date_to: date = Query(...),
    station_id: list[uuid.UUID] | None = Query(default=None),
    current_user: User = Depends(require_permission(REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> OrgExpenseReport:
    _validate_date_range(date_from, date_to)
    station_ids = await _authorized_stations(
        db, organization_id=organization_id, current_user=current_user, permission_code=REPORT_READ, station_id=station_id
    )
    # Org-level expenses (station_id IS NULL) are visible to anyone with
    # REPORT_READ anywhere in the org - the same rule the single-station
    # expense-summary report already applies (app/api/reports.py).
    expenses = (
        await db.execute(
            select(Expense).where(
                Expense.organization_id == organization_id,
                (Expense.station_id.in_(station_ids)) | Expense.station_id.is_(None),
                Expense.expense_date >= date_from,
                Expense.expense_date <= date_to,
            )
        )
    ).scalars().all()

    by_category = categorize_expenses(expenses)

    by_station_bucket: dict[uuid.UUID, dict[str, Decimal]] = {}
    for e in expenses:
        if e.station_id is None:
            continue
        bucket = by_station_bucket.setdefault(e.station_id, {"total": Decimal(0), "approved": Decimal(0)})
        bucket["total"] += e.amount
        if e.reversed_at is None and e.status == "approved":
            bucket["approved"] += e.amount
    stations = await station_names(db, list(by_station_bucket.keys()))
    station_rows = [
        OrgExpenseStationRow(
            station_id=sid,
            station_name=stations[sid].name if sid in stations else "Unknown",
            total_amount=v["total"],
            approved_amount=v["approved"],
        )
        for sid, v in by_station_bucket.items()
    ]

    grand_total = sum((r.total_amount for r in by_category), Decimal(0))
    grand_approved = sum((r.approved_amount for r in by_category), Decimal(0))
    return OrgExpenseReport(
        date_from=date_from,
        date_to=date_to,
        by_category=by_category,
        by_station=station_rows,
        grand_total=grand_total,
        grand_approved=grand_approved,
    )


@router.get("/stock", response_model=OrgStockReport)
async def org_stock_report(
    organization_id: uuid.UUID,
    station_id: list[uuid.UUID] | None = Query(default=None),
    current_user: User = Depends(require_permission(REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> OrgStockReport:
    station_ids = await _authorized_stations(
        db, organization_id=organization_id, current_user=current_user, permission_code=REPORT_READ, station_id=station_id
    )
    tank_rows = await current_tank_stock(db, station_ids)

    grades = await fuel_grade_names(db, {r["tank"].fuel_grade_id for r in tank_rows})
    stations = await station_names(db, list({r["tank"].station_id for r in tank_rows}))

    by_grade_totals: dict[uuid.UUID, Decimal] = {}
    tanks: list[OrgStockTankRow] = []
    for r in tank_rows:
        tank = r["tank"]
        grade = grades.get(tank.fuel_grade_id)
        station = stations.get(tank.station_id)
        by_grade_totals[tank.fuel_grade_id] = by_grade_totals.get(tank.fuel_grade_id, Decimal(0)) + r["book_stock"]
        tanks.append(
            OrgStockTankRow(
                tank_id=tank.id,
                tank_code=tank.code,
                station_id=tank.station_id,
                station_name=station.name if station else "Unknown",
                fuel_grade_id=tank.fuel_grade_id,
                fuel_grade_name=grade.name if grade else "Unknown",
                book_stock=r["book_stock"],
                last_physical_dip_reading=r["last_physical_dip_reading"],
                last_physical_dip_at=r["last_physical_dip_at"],
            )
        )

    grade_rows = [
        OrgStockGradeRow(fuel_grade_id=gid, fuel_grade_name=grades[gid].name if gid in grades else "Unknown", total_book_stock=total)
        for gid, total in by_grade_totals.items()
    ]
    return OrgStockReport(generated_at=datetime.now(timezone.utc), by_fuel_grade=grade_rows, tanks=tanks)


# Priority order used to resolve one employee's single status for a given
# day when they have attendance records at more than one authorized
# station on the same date (the unique constraint is per-station, so this
# is a real, if unusual, possibility for staff covering multiple
# stations) - "did they show up anywhere" outranks "were they recorded
# late somewhere", which outranks a half day, which outranks approved
# leave, which outranks absent. Documented explicitly: this is a
# deliberate business rule, not an arbitrary pick.
_STATUS_PRIORITY = [
    AttendanceStatus.PRESENT.value,
    AttendanceStatus.LATE.value,
    AttendanceStatus.HALF_DAY.value,
    AttendanceStatus.LEAVE.value,
    AttendanceStatus.ABSENT.value,
]


@router.get("/attendance", response_model=OrgAttendanceReport)
async def org_attendance_report(
    organization_id: uuid.UUID,
    date_from: date = Query(...),
    date_to: date = Query(...),
    station_id: list[uuid.UUID] | None = Query(default=None),
    current_user: User = Depends(require_permission(ATTENDANCE_READ)),
    db: AsyncSession = Depends(get_db),
) -> OrgAttendanceReport:
    _validate_date_range(date_from, date_to)
    station_ids = await _authorized_stations(
        db, organization_id=organization_id, current_user=current_user, permission_code=ATTENDANCE_READ, station_id=station_id
    )

    total_employees = (
        await db.execute(
            select(UserStationRole.user_id)
            .join(User, User.id == UserStationRole.user_id)
            .where(
                UserStationRole.organization_id == organization_id,
                UserStationRole.is_active.is_(True),
                User.is_active.is_(True),
                (UserStationRole.station_id.in_(station_ids)) | UserStationRole.station_id.is_(None),
            )
            .distinct()
        )
    ).all()
    total_employee_count = len(total_employees)

    records = (
        await db.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.organization_id == organization_id,
                AttendanceRecord.station_id.in_(station_ids),
                AttendanceRecord.attendance_date >= date_from,
                AttendanceRecord.attendance_date <= date_to,
            )
        )
    ).scalars().all()

    # Per-day, per-user resolved status (dedup rule above).
    by_day_user: dict[date, dict[uuid.UUID, str]] = {}
    by_station_counts: dict[uuid.UUID, dict[str, int]] = {}
    for r in records:
        day_bucket = by_day_user.setdefault(r.attendance_date, {})
        existing = day_bucket.get(r.user_id)
        if existing is None or _STATUS_PRIORITY.index(r.status) < _STATUS_PRIORITY.index(existing):
            day_bucket[r.user_id] = r.status

        station_bucket = by_station_counts.setdefault(
            r.station_id, {"present": 0, "absent": 0, "late": 0, "half_day": 0, "leave": 0}
        )
        station_bucket[r.status] = station_bucket.get(r.status, 0) + 1

    days: list[OrgAttendanceDay] = []
    for day in sorted(by_day_user.keys()):
        statuses = list(by_day_user[day].values())
        days.append(
            OrgAttendanceDay(
                attendance_date=day,
                present_count=statuses.count(AttendanceStatus.PRESENT.value),
                absent_count=statuses.count(AttendanceStatus.ABSENT.value),
                late_count=statuses.count(AttendanceStatus.LATE.value),
                half_day_count=statuses.count(AttendanceStatus.HALF_DAY.value),
                leave_count=statuses.count(AttendanceStatus.LEAVE.value),
            )
        )

    stations = await station_names(db, list(by_station_counts.keys()))
    station_rows = [
        OrgAttendanceStationRow(
            station_id=sid,
            station_name=stations[sid].name if sid in stations else "Unknown",
            present_count=v.get("present", 0),
            absent_count=v.get("absent", 0),
            late_count=v.get("late", 0),
            half_day_count=v.get("half_day", 0),
            leave_count=v.get("leave", 0),
        )
        for sid, v in by_station_counts.items()
    ]

    return OrgAttendanceReport(
        date_from=date_from,
        date_to=date_to,
        total_employees=total_employee_count,
        days=days,
        by_station=station_rows,
    )


@router.get("/station-performance", response_model=OrgStationPerformanceReport)
async def org_station_performance_report(
    organization_id: uuid.UUID,
    date_from: date = Query(...),
    date_to: date = Query(...),
    station_id: list[uuid.UUID] | None = Query(default=None),
    current_user: User = Depends(require_permission(REPORT_READ)),
    db: AsyncSession = Depends(get_db),
) -> OrgStationPerformanceReport:
    """One comparable row per authorized station: sales, revenue tendered,
    approved expenses and current stock, side by side. Deliberately no
    profit/margin column - see StationPerformanceRow's own docstring."""
    _validate_date_range(date_from, date_to)
    station_ids = await _authorized_stations(
        db, organization_id=organization_id, current_user=current_user, permission_code=REPORT_READ, station_id=station_id
    )

    shifts = await approved_shifts_in_range(db, station_ids, date_from, date_to)
    by_grade, by_station_sales = await sales_by_grade_and_station(db, shifts)
    _by_category, by_station_tender = await tender_totals_by_category_and_station(db, shifts)

    expenses = (
        await db.execute(
            select(Expense).where(
                Expense.organization_id == organization_id,
                Expense.station_id.in_(station_ids),
                Expense.expense_date >= date_from,
                Expense.expense_date <= date_to,
                Expense.status == "approved",
                Expense.reversed_at.is_(None),
            )
        )
    ).scalars().all()
    approved_expense_by_station: dict[uuid.UUID, Decimal] = {}
    for e in expenses:
        approved_expense_by_station[e.station_id] = approved_expense_by_station.get(e.station_id, Decimal(0)) + e.amount

    tank_rows = await current_tank_stock(db, station_ids)
    stock_by_station: dict[uuid.UUID, Decimal] = {}
    for r in tank_rows:
        sid = r["tank"].station_id
        stock_by_station[sid] = stock_by_station.get(sid, Decimal(0)) + r["book_stock"]

    employee_count_rows = (
        await db.execute(
            select(UserStationRole.station_id, func.count(func.distinct(UserStationRole.user_id)))
            .join(User, User.id == UserStationRole.user_id)
            .where(
                UserStationRole.organization_id == organization_id,
                UserStationRole.station_id.in_(station_ids),
                UserStationRole.is_active.is_(True),
                User.is_active.is_(True),
            )
            .group_by(UserStationRole.station_id)
        )
    ).all()
    employee_count_by_station = dict(employee_count_rows)

    stations = await station_names(db, station_ids)
    rows = []
    for sid in station_ids:
        sales = by_station_sales.get(sid, {"litres": Decimal(0), "revenue": Decimal(0)})
        tender = by_station_tender.get(sid, {"total": Decimal(0)})
        rows.append(
            StationPerformanceRow(
                station_id=sid,
                station_name=stations[sid].name if sid in stations else "Unknown",
                litres_sold=sales["litres"],
                expected_revenue=sales["revenue"],
                total_tender_amount=tender.get("total", Decimal(0)),
                approved_expenses=approved_expense_by_station.get(sid, Decimal(0)),
                total_book_stock=stock_by_station.get(sid, Decimal(0)),
                employee_count=employee_count_by_station.get(sid, 0),
            )
        )

    return OrgStationPerformanceReport(date_from=date_from, date_to=date_to, rows=rows)
