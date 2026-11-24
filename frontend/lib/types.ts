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
  currency_code: string | null;
  phone: string | null;
  address: string | null;
  city: string | null;
  province: string | null;
  country: string | null;
  created_at: string;
  updated_at: string;
}

export interface Invitation {
  id: string;
  organization_id: string;
  email: string;
  full_name: string;
  role_id: string;
  station_id: string | null;
  expires_at: string;
  accepted_at: string | null;
  revoked_at: string | null;
  invited_by_user_id: string;
  created_at: string;
}

export interface InvitationCreateResponse {
  id: string;
  email: string;
  full_name: string;
  expires_at: string;
  token: string;
}

export type SupportSessionStatus = "active" | "ended" | "expired";

export interface SupportSession {
  id: string;
  organization_id: string;
  organization_name: string;
  station_id: string | null;
  station_name: string | null;
  reason: string;
  created_at: string;
  expires_at: string;
  ended_at: string | null;
  status: SupportSessionStatus;
}

export interface InvitationPreview {
  organization_name: string;
  email: string;
  full_name: string;
  role_name: string;
  station_name: string | null;
  valid: boolean;
  reason: string | null;
}

export interface PlatformOrganizationRow {
  id: string;
  name: string;
  city: string | null;
  is_active: boolean;
  created_at: string;
  owner_full_name: string | null;
  owner_email: string | null;
  station_count: number;
  employee_count: number;
  last_activity_at: string | null;
}

export interface PlatformStats {
  total_organizations: number;
  active_organizations: number;
  suspended_organizations: number;
  total_owners: number;
  total_users: number;
  recent_organizations: { id: string; name: string; is_active: boolean; created_at: string }[];
  generated_at: string;
}

export interface TenantOnboardingResponse {
  organization_id: string;
  organization_name: string;
  station_id: string;
  owner_user_id: string;
  owner_email: string;
}

export interface Plan {
  id: string;
  code: string;
  name: string;
  description: string | null;
  price_monthly: string;
  price_annual: string;
  max_stations: number | null;
  max_users: number | null;
  is_active: boolean;
}

export type SubscriptionStatus = "trial" | "active" | "past_due" | "canceled" | "expired";
export type BillingCycle = "monthly" | "annual";

export interface Subscription {
  id: string;
  organization_id: string;
  plan_id: string;
  plan: Plan;
  status: SubscriptionStatus;
  billing_cycle: BillingCycle;
  trial_ends_at: string | null;
  current_period_start: string;
  current_period_end: string;
  canceled_at: string | null;
}

export type SubscriptionPaymentStatus = "verified" | "failed";

export interface SubscriptionPayment {
  id: string;
  subscription_id: string;
  amount: string;
  method: string;
  reference: string | null;
  status: SubscriptionPaymentStatus;
  period_start: string;
  period_end: string;
  notes: string | null;
  recorded_by_user_id: string;
  created_at: string;
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
  employee_code: string | null;
  job_title: string | null;
  phone: string | null;
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
  created_at: string;
}

// ---- Phase 8b: organization-wide (multi-station) aggregate reports ----

export interface ExpenseSummaryRow {
  category: string;
  total_amount: string;
  approved_amount: string;
  pending_amount: string;
  rejected_amount: string;
  count: number;
}

export interface OrgSalesGradeRow {
  fuel_grade_id: string;
  fuel_grade_code: string;
  fuel_grade_name: string;
  litres_sold: string;
  expected_revenue: string;
}

export interface OrgSalesStationRow {
  station_id: string;
  station_name: string;
  litres_sold: string;
  expected_revenue: string;
}

export interface OrgSalesReport {
  date_from: string;
  date_to: string;
  shift_count: number;
  total_litres_sold: string;
  total_expected_revenue: string;
  by_fuel_grade: OrgSalesGradeRow[];
  by_station: OrgSalesStationRow[];
}

export interface OrgRevenueStationRow {
  station_id: string;
  station_name: string;
  expected_revenue: string;
  total_tender_amount: string;
  cash_amount: string;
  card_amount: string;
  digital_amount: string;
  credit_amount: string;
}

export interface OrgRevenueReport {
  date_from: string;
  date_to: string;
  total_recognized_revenue: string;
  total_tender_amount: string;
  cash_amount: string;
  card_amount: string;
  digital_amount: string;
  credit_amount: string;
  by_station: OrgRevenueStationRow[];
}

export interface OrgExpenseStationRow {
  station_id: string;
  station_name: string;
  total_amount: string;
  approved_amount: string;
}

export interface OrgExpenseReport {
  date_from: string;
  date_to: string;
  by_category: ExpenseSummaryRow[];
  by_station: OrgExpenseStationRow[];
  grand_total: string;
  grand_approved: string;
}

export interface OrgStockTankRow {
  tank_id: string;
  tank_code: string;
  station_id: string;
  station_name: string;
  fuel_grade_id: string;
  fuel_grade_name: string;
  book_stock: string;
  last_physical_dip_reading: string | null;
  last_physical_dip_at: string | null;
}

export interface OrgStockGradeRow {
  fuel_grade_id: string;
  fuel_grade_name: string;
  total_book_stock: string;
}

export interface OrgStockReport {
  generated_at: string;
  by_fuel_grade: OrgStockGradeRow[];
  tanks: OrgStockTankRow[];
}

export interface OrgAttendanceDay {
  attendance_date: string;
  present_count: number;
  absent_count: number;
  late_count: number;
  half_day_count: number;
  leave_count: number;
}

export interface OrgAttendanceStationRow {
  station_id: string;
  station_name: string;
  present_count: number;
  absent_count: number;
  late_count: number;
  half_day_count: number;
  leave_count: number;
}

export interface OrgAttendanceReport {
  date_from: string;
  date_to: string;
  total_employees: number;
  days: OrgAttendanceDay[];
  by_station: OrgAttendanceStationRow[];
}

export interface StationPerformanceRow {
  station_id: string;
  station_name: string;
  litres_sold: string;
  expected_revenue: string;
  total_tender_amount: string;
  approved_expenses: string;
  total_book_stock: string;
  employee_count: number;
}

export interface OrgStationPerformanceReport {
  date_from: string;
  date_to: string;
  rows: StationPerformanceRow[];
}

export interface OrgDailySalesDay {
  sales_date: string;
  litres_sold: string;
  expected_revenue: string;
}

export interface OrgDailySalesReport {
  date_from: string;
  date_to: string;
  days: OrgDailySalesDay[];
}

export interface Station {
  id: string;
  organization_id: string;
  name: string;
  code: string;
  address: string | null;
  phone: string | null;
  email: string | null;
  timezone: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ExpenseCategory {
  id: string;
  organization_id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ShiftTemplate {
  id: string;
  organization_id: string;
  station_id: string;
  name: string;
  start_time: string;
  end_time: string;
  grace_period_minutes: number;
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
  meter_event_pre_reading: string | null;
  meter_event_post_reading: string | null;
  meter_event_notes: string | null;
  meter_event_approved_by_user_id: string | null;
  meter_event_approved_at: string | null;
}

export interface Dispenser {
  id: string;
  station_id: string;
  code: string;
  name: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Nozzle {
  id: string;
  dispenser_id: string;
  tank_id: string;
  code: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export type HardwareDeviceType = "dispenser_controller" | "forecourt_controller" | "atg" | "existing_pos" | "biometric_attendance";
export type HardwareConnectionType = "tcp_ip" | "serial";
export type HardwareDeviceStatus = "draft" | "testing" | "connected" | "failed";

export interface HardwareDevice {
  id: string;
  station_id: string;
  device_type: HardwareDeviceType;
  label: string;
  brand: string | null;
  model: string | null;
  serial_number: string | null;
  connection_type: HardwareConnectionType;
  ip_address: string | null;
  port: number | null;
  com_port: string | null;
  status: HardwareDeviceStatus;
  last_test_message: string | null;
  created_by_user_id: string;
  created_at: string;
  updated_at: string;
}

export type MeterEventType = "replacement" | "reset" | "rollover";

export interface MeterEventRow {
  nozzle_reading_id: string;
  shift_id: string;
  shift_label: string | null;
  shift_opened_at: string;
  shift_status: string;
  station_id: string;
  nozzle_id: string;
  nozzle_code: string;
  dispenser_code: string;
  tank_code: string;
  fuel_grade_name: string;
  event_type: string;
  opening_totalizer: string;
  meter_event_pre_reading: string;
  meter_event_post_reading: string;
  closing_totalizer: string;
  dispensed_litres: string | null;
  notes: string | null;
  recorded_by_user_id: string | null;
  recorded_at: string | null;
  approved_by_user_id: string | null;
  approved_at: string | null;
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
  location: string | null;
  calibration_reference: string | null;
  is_active: boolean;
  book_stock: string;
  safe_capacity_available: string;
}

export interface TankDipChartEntry {
  id: string;
  tank_id: string;
  dip_mm: string;
  volume_litres: string;
  created_by_user_id: string | null;
  created_at: string;
}

export interface TankDipChartLookupResult {
  dip_mm: string;
  volume_litres: string;
  exact_match: boolean;
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
  phone: string | null;
  contact_person: string | null;
  credit_limit: string | null;
  payment_terms_days: number | null;
  address: string | null;
  notes: string | null;
  is_active: boolean;
}

export interface CreditCustomerBalanceDetail {
  credit_customer_id: string;
  credit_customer_name: string;
  balance: string;
  credit_limit: string | null;
}

export interface CreditCustomerStatementEntry {
  date: string;
  description: string;
  debit: string;
  credit: string;
  running_balance: string;
}

export interface CreditCustomerStatement {
  credit_customer_id: string;
  credit_customer_name: string;
  opening_balance: string;
  entries: CreditCustomerStatementEntry[];
  closing_balance: string;
}

export interface CreditCustomerAgeingEntry {
  credit_customer_id: string;
  credit_customer_name: string;
  current: string;
  days_30: string;
  days_60: string;
  days_90: string;
  over_90: string;
  total: string;
}

export type ReadingCorrectionStatus = "pending" | "approved" | "rejected";

export interface ReadingCorrection {
  id: string;
  organization_id: string;
  station_id: string;
  shift_id: string;
  reading_type: string;
  tank_reading_id: string | null;
  nozzle_reading_id: string | null;
  original_value: string;
  corrected_value: string;
  reason: string;
  original_submitted_at: string;
  is_post_lock: boolean;
  status: ReadingCorrectionStatus;
  requested_by_user_id: string;
  requested_at: string;
  decided_by_user_id: string | null;
  decided_at: string | null;
  rejection_reason: string | null;
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
  contact_phone: string | null;
  contact_email: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface SupplierInvoice {
  id: string;
  organization_id: string;
  supplier_id: string;
  tanker_receipt_id: string | null;
  reference: string | null;
  amount: string;
  invoice_date: string;
  description: string | null;
  created_by_user_id: string;
  created_at: string;
}

export interface SupplierPayment {
  id: string;
  organization_id: string;
  supplier_id: string;
  amount: string;
  payment_date: string;
  reference: string | null;
  recorded_by_user_id: string;
  recorded_at: string;
  approved_by_user_id: string | null;
  approved_at: string | null;
  reversed_by_user_id: string | null;
  reversed_at: string | null;
  reversal_reason: string | null;
}

export interface SupplierLedgerStatementEntry {
  entry_date: string;
  entry_type: string;
  reference: string | null;
  description: string | null;
  amount: string;
  running_balance: string;
}

export interface SupplierLedgerStatement {
  supplier_id: string;
  supplier_name: string;
  date_from: string;
  date_to: string;
  opening_balance: string;
  entries: SupplierLedgerStatementEntry[];
  closing_balance: string;
}

export interface AttendanceRecord {
  id: string;
  organization_id: string;
  station_id: string;
  user_id: string;
  attendance_date: string;
  status: string;
  check_in_time: string | null;
  check_out_time: string | null;
  source: string;
  notes: string | null;
  recorded_by_user_id: string;
  created_at: string;
  updated_at: string;
}

export interface PayrollRule {
  id: string;
  organization_id: string;
  station_id: string;
  rule_name: string;
  shift_start_time: string;
  late_threshold_minutes: number;
  half_day_threshold_minutes: number;
  late_deduction_amount: string;
  absent_deduction_amount: string;
  half_day_deduction_amount: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface SalaryRecord {
  id: string;
  organization_id: string;
  station_id: string;
  user_id: string;
  period_start: string;
  period_end: string;
  base_salary: string;
  total_deductions: string;
  net_salary: string;
  days_present: number;
  days_absent: number;
  days_late: number;
  days_half_day: number;
  days_leave: number;
  notes: string | null;
  generated_by_user_id: string;
  is_finalized: boolean;
  created_at: string;
  updated_at: string;
}

export type EVChargerType = "ac" | "dc";
export type EVPortStatus = "available" | "occupied" | "charging" | "out_of_service" | "faulted" | "offline";
export type EVPricingBasis = "per_kwh" | "time_based" | "session_fee";
export type EVSessionStatus =
  | "initiated"
  | "charging"
  | "completed"
  | "interrupted"
  | "failed"
  | "cancelled"
  | "refunded";

export interface EVCharger {
  id: string;
  station_id: string;
  code: string;
  label: string;
  manufacturer: string | null;
  model: string | null;
  serial_number: string | null;
  charger_type: EVChargerType;
  rated_power_kw: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface EVChargerPort {
  id: string;
  charger_id: string;
  port_code: string;
  connector_standard: string;
  rated_power_kw: string | null;
  status: EVPortStatus;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface EVTariff {
  id: string;
  station_id: string;
  charger_id: string | null;
  pricing_basis: EVPricingBasis;
  rate: string;
  effective_from: string;
  effective_to: string | null;
  created_by_user_id: string | null;
  created_at: string;
}

export interface EVChargingSession {
  id: string;
  port_id: string;
  tariff_id: string;
  session_reference: string | null;
  status: EVSessionStatus;
  start_time: string;
  end_time: string | null;
  start_meter_kwh: string;
  end_meter_kwh: string | null;
  delivered_kwh: string | null;
  gross_amount: string | null;
  payment_method_id: string | null;
  credit_customer_id: string | null;
  vehicle_reference: string | null;
  fault_reason: string | null;
  notes: string | null;
  created_by_user_id: string;
  reversed_by_user_id: string | null;
  reversed_at: string | null;
  reversal_reason: string | null;
  created_at: string;
  updated_at: string;
}
