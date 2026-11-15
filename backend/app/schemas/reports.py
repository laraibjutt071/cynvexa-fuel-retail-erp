import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class DailyFuelSalesGradeRow(BaseModel):
    fuel_grade_id: uuid.UUID
    fuel_grade_code: str
    fuel_grade_name: str
    litres_sold: Decimal
    expected_revenue: Decimal


class DailyFuelSalesDay(BaseModel):
    sale_date: date
    shift_count: int
    grades: list[DailyFuelSalesGradeRow]
    total_litres_sold: Decimal
    total_expected_revenue: Decimal
    total_tender_amount: Decimal


class TankVarianceReportRow(BaseModel):
    shift_id: uuid.UUID
    shift_date: date
    tank_id: uuid.UUID
    tank_code: str
    opening_book_stock: Decimal
    closing_book_stock: Decimal
    physical_closing_reading: Decimal | None
    closing_variance: Decimal | None
    closing_variance_percent: Decimal | None
    within_tolerance: bool | None


class ShiftReconciliationReportRow(BaseModel):
    shift_id: uuid.UUID
    shift_label: str | None
    opened_at: datetime
    status: str
    expected_fuel_revenue: Decimal
    total_tender_amount: Decimal
    revenue_variance: Decimal
    expected_physical_cash: Decimal
    actual_physical_cash: Decimal
    cash_shortage_excess: Decimal
    requires_authorization: bool
    authorized_at: datetime | None


class PendingApprovalsReport(BaseModel):
    tanker_receipts_awaiting_approval: int
    shifts_awaiting_approval: int
    unapproved_meter_events: int
    reconciliations_requiring_authorization: int
    unapproved_decreasing_cash_movements: int
    pending_expenses: int
    unapproved_supplier_payments: int
    low_stock_inventory_items: int


class ExpenseSummaryRow(BaseModel):
    category: str
    total_amount: Decimal
    approved_amount: Decimal
    pending_amount: Decimal
    rejected_amount: Decimal
    count: int


class ExpenseSummaryReport(BaseModel):
    date_from: date
    date_to: date
    rows: list[ExpenseSummaryRow]
    grand_total: Decimal
    grand_approved: Decimal


class InventoryStockRow(BaseModel):
    inventory_item_id: uuid.UUID
    sku: str
    name: str
    unit: str
    on_hand: Decimal
    reorder_level: Decimal
    is_below_reorder: bool


class SupplierLedgerStatementEntry(BaseModel):
    entry_date: date
    entry_type: str
    reference: str | None
    description: str | None
    amount: Decimal
    running_balance: Decimal


class SupplierLedgerStatement(BaseModel):
    supplier_id: uuid.UUID
    supplier_name: str
    date_from: date
    date_to: date
    opening_balance: Decimal
    entries: list[SupplierLedgerStatementEntry]
    closing_balance: Decimal


class PriceChangeHistoryRow(BaseModel):
    fuel_grade_id: uuid.UUID
    fuel_grade_name: str
    price_per_litre: Decimal
    effective_from: datetime
    previous_price: Decimal | None
