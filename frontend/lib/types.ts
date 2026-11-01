export interface StationRoleSummary {
  organization_id: string;
  station_id: string | null;
  role_name: string;
  permissions: string[];
}

export interface Me {
  id: string;
  email: string;
  full_name: string;
  is_superuser: boolean;
  station_roles: StationRoleSummary[];
}

export interface Organization {
  id: string;
  name: string;
  legal_name: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Session {
  id: string;
  created_at: string;
  expires_at: string;
}

export interface OrgUser {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  created_at: string;
}

export interface Permission {
  id: string;
  code: string;
  description: string;
}

export interface Role {
  id: string;
  name: string;
  description: string;
  is_system: boolean;
  permissions: Permission[];
}

export interface RoleAssignment {
  id: string;
  user_id: string;
  organization_id: string;
  station_id: string | null;
  role_id: string;
  is_active: boolean;
}

export interface Station {
  id: string;
  organization_id: string;
  name: string;
  code: string;
  address: string | null;
  timezone: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface SupplierBalance {
  supplier_id: string;
  supplier_name: string;
  balance: string;
}

export interface CreditCustomerBalance {
  credit_customer_id: string;
  credit_customer_name: string;
  balance: string;
}

export interface Expense {
  id: string;
  organization_id: string;
  station_id: string | null;
  category: string;
  description: string;
  amount: string;
  expense_date: string;
  status: "pending" | "approved" | "rejected";
  created_by_user_id: string;
  created_at: string;
  decided_by_user_id: string | null;
  decided_at: string | null;
  rejection_reason: string | null;
  reversed_by_user_id: string | null;
  reversed_at: string | null;
  reversal_reason: string | null;
}

export interface InventoryItemWithStock {
  id: string;
  organization_id: string;
  station_id: string;
  sku: string;
  name: string;
  unit: string;
  reorder_level: string;
  is_active: boolean;
  on_hand: string;
  below_reorder_level: boolean;
}

export interface InventoryMovement {
  id: string;
  organization_id: string;
  station_id: string;
  inventory_item_id: string;
  movement_type: "receipt" | "issue" | "sale" | "adjustment_increase" | "adjustment_decrease";
  quantity: string;
  amount: string | null;
  reference: string | null;
  reason: string | null;
  created_by_user_id: string;
  created_at: string;
}

export interface DailyFuelSalesGradeRow {
  fuel_grade_id: string;
  fuel_grade_code: string;
  fuel_grade_name: string;
  litres_sold: string;
  expected_revenue: string;
}

export interface DailyFuelSalesDay {
  sale_date: string;
  shift_count: number;
  grades: DailyFuelSalesGradeRow[];
  total_litres_sold: string;
  total_expected_revenue: string;
  total_tender_amount: string;
}

export interface TankVarianceReportRow {
  shift_id: string;
  shift_date: string;
  tank_id: string;
  tank_code: string;
  opening_book_stock: string;
  closing_book_stock: string;
  physical_closing_reading: string | null;
  closing_variance: string | null;
  closing_variance_percent: string | null;
  within_tolerance: boolean | null;
}

export interface ShiftReconciliationReportRow {
  shift_id: string;
  shift_label: string | null;
  opened_at: string;
  status: string;
  expected_fuel_revenue: string;
  total_tender_amount: string;
  revenue_variance: string;
  expected_physical_cash: string;
  actual_physical_cash: string;
  cash_shortage_excess: string;
  requires_authorization: boolean;
  authorized_at: string | null;
}

export interface PendingApprovalsReport {
  tanker_receipts_awaiting_approval: number;
  shifts_awaiting_approval: number;
  unapproved_meter_events: number;
  reconciliations_requiring_authorization: number;
  unapproved_decreasing_cash_movements: number;
  pending_expenses: number;
  unapproved_supplier_payments: number;
  low_stock_inventory_items: number;
}

export interface AuditLogEntry {
  id: string;
  organization_id: string | null;
  station_id: string | null;
  actor_user_id: string | null;
  action: string;
  entity_type: string;
  entity_id: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  created_at: string;
}

export type ShiftStatus = "open" | "closed" | "approved";

export interface Shift {
  id: string;
  organization_id: string;
  station_id: string;
  label: string | null;
  status: ShiftStatus;
  opened_by_user_id: string;
  opened_at: string;
  closed_by_user_id: string | null;
  closed_at: string | null;
  approved_by_user_id: string | null;
  approved_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ShiftTankReading {
  id: string;
  shift_id: string;
  tank_id: string;
  reading_type: "opening" | "closing";
  dip_reading: string;
  recorded_by_user_id: string;
  recorded_at: string;
}

export interface ShiftNozzleReading {
  id: string;
  shift_id: string;
  nozzle_id: string;
  opening_totalizer: string;
  opening_recorded_by_user_id: string;
  opening_recorded_at: string;
  closing_totalizer: string | null;
  closing_recorded_by_user_id: string | null;
  closing_recorded_at: string | null;
  dispensed_litres: string | null;
  meter_event_type: string | null;
  meter_event_approved_by_user_id: string | null;
}

export interface NozzleOverview {
  nozzle_id: string;
  nozzle_code: string;
  dispenser_id: string;
  dispenser_code: string;
  tank_id: string;
  tank_code: string;
  fuel_grade_id: string;
  fuel_grade_name: string;
  last_closing_totalizer: string | null;
  current_price_per_litre: string | null;
}

export interface Tank {
  id: string;
  station_id: string;
  fuel_grade_id: string;
  code: string;
  name: string;
  capacity: string;
  safe_fill_limit: string;
  is_active: boolean;
  book_stock: string;
  safe_capacity_available: string;
}

export interface FuelGrade {
  id: string;
  organization_id: string;
  name: string;
  code: string;
  is_active: boolean;
}

export interface FuelPrice {
  id: string;
  station_id: string;
  fuel_grade_id: string;
  price_per_litre: string;
  effective_from: string;
  created_by_user_id: string | null;
  created_at: string;
}

export interface PaymentMethod {
  id: string;
  organization_id: string;
  code: string;
  name: string;
  category: "cash" | "card" | "digital" | "credit";
  is_active: boolean;
}

export interface CreditCustomer {
  id: string;
  organization_id: string;
  name: string;
  is_active: boolean;
}

export interface ShiftTender {
  id: string;
  shift_id: string;
  payment_method_id: string;
  amount: string;
  credit_customer_id: string | null;
  reference: string | null;
  recorded_by_user_id: string;
  recorded_at: string;
  reversed_at: string | null;
}

export type CashMovementType =
  | "opening_cash"
  | "expense"
  | "deposit"
  | "safe_transfer_in"
  | "safe_transfer_out"
  | "refund"
  | "other_increase"
  | "other_decrease";

export interface ShiftCashMovement {
  id: string;
  shift_id: string;
  movement_type: CashMovementType;
  amount: string;
  reason: string;
  recorded_by_user_id: string;
  recorded_at: string;
  approved_by_user_id: string | null;
  reversed_at: string | null;
}

export interface ShiftReconciliation {
  id: string;
  shift_id: string;
  expected_fuel_revenue: string;
  total_tender_amount: string;
  revenue_variance: string;
  revenue_variance_percent: string;
  revenue_within_tolerance: boolean;
  expected_physical_cash: string;
  actual_physical_cash: string;
  cash_shortage_excess: string;
  cash_within_tolerance: boolean;
  requires_authorization: boolean;
  explanation: string | null;
  authorized_by_user_id: string | null;
  authorized_at: string | null;
}

export type TankerReceiptStatus = "pending_unload" | "awaiting_approval" | "approved" | "rejected";

export interface TankerReceipt {
  id: string;
  organization_id: string;
  station_id: string;
  tank_id: string;
  fuel_grade_id: string;
  supplier_id: string;
  status: TankerReceiptStatus;
  tanker_registration: string;
  driver_name: string | null;
  supplier_invoice_reference: string | null;
  invoice_quantity: string | null;
  dispatched_quantity: string | null;
  calibrated_quantity: string | null;
  pre_receipt_tank_reading: string;
  post_receipt_tank_reading: string | null;
  tank_gain_quantity: string | null;
  accepted_quantity: string | null;
  payable_quantity_basis: string | null;
  payable_quantity: string | null;
  variance_quantity: string | null;
  variance_percent: string | null;
  within_tolerance: boolean | null;
  rejection_reason: string | null;
  created_at: string;
}

export interface Supplier {
  id: string;
  organization_id: string;
  name: string;
  is_active: boolean;
}
