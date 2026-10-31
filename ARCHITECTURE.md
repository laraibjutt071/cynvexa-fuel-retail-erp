# CYNVEXA Fuel Retail ERP — Architecture

## 1. Status of the repository

This project started from an empty directory. There is no prior codebase to preserve. This document and `docs/IMPLEMENTATION_PLAN.md` are the baseline going forward — update them as scope is confirmed with the owner, not just when code changes.

## 2. Source of truth

`docs/blueprint/CYNVEXA_Fuel_Retail_Petrol_Pump_ERP_Discovery_Product_Blueprint.docx` (copied into the repo for traceability) is the discovery document that drives scope, terminology and MVP boundaries. It is explicitly an **owner-review discovery document**, not a frozen spec: it contains several "CRITICAL OWNER DECISION" and "COMPLIANCE CAUTION" markers for business rules that are not yet resolved (e.g. which quantity is the authoritative payable quantity on a tanker receipt; tax/accounting treatment; whether density/temperature/water-level matters per station).

`docs/ASSUMPTIONS.md` records every such open point, the configurable default implemented so development can proceed, and the decision owner (station owner or accountant) who must confirm or override it. No business rule from the blueprint is silently hardened into an unconditional rule — each is a per-station configuration with a safe default.

## 3. Technology

| Layer | Choice | Why |
|---|---|---|
| Frontend | Next.js (App Router) + React + TypeScript + Tailwind + shadcn/ui | Matches the requested stack; server components for data-heavy screens, client components for shift/reconciliation entry forms. |
| Backend | Python + FastAPI + Pydantic v2 + SQLAlchemy 2.0 (async) + Alembic | Typed request/response boundary, async DB access, explicit migrations. |
| Database | PostgreSQL | Transactional integrity for financial/stock ledgers, `NUMERIC` for money/litres, row-level constraints. |
| Auth | Password hashing (argon2) + short-lived JWT access token + rotating refresh token in an HttpOnly, Secure, SameSite cookie | No long-lived tokens in browser storage; CSRF mitigated by SameSite + double-submit header on state-changing requests. |
| Testing | Pytest (backend, unit + API), Vitest/RTL (frontend unit — later phase), Playwright (critical end-to-end flows — later phase) | Backend calculations and permissions are the highest-risk surface and are tested first. |
| Deployment | Docker images for `backend` and `frontend`, docker-compose for local dev, environment-based config (`.env` per environment, never committed), managed Postgres in staging/production | Matches "cloud readiness" requirements; no secrets in frontend bundles or git history. |

## 4. Repository layout

```
/
├── ARCHITECTURE.md
├── docs/
│   ├── IMPLEMENTATION_PLAN.md
│   ├── ASSUMPTIONS.md
│   └── blueprint/
│       └── CYNVEXA_Fuel_Retail_Petrol_Pump_ERP_Discovery_Product_Blueprint.docx
├── docker-compose.yml
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app factory, middleware, routers, exception handlers
│   │   ├── config.py                # Pydantic settings, env-based
│   │   ├── database.py              # async engine/session, connection pooling
│   │   ├── models/                  # SQLAlchemy ORM models (one module per aggregate)
│   │   ├── schemas/                 # Pydantic request/response models
│   │   ├── api/                      # FastAPI routers, one module per resource
│   │   │   └── deps.py               # shared dependencies: current_user, db session, org/station scoping
│   │   ├── core/
│   │   │   ├── security.py          # password hashing, JWT issue/verify
│   │   │   ├── permissions.py       # role → permission map, require_permission() dependency
│   │   │   └── audit.py             # audit log writer used by mutating endpoints
│   │   └── exceptions.py            # typed domain exceptions → safe HTTP responses
│   ├── alembic/                     # migrations (one per schema change, never edited after merge)
│   ├── tests/                       # pytest, mirrors app/ structure
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── .env.example
└── frontend/
    ├── app/                          # Next.js App Router
    ├── components/
    ├── lib/                          # API client, auth context
    ├── package.json
    ├── Dockerfile
    └── .env.example
```

Each later phase adds model/schema/api/test modules under this same structure — it does not introduce a second structure.

## 5. Database entity plan (full MVP target; built up phase by phase)

**Phase A (this phase):**
`Organization`, `Station`, `User`, `Role`, `Permission`, `UserStationRole` (a user's role is scoped to an organization and, optionally, a specific station — this is the access-isolation boundary), `AuditLog`.

**Phase B — Fuel operations (implemented):**
`FuelGrade`, `Tank`, `Dispenser`, `Nozzle`, `FuelPrice` (effective-dated, never overwritten), `Supplier`, `TankerReceipt` (captures document/declared/accepted/payable quantity as distinct fields per the blueprint's Section 4 distinction), `StockLedgerEntry` (append-only; book stock is a computed projection over this ledger, never a mutable column), `Attachment` (evidence, pulled forward from Phase E - see Phase E note below). `FuelPurchaseOrder` and `StockVarianceInvestigation` were scoped out of this pass (see `docs/IMPLEMENTATION_PLAN.md`'s Phase B record) and remain future work.

**Phase C — Shift operations (implemented):**
`Shift` (strict one-way state machine: `open` → `closed` → `approved`, no reopen path yet - see `docs/ASSUMPTIONS.md` #7/#18), `ShiftTankReading` (opening/closing physical dip - the "physical stock observation" this blueprint section calls for), `ShiftNozzleReading` (opening/closing totalizer, with meter replacement/reset/rollover fields and their own approval gate), `ShiftExceptionalEvent` (test draws/calibration, posted to the ledger as `StockMovementType.TEST_CALIBRATION`, kept separate from `SALE`), `ShiftPriceChange` + `ShiftPriceChangeReading` (mid-shift price-period boundary reading - capture only; splitting revenue by price period is Phase D's job once revenue exists). Stock variance reporting is a live-computed view (`GET .../shifts/{id}/variance`), not a stored entity - see §6 below.

**Phase D — Financial reconciliation (implemented):**
`PaymentMethod` (org-configurable catalogue, each tagged with a `category` - cash/card/digital/credit - that drives the math), `CreditCustomer` (minimal stub, see Phase E note), `ShiftTender` (one amount through one method, reversible), `ShiftCashMovement` (opening cash/expense/deposit/safe-transfer/refund, each decreasing type approval-gated, reversible), `ShiftReconciliation` (one per shift: expected fuel revenue, total tender, expected vs. actual physical cash, both variances and their tolerance flags - see §6), `ShiftReconciliationAmendment` (the approved-correction mechanism for an already-finalized `ShiftReconciliation`). `expected_fuel_revenue` is computed (`app/core/revenue.py`), not stored redundantly anywhere else, directly from `ShiftNozzleReading` + the Phase C `ShiftPriceChange`/`ShiftPriceChangeReading` boundary data - this is where the price-period revenue split deferred in Phase C actually happens.

**Phase E/F — Supporting operations and the owner dashboard (implemented together as "Phase 6"):**
`SupplierInvoice` + `SupplierPayment` (a supplier's balance is invoiced minus *approved* payments - `app/core/supplier_ledger.py`; the invoice amount is recorded directly, never derived from a purchase price this system has never captured, see `docs/ASSUMPTIONS.md` #26), `CreditCustomerPayment` (a credit customer's balance is their non-reversed `ShiftTender` credit sales minus non-reversed collections - `app/core/credit_ledger.py`, reading `ShiftTender` directly rather than duplicating the receivable into a second ledger), `Expense` (general, non-shift business expenses with their own record/approve/reject/reverse workflow - distinct from a shift's own `ShiftCashMovement(EXPENSE)`), `InventoryItem` + `InventoryMovement` (shop/lubricant stock - the same append-only-ledger pattern as `StockLedgerEntry`, see `app/core/inventory.py::get_inventory_stock`). The dashboard itself (daily fuel sales/litres, tank book-vs-physical variance, shift & cash reconciliation, pending approvals/exceptions, supplier/customer balances, audit history, CSV exports) is read-only reporting over these and every earlier phase's tables - see `app/api/reports.py` and `app/api/audit.py` - never a separate store of its own numbers. `CreditCustomerVehicle` and full credit-limit/ageing/statement features remain unbuilt (`docs/ASSUMPTIONS.md` #22/#24); inventory valuation (COGS/margin) is not computed (#28).

All money and litre columns use `NUMERIC` (never `FLOAT`/`DOUBLE`), with an explicit scale/rounding rule documented per field.

## 6. Critical business rules carried into design now

- **Book stock is a ledger, not a column.** `StockLedgerEntry` rows are append-only; `app/core/stock.py::get_book_stock` is the one function that may compute it, as `SUM(increasing) − SUM(decreasing)`, optionally as of a point in time. A physical dip/ATG reading is stored as its own fact (`ShiftTankReading`, `TankerReceipt.pre/post_receipt_tank_reading`) and never overwrites the ledger — variance is `physical − book`, always visible (`GET .../shifts/{id}/variance`), never auto-corrected.
- **Approved records are immutable - except through an approved amendment or a reversal, never a silent edit.** `TankerReceipt` and `Shift` are strict state machines with no edit path out of a terminal state (every mutating endpoint locks its row with `SELECT ... FOR UPDATE` and checks status first, so a duplicate approve/reject/close is rejected (409), never double-applied). `ShiftReconciliation` goes one step further and actually implements the correction path ARCHITECTURE.md always called for: a `ShiftReconciliationAmendment` captures before/after/reason/requester/approver and, once approved, is the only way `actual_physical_cash`/`explanation` on an already-approved reconciliation ever change - the original value is preserved on the amendment row forever, and prior authorization is left untouched rather than silently invalidated. `ShiftTender`/`ShiftCashMovement` support a simpler reversal (exclude-from-totals + who/when/why), allowed even after the shift is approved. The same pattern has not yet been extended to `Shift`'s own readings or to `TankerReceipt` - still an open gap, narrower than before (`docs/ASSUMPTIONS.md` #18).
- **Gross dispensed quantity** = closing totalizer − opening totalizer, rejected (422) if negative - *unless* a flagged, explicitly-approved meter replacement/reset/rollover event justifies the discontinuity, in which case dispensed is the sum of the two bounded segments either side of the event (`ShiftNozzleReading.meter_event_*` fields; see its model docstring). The flagged event itself must be separately approved before the shift can be approved.
- **Revenue allocation across a mid-shift price change is computed, not just captured.** `app/core/revenue.py::compute_expected_fuel_revenue` walks each nozzle's dispensed litres through its shift's `ShiftPriceChange` boundary readings (Phase C), splitting into segments priced at the rate effective in each segment, and sums - rounding the final total once (round-half-up to 2dp; see `docs/ASSUMPTIONS.md` #20 for why that specific choice is still open). A price change with no boundary reading for a given nozzle simply can't be placed on that nozzle's timeline and is skipped for it - a data gap, not silently smoothed over.
- **Reconciliation never edits fuel quantities to absorb a cash shortage, and never confuses a deposit with revenue.** `expected_fuel_revenue` is computed purely from litres × price; `ShiftCashMovement` (opening cash, expenses, deposits, transfers, refunds) is never read by that calculation at all. A cash shortage and a revenue variance are two independently-computed, independently-tolerance-checked numbers on `ShiftReconciliation`, verified not to interact by direct test (`test_deposit_reduces_expected_cash_but_never_affects_revenue_variance`).
- **A material discrepancy requires an explanation and, separately, authorization from the right role.** "Material" means either tolerance (`Station.cash_variance_tolerance_amount`, an absolute figure; `Station.revenue_variance_tolerance_percent`) is breached. Creating the reconciliation without an explanation when material is rejected outright; a shift cannot reach final approval while `requires_authorization` is true and unauthorized. Per blueprint §12's literal "Accountant | Cash variance approval", only Accountant and Owner hold `shift_reconcile:approve` - not Station Manager or Shift Supervisor, even though those roles hold the equivalent approval permission everywhere else (`docs/ASSUMPTIONS.md` #23).
- **Insufficient capacity/stock is checked under a row lock, at the moment it matters, not just at submission time.** A tanker receipt's capacity is checked at creation (early feedback) **and** re-checked against the live ledger at approval (authoritative, tank row locked); a shift's dispensed total is checked against live book stock at approval the same way; an inventory movement that would take stock negative is rejected the same way (`app/api/inventory_movements.py`, under a row lock on the `InventoryItem`). Two concurrent approvals for the same tank or the same record cannot both pass against the same stale figure - verified with real concurrent-connection tests (`asyncio.gather` against separate DB sessions), not just by reading the code.
- **Every dashboard figure is derived from persisted records, never hardcoded.** The daily fuel sales report sums the stock ledger's own `SALE` postings and `compute_expected_fuel_revenue_by_grade`, both read-only projections over data already written by shift approval; the pending-approvals/exceptions view counts real unresolved rows (unapproved receipts, closed-but-unapproved shifts, unauthorized reconciliations, unapproved cash outflows and supplier payments, pending expenses, below-reorder-level inventory items) across whichever stations the caller can see, the same visibility scoping the audit log already uses. A `coalesce(sum(...), 0)` over zero rows is explicitly re-quantized to the column's own decimal scale (`app/core/stock.py`, `app/core/inventory.py`, `app/core/supplier_ledger.py`, `app/core/credit_ledger.py`) so a brand-new tank/item/supplier/customer reports "0.000"/"0.00" consistently rather than a differently-formatted bare "0" - a real inconsistency caught by an end-to-end UI test, not by reading the code.

## 7. Security boundaries established in Phase A

- Every authenticated request resolves to a `User` with one or more `UserStationRole` rows; every data-access query is filtered by the caller's organization (and station, where applicable) at the query layer, not just the UI — this is enforced in `api/deps.py`, not left to each router to remember.
- Passwords hashed with argon2id; no plaintext or reversible storage.
- JWT access tokens are short-lived (15 min default) and carry no authorization claims beyond user id — permissions are re-checked against the database on every request, so a revoked role takes effect immediately rather than waiting for token expiry.
- All mutating endpoints go through a single `require_permission(...)` dependency; there is no endpoint that infers permission from the frontend's behavior.
- All mutating endpoints write an `AuditLog` row (actor, action, entity, before/after where applicable, timestamp) inside the same DB transaction as the mutation — audit and mutation succeed or fail together.
- **Audit log visibility is station-scoped, not just organization-scoped.** `AuditLog.station_id` (nullable: null = an org-level event with no single station, e.g. an organization profile change) lets `GET /organizations/{id}/audit-log` restrict a station-scoped `AUDIT_READ` holder to their own station's events plus org-level ones, via `app/core/permissions.py::get_station_visibility_scope`. Without this, a station-scoped role (e.g. a per-station accountant) would see every other station's audit trail in the same org just because `AUDIT_READ` was checked at the organization level.
- **Password change invalidates every other session.** `PATCH /auth/password` revokes all of the user's refresh tokens on success - a credential rotation (because the old one leaked, or routine hygiene) must not leave a previously-issued session still usable. `POST /auth/logout-all` and `GET /auth/sessions` give the user the same control without changing their password.
- **Granting or revoking a `UserStationRole` cannot exceed the actor's own scope.** `require_permission` alone is not enough to guard `POST/DELETE .../users/{id}/roles`, because that check only resolves scope from the URL (organization-level), while the scope being *granted* comes from the request body. An actor whose own role is scoped to one station must not be able to grant (or revoke) an org-wide role, or a role at a different station, to someone else — that would be privilege escalation through a station-scoped delegate. This is enforced separately via `app/core/permissions.py::actor_can_grant_scope`, which is deliberately a different, stricter function from `user_has_permission` (see its docstring) rather than a parameter on the same function. Any new endpoint that lets one user change another user's access must use this, not `require_permission` alone — found and fixed during the Phase 1 QA pass (see `docs/IMPLEMENTATION_PLAN.md`).
