import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.schemas.reports import ExpenseSummaryRow


class OrgSalesGradeRow(BaseModel):
    fuel_grade_id: uuid.UUID
    fuel_grade_code: str
    fuel_grade_name: str
    litres_sold: Decimal
    expected_revenue: Decimal


class OrgSalesStationRow(BaseModel):
    station_id: uuid.UUID
    station_name: str
    litres_sold: Decimal
    expected_revenue: Decimal


class OrgSalesReport(BaseModel):
    date_from: date
    date_to: date
    shift_count: int
    total_litres_sold: Decimal
    total_expected_revenue: Decimal
    by_fuel_grade: list[OrgSalesGradeRow]
    by_station: list[OrgSalesStationRow]


class OrgRevenueStationRow(BaseModel):
    station_id: uuid.UUID
    station_name: str
    expected_revenue: Decimal
    total_tender_amount: Decimal
    cash_amount: Decimal
    card_amount: Decimal
    digital_amount: Decimal
    credit_amount: Decimal


class OrgRevenueReport(BaseModel):
    """
    total_recognized_revenue is fuel litres x price (app/core/revenue.py) -
    never equal to cash collected. total_tender_amount and the four
    category amounts below are what was actually tendered across every
    payment method (app/core/reconciliation.py's same distinction);
    cash_amount specifically is the portion that became physical cash,
    the rest never does. These are deliberately separate fields, not one
    number - a client comparing them is exactly the intended use.
    """

    date_from: date
    date_to: date
    total_recognized_revenue: Decimal
    total_tender_amount: Decimal
    cash_amount: Decimal
    card_amount: Decimal
    digital_amount: Decimal
    credit_amount: Decimal
    by_station: list[OrgRevenueStationRow]


class OrgExpenseStationRow(BaseModel):
    station_id: uuid.UUID
    station_name: str
    total_amount: Decimal
    approved_amount: Decimal


class OrgExpenseReport(BaseModel):
    date_from: date
    date_to: date
    by_category: list[ExpenseSummaryRow]
    by_station: list[OrgExpenseStationRow]
    grand_total: Decimal
    grand_approved: Decimal


class OrgStockTankRow(BaseModel):
    tank_id: uuid.UUID
    tank_code: str
    station_id: uuid.UUID
    station_name: str
    fuel_grade_id: uuid.UUID
    fuel_grade_name: str
    book_stock: Decimal
    last_physical_dip_reading: Decimal | None
    last_physical_dip_at: datetime | None


class OrgStockGradeRow(BaseModel):
    fuel_grade_id: uuid.UUID
    fuel_grade_name: str
    total_book_stock: Decimal


class OrgStockReport(BaseModel):
    """book_stock is always a live ledger projection (app/core/stock.py);
    last_physical_dip_reading/_at is the most recent physical observation
    on record for that tank, from any shift - the two are never summed
    together, here or anywhere else in this report."""

    generated_at: datetime
    by_fuel_grade: list[OrgStockGradeRow]
    tanks: list[OrgStockTankRow]


class OrgAttendanceDay(BaseModel):
    attendance_date: date
    present_count: int
    absent_count: int
    late_count: int
    half_day_count: int
    leave_count: int


class OrgAttendanceStationRow(BaseModel):
    station_id: uuid.UUID
    station_name: str
    present_count: int
    absent_count: int
    late_count: int
    half_day_count: int
    leave_count: int


class OrgAttendanceReport(BaseModel):
    """total_employees is a headcount (distinct active staff assigned to
    an authorized station), not a sum of attendance rows. days/by_station
    count each employee once per day even if they have attendance records
    at more than one authorized station that day - see
    app/api/org_reports.py's own docstring for the exact resolution rule."""

    date_from: date
    date_to: date
    total_employees: int
    days: list[OrgAttendanceDay]
    by_station: list[OrgAttendanceStationRow]


class StationPerformanceRow(BaseModel):
    """Independent metrics only - no profit/margin figure is computed or
    implied, since this system has no cost-of-goods-sold data to support
    one (docs/ASSUMPTIONS.md #28)."""

    station_id: uuid.UUID
    station_name: str
    litres_sold: Decimal
    expected_revenue: Decimal
    total_tender_amount: Decimal
    approved_expenses: Decimal
    total_book_stock: Decimal
    employee_count: int


class OrgStationPerformanceReport(BaseModel):
    date_from: date
    date_to: date
    rows: list[StationPerformanceRow]
