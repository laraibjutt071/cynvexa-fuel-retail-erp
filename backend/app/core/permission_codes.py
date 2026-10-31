"""
Permission codes are data (seeded Permission rows), not a hardcoded enum consumed
by business logic — this module is only the canonical list used to seed the
database and to annotate endpoints. Changing what a role can do is a data change
(UPDATE role_permissions), never a code change, except when a wholly new action
is introduced (a new row here + a migration/seed update).
"""

ORGANIZATION_CREATE = "organization:create"  # platform (is_superuser) action, not role-based
ORGANIZATION_READ = "organization:read"
ORGANIZATION_UPDATE = "organization:update"

STATION_CREATE = "station:create"
STATION_READ = "station:read"
STATION_UPDATE = "station:update"

USER_CREATE = "user:create"
USER_READ = "user:read"
USER_UPDATE = "user:update"
USER_ASSIGN_ROLE = "user:assign_role"

ROLE_READ = "role:read"

AUDIT_READ = "audit:read"

# Phase B — fuel master data and tanker receipts. Master-data resources
# (fuel grades, suppliers, tanks, dispensers, nozzles) use one combined
# "manage" permission for create+update, same as STATION_UPDATE already
# covers every station field — these are config actions edited as a whole,
# not field-by-field. FuelPrice and FuelReceipt are deliberately NOT folded
# into that pattern: prices are append-only (no update permission exists at
# all - see FuelPrice's model docstring) and receipts have a multi-step,
# separation-of-duties lifecycle (see docs/ASSUMPTIONS.md #15/#16 for which
# roles do which step - still an open owner decision).
FUEL_GRADE_READ = "fuel_grade:read"
FUEL_GRADE_MANAGE = "fuel_grade:manage"

SUPPLIER_READ = "supplier:read"
SUPPLIER_MANAGE = "supplier:manage"

TANK_READ = "tank:read"
TANK_MANAGE = "tank:manage"

DISPENSER_READ = "dispenser:read"
DISPENSER_MANAGE = "dispenser:manage"

NOZZLE_READ = "nozzle:read"
NOZZLE_MANAGE = "nozzle:manage"

FUEL_PRICE_READ = "fuel_price:read"
FUEL_PRICE_CREATE = "fuel_price:create"

FUEL_RECEIPT_READ = "fuel_receipt:read"
FUEL_RECEIPT_CREATE = "fuel_receipt:create"  # create + record the post-unload reading
FUEL_RECEIPT_APPROVE = "fuel_receipt:approve"  # approve or reject; posts the stock ledger entry

# Phase C — shift operations. Per blueprint §12, "Cashier / Nozzle Operator"
# is explicitly named for "shift submission and closure", so SHIFT_OPEN and
# SHIFT_CLOSE (recording readings, exceptional litres, price-change boundary
# readings) are the one place in this app where that role gets a write
# permission beyond station:read. SHIFT_APPROVE (posts the stock ledger,
# approves flagged meter events) stays with the same roles as
# fuel_receipt:approve, for the same separation-of-duties reason.
SHIFT_READ = "shift:read"
SHIFT_OPEN = "shift:open"
SHIFT_CLOSE = "shift:close"
SHIFT_APPROVE = "shift:approve"

# Phase D — shift-level financial reconciliation. Master data (payment
# methods, the minimal credit-customer stub) follows the read/manage
# pattern, Owner-only for manage. The reconciliation workflow itself is
# split exactly like tanker receipts and meter events: recording (tenders,
# cash movements, the reconciliation's own numbers) is one permission,
# approving/authorizing is another - per blueprint §12, which names
# "Accountant" explicitly for "Cash variance approval" and nothing else for
# this area. SHIFT_RECONCILE_APPROVE therefore goes ONLY to Accountant and
# Owner below, not Station Manager/Shift Supervisor (who get it for fuel
# receipts and shift operations) - deliberately narrower here, logged as an
# open question in docs/ASSUMPTIONS.md rather than guessed wider.
PAYMENT_METHOD_READ = "payment_method:read"
PAYMENT_METHOD_MANAGE = "payment_method:manage"

CREDIT_CUSTOMER_READ = "credit_customer:read"
CREDIT_CUSTOMER_MANAGE = "credit_customer:manage"

SHIFT_RECONCILE_RECORD = "shift_reconcile:record"
SHIFT_RECONCILE_APPROVE = "shift_reconcile:approve"

# Phase E/F — supporting operations and the owner dashboard. Supplier
# payments and expenses are cash LEAVING the business, so they keep the
# same record/approve split used everywhere else money goes out
# (tanker receipts, shift cash movements, reconciliation authorization).
# Credit-customer collections are cash COMING IN, so - consistent with
# increasing ShiftCashMovement types never needing approval - collection
# gets a single permission, no separate approve step.
SUPPLIER_LEDGER_READ = "supplier_ledger:read"
SUPPLIER_LEDGER_RECORD = "supplier_ledger:record"
SUPPLIER_LEDGER_APPROVE = "supplier_ledger:approve"

CREDIT_COLLECTION_READ = "credit_collection:read"
CREDIT_COLLECTION_RECORD = "credit_collection:record"

EXPENSE_READ = "expense:read"
EXPENSE_RECORD = "expense:record"
EXPENSE_APPROVE = "expense:approve"

INVENTORY_ITEM_READ = "inventory_item:read"
INVENTORY_ITEM_MANAGE = "inventory_item:manage"
INVENTORY_MOVEMENT_READ = "inventory_movement:read"
INVENTORY_MOVEMENT_RECORD = "inventory_movement:record"
# Adjustments correct a physical-vs-book discrepancy rather than record a
# routine transaction, so they get their own, stricter permission - the
# inventory equivalent of a stock variance investigation.
INVENTORY_MOVEMENT_ADJUST = "inventory_movement:adjust"

# One permission for every owner-dashboard report (daily sales, tank
# variance, shift/cash reconciliation, pending approvals/exceptions) and
# their CSV exports - these are read-only aggregations over data the
# holder's other read permissions already cover; this is the
# dashboard-visibility gate, not a new data-access grant.
REPORT_READ = "report:read"

ALL_PERMISSIONS: dict[str, str] = {
    ORGANIZATION_READ: "View organization profile and settings.",
    ORGANIZATION_UPDATE: "Edit organization profile and settings.",
    STATION_CREATE: "Create a new station within the organization.",
    STATION_READ: "View station configuration.",
    STATION_UPDATE: "Edit station configuration.",
    USER_CREATE: "Create a new user within the organization.",
    USER_READ: "View user accounts and their role assignments.",
    USER_UPDATE: "Edit or deactivate a user account.",
    USER_ASSIGN_ROLE: "Assign or revoke a role for a user at a station or organization.",
    ROLE_READ: "View available roles and their permissions.",
    AUDIT_READ: "View the audit log.",
    FUEL_GRADE_READ: "View the fuel grade catalogue.",
    FUEL_GRADE_MANAGE: "Create or edit a fuel grade.",
    SUPPLIER_READ: "View supplier records.",
    SUPPLIER_MANAGE: "Create or edit a supplier record.",
    TANK_READ: "View tank configuration.",
    TANK_MANAGE: "Create or edit a tank.",
    DISPENSER_READ: "View dispenser configuration.",
    DISPENSER_MANAGE: "Create or edit a dispenser.",
    NOZZLE_READ: "View nozzle configuration.",
    NOZZLE_MANAGE: "Create or edit a nozzle.",
    FUEL_PRICE_READ: "View the fuel price history.",
    FUEL_PRICE_CREATE: "Set a new effective-dated fuel price.",
    FUEL_RECEIPT_READ: "View fuel receipt records.",
    FUEL_RECEIPT_CREATE: "Record a tanker receipt and its post-unload reading.",
    FUEL_RECEIPT_APPROVE: "Approve or reject a tanker receipt, posting it to the stock ledger.",
    SHIFT_READ: "View shift records, readings and variance reports.",
    SHIFT_OPEN: "Open a shift and record opening tank/nozzle readings.",
    SHIFT_CLOSE: "Record closing readings, exceptional litres and price-change boundary readings; close a shift.",
    SHIFT_APPROVE: "Approve a closed shift (posts the stock ledger) and approve flagged meter events.",
    PAYMENT_METHOD_READ: "View configured payment methods.",
    PAYMENT_METHOD_MANAGE: "Create or edit a payment method.",
    CREDIT_CUSTOMER_READ: "View credit customer records.",
    CREDIT_CUSTOMER_MANAGE: "Create or edit a credit customer record.",
    SHIFT_RECONCILE_RECORD: (
        "Record tenders, cash movements and the shift reconciliation's own figures."
    ),
    SHIFT_RECONCILE_APPROVE: (
        "Approve a cash movement, reverse a tender or cash movement, authorize a material "
        "reconciliation discrepancy, and approve a reconciliation amendment."
    ),
    SUPPLIER_LEDGER_READ: "View supplier invoices, payments and balances.",
    SUPPLIER_LEDGER_RECORD: "Record a supplier invoice or payment.",
    SUPPLIER_LEDGER_APPROVE: "Approve or reverse a supplier payment.",
    CREDIT_COLLECTION_READ: "View credit customer collections and balances.",
    CREDIT_COLLECTION_RECORD: "Record or reverse a credit customer collection.",
    EXPENSE_READ: "View expense records.",
    EXPENSE_RECORD: "Record an expense.",
    EXPENSE_APPROVE: "Approve, reject or reverse an expense.",
    INVENTORY_ITEM_READ: "View the shop/lubricant inventory catalogue.",
    INVENTORY_ITEM_MANAGE: "Create or edit an inventory item.",
    INVENTORY_MOVEMENT_READ: "View inventory movements and on-hand stock.",
    INVENTORY_MOVEMENT_RECORD: "Record an inventory receipt, issue or sale.",
    INVENTORY_MOVEMENT_ADJUST: "Record an inventory stock adjustment.",
    REPORT_READ: "View owner-dashboard reports and export them.",
}

# Seed roles. Per docs/ASSUMPTIONS.md #11 and #7, this is a starting point for the
# owner to review and correct, not a final role list. The Phase B additions below
# follow the blueprint's §12 "Protected actions" table where it names a role
# explicitly (fuel price change -> Owner/GM; tanker acceptance -> Station
# Manager/Shift Supervisor); everywhere else is this implementation's own
# reasonable default, logged as an open question in docs/ASSUMPTIONS.md.
SEED_ROLES: dict[str, list[str]] = {
    "Owner": list(ALL_PERMISSIONS.keys()),
    "Station Manager": [
        STATION_READ,
        STATION_UPDATE,
        USER_READ,
        AUDIT_READ,
        ROLE_READ,
        FUEL_GRADE_READ,
        SUPPLIER_READ,
        TANK_READ,
        DISPENSER_READ,
        NOZZLE_READ,
        FUEL_PRICE_READ,
        FUEL_RECEIPT_READ,
        FUEL_RECEIPT_CREATE,
        FUEL_RECEIPT_APPROVE,
        SHIFT_READ,
        SHIFT_OPEN,
        SHIFT_CLOSE,
        SHIFT_APPROVE,
        PAYMENT_METHOD_READ,
        CREDIT_CUSTOMER_READ,
        SHIFT_RECONCILE_RECORD,
        SUPPLIER_LEDGER_READ,
        SUPPLIER_LEDGER_RECORD,
        CREDIT_COLLECTION_READ,
        CREDIT_COLLECTION_RECORD,
        EXPENSE_READ,
        EXPENSE_RECORD,
        EXPENSE_APPROVE,
        INVENTORY_ITEM_READ,
        INVENTORY_ITEM_MANAGE,
        INVENTORY_MOVEMENT_READ,
        INVENTORY_MOVEMENT_RECORD,
        INVENTORY_MOVEMENT_ADJUST,
        REPORT_READ,
    ],
    "Shift Supervisor": [
        STATION_READ,
        USER_READ,
        ROLE_READ,
        FUEL_GRADE_READ,
        TANK_READ,
        DISPENSER_READ,
        NOZZLE_READ,
        FUEL_PRICE_READ,
        FUEL_RECEIPT_READ,
        FUEL_RECEIPT_CREATE,
        FUEL_RECEIPT_APPROVE,
        SHIFT_READ,
        SHIFT_OPEN,
        SHIFT_CLOSE,
        SHIFT_APPROVE,
        PAYMENT_METHOD_READ,
        CREDIT_CUSTOMER_READ,
        SHIFT_RECONCILE_RECORD,
        INVENTORY_ITEM_READ,
        INVENTORY_MOVEMENT_READ,
        INVENTORY_MOVEMENT_RECORD,
    ],
    "Cashier / Operator": [
        STATION_READ,
        SHIFT_READ,
        SHIFT_OPEN,
        SHIFT_CLOSE,
        PAYMENT_METHOD_READ,
        SHIFT_RECONCILE_RECORD,
        INVENTORY_ITEM_READ,
        INVENTORY_MOVEMENT_READ,
        INVENTORY_MOVEMENT_RECORD,
    ],
    "Accountant": [
        STATION_READ,
        AUDIT_READ,
        ROLE_READ,
        SUPPLIER_READ,
        FUEL_PRICE_READ,
        FUEL_RECEIPT_READ,
        SHIFT_READ,
        PAYMENT_METHOD_READ,
        CREDIT_CUSTOMER_READ,
        SHIFT_RECONCILE_RECORD,
        SHIFT_RECONCILE_APPROVE,
        SUPPLIER_LEDGER_READ,
        SUPPLIER_LEDGER_RECORD,
        SUPPLIER_LEDGER_APPROVE,
        CREDIT_COLLECTION_READ,
        CREDIT_COLLECTION_RECORD,
        EXPENSE_READ,
        EXPENSE_RECORD,
        EXPENSE_APPROVE,
        INVENTORY_ITEM_READ,
        INVENTORY_MOVEMENT_READ,
        REPORT_READ,
    ],
    "Storekeeper / Technician": [
        STATION_READ,
        FUEL_GRADE_READ,
        TANK_READ,
        TANK_MANAGE,
        DISPENSER_READ,
        DISPENSER_MANAGE,
        NOZZLE_READ,
        NOZZLE_MANAGE,
        FUEL_RECEIPT_READ,
        FUEL_RECEIPT_CREATE,
        SHIFT_READ,
        INVENTORY_ITEM_READ,
        INVENTORY_ITEM_MANAGE,
        INVENTORY_MOVEMENT_READ,
        INVENTORY_MOVEMENT_RECORD,
        INVENTORY_MOVEMENT_ADJUST,
    ],
    "Auditor / Viewer": [
        STATION_READ,
        USER_READ,
        AUDIT_READ,
        ROLE_READ,
        ORGANIZATION_READ,
        FUEL_GRADE_READ,
        SUPPLIER_READ,
        TANK_READ,
        DISPENSER_READ,
        NOZZLE_READ,
        FUEL_PRICE_READ,
        FUEL_RECEIPT_READ,
        SHIFT_READ,
        PAYMENT_METHOD_READ,
        CREDIT_CUSTOMER_READ,
        SUPPLIER_LEDGER_READ,
        CREDIT_COLLECTION_READ,
        EXPENSE_READ,
        INVENTORY_ITEM_READ,
        INVENTORY_MOVEMENT_READ,
        REPORT_READ,
    ],
}
