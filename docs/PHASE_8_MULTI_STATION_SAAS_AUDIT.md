# Phase 8 Audit — Multi-Station-Per-Organization Architecture

Scope: confirm the existing architecture already supports one organization operating multiple stations as a single tenant (not multiple tenants), identify what's genuinely missing against the brief's dashboard/data-integrity requirements, and propose the smallest safe plan. **No code has been changed for this audit.**

## Headline finding

**The core architecture already is this.** `organization_id` has always been the tenant boundary; `station_id` has always been a child of exactly one organization, never a tenant boundary of its own. Every business table (`Shift`, `Expense`, `AttendanceRecord`, `PayrollRule`, `SalaryRecord`, `TankerReceipt`, `InventoryMovement`, …) carries both `organization_id` and `station_id` directly, an organization already supports an unlimited number of stations today, and `UserStationRole.station_id IS NULL` (org-wide) vs. a specific station is the exact mechanism the brief describes for "organization-level and station-level permissions." This was built from Phase A/B onward and re-verified, not newly discovered. What's missing is almost entirely on the **reporting/dashboard side** — aggregating across stations — plus a couple of real gaps in enforcement and UI discoverability.

## 1. Existing multi-organization and multi-station capabilities

| Capability | Status | Where |
|---|---|---|
| One organization, many stations, each a plain FK child (never a tenant boundary) | ✅ Built | `Station.organization_id`, every business table |
| Add a station to an existing org without creating a new org | ✅ Built | `POST /organizations/{id}/stations`, `frontend/app/dashboard/org/[orgId]/stations/page.tsx` |
| Org-wide role vs. station-scoped role (the permission-configurability requirement) | ✅ Built | `UserStationRole.station_id` nullable; `user_has_permission`/`get_station_visibility_scope`/`actor_can_grant_scope` (`app/core/permissions.py`) |
| A station-scoped role cannot read/write another station's records | ✅ Built & tested | `require_permission`'s station_id match; `role-permissions.spec.ts`, `test_rbac.py`, `daily-entry-roles.spec.ts`'s cross-station/cross-tenant tests |
| Station creation/update validated against the right organization (no cross-org station reference possible) | ✅ Built | `get_station_or_404` (33 call sites) scopes every lookup by `(station_id, organization_id)` together |
| Org-wide aggregate counts for approvals/exceptions, correctly scoped to the caller's visible stations | ✅ Built | `GET /organizations/{id}/reports/pending-approvals`, `get_station_visibility_scope` |
| Org-wide audit log, correctly station-filtered for a station-scoped viewer | ✅ Built | `GET /organizations/{id}/audit-log` |
| Staff list with a station filter | ✅ Built | `frontend/app/dashboard/org/[orgId]/staff/page.tsx` |
| Platform Super Admin's own org-wide (cross-tenant) management, with Phase 5b's read-only support-session gate | ✅ Built | `app/api/platform.py`, `app/core/support_sessions.py` |
| Historical records, append-only ledgers, audit trail | ✅ Built | `StockLedgerEntry`, `InventoryMovement`, `AuditLog` — none of this phase's work touches them |

## 2. Missing functionality

1. **No consolidated company-wide sales/revenue/stock dashboard.** `/dashboard/org/{orgId}` (the existing "org dashboard") covers pending approvals, supplier balances, credit balances, expenses, and audit — never fuel sales, revenue, or stock totals. Every revenue/stock/reconciliation report (`daily-fuel-sales`, `tank-variance`, `shift-reconciliation`, `expense-summary`, `inventory-stock`, `price-change-history`) is mounted at `/organizations/{id}/stations/{id}/reports/...` — **one station at a time**, with no organization-wide rollup version of any of them.
2. **No station-wise performance comparison view.** Nothing lets an owner see "Lahore vs. Gujranwala vs. Sheikhupura" side by side for any metric — not in the backend (no endpoint returns per-station rows for a metric across stations) nor the frontend.
3. **No persistent station switcher.** There is no "you are viewing: Lahore Station ▾" control anywhere in the shell. Switching stations today means navigating to the full `/stations` list page and clicking a row — workable, but not what "clear station selector" asks for.
4. **No combined attendance/employee overview across stations.** Attendance is entirely mounted under `/organizations/{id}/stations/{id}/attendance` — no org-wide view of who's present/absent today across every station.
5. **No enforcement of a subscription plan's `max_stations`/`max_users`.** Both fields already exist on `Plan` and are populated at onboarding, but nothing reads them — `create_station` and `create_user` never check the organization's active subscription's limits. An organization on a 1-station plan can create unlimited stations today.

## 3. Database relationship gaps

**None found that need a migration.** Every station-owned table already carries `organization_id` directly (not just reachable via a join through `station_id`), and every write path validates `station.organization_id == organization_id` via `get_station_or_404` before using it. There is no table where a station could be silently misattributed to the wrong organization, and no station can exist without an organization. This requirement is already fully satisfied by the existing schema — the gap list above is entirely about missing queries/endpoints/UI, not missing columns or constraints.

## 4. Authorization and data-isolation risks

1. **Already covered, re-verified, not a gap**: cross-station and cross-organization isolation for a real (non-superuser) role — confirmed by existing passing tests (`role-permissions.spec.ts`, `daily-entry-roles.spec.ts`, `test_rbac.py`) and unaffected by anything in this audit.
2. **One real, pre-existing inconsistency, surfaced by this audit**: `frontend/lib/permissions.ts`'s `can()` still returns `true` unconditionally for `is_superuser`, documented as deliberately mirroring the backend's old boundary ("a superuser bypasses every check, matching the backend's own `require_permission`"). Since Phase 5b, that's no longer true on the backend — a bare superuser with no active support session is now denied almost everywhere `can()` would still show a button or nav item as available. This is a UI-only inconsistency (the backend remains the real, correctly-enforced boundary — nothing here is an actual data leak), but a platform admin without an active session would see controls that then 403 when used. Worth fixing opportunistically whenever this hook is next touched; not a reason to block this phase.
3. No new risk is introduced by the "missing functionality" items above, provided any new org-wide report strictly reuses the existing station-visibility-scoping pattern (`get_station_visibility_scope`/the Phase 5b support-session equivalent) rather than a new, parallel one.

## 5. Dashboard gaps

Directly follows from §2: company-wide sales/revenue/expenses/stock overview, station-wise comparison, and combined attendance are the three concrete dashboard gaps. The individual station dashboard, station-specific shifts/inventory/tanks/nozzles/transactions/attendance, and "add/manage stations without a new organization" are all already built and don't need touching.

## 6. Required implementation phases (proposed, smallest-safe)

**Phase 8a — Plan limit enforcement (small, backend-only).**
Check the organization's active subscription's `max_stations`/`max_users` in `create_station`/`create_user`, returning a clear 409 when exceeded. No migration. Minutes of risk, closes a real gap (§2.5).

**Phase 8b — Organization-wide consolidated reports (the bulk of the work).**
New `org_router`-mounted endpoints (`/organizations/{id}/reports/...`) that aggregate the existing per-station figures across every station the caller can see — reusing `compute_expected_fuel_revenue`/`get_book_stock`/existing report queries per station and summing, not a new calculation engine. Candidates, in order of value: a company-wide sales/revenue/stock summary; a station-comparison table (one row per station, the same metrics side by side); a combined attendance-today view. Every new endpoint must resolve its visible-station set the same way `pending-approvals` already does (or the Phase 5b support-session equivalent for a superuser) — no new scoping logic.

**Phase 8c — Frontend: consolidated dashboard tab + station switcher.**
A new tab (or new top-level page) on the org dashboard rendering 8b's data; a persistent station-switcher control (sidebar or header) that lists the caller's visible stations and lets them jump between a station's dashboard and the org-wide one, replacing the current "go to the Stations list page" flow. No change to the login page or any existing page's URL structure.

**Not in scope for this phase** (per the brief's own rules): no AI, no new paid services, no hardware integration, no database-architecture change, no login-page change.

## 7. Tests needed

- Backend: each new org-wide report endpoint gets the same test shape `pending-approvals` already has — org-wide role sees every station's figures, a station-scoped role sees only its own, a cross-org caller is rejected, figures match the sum of calling each station's existing single-station endpoint individually (the aggregation must never invent a number the per-station endpoint doesn't already produce).
- Backend: plan-limit enforcement — creating a station/user at the limit succeeds, one past it is rejected (409), an organization with no subscription at all is not blocked (don't break every existing org that predates subscriptions).
- Frontend/Playwright: the station switcher changes the active station and the nav updates accordingly; the consolidated dashboard tab shows real aggregated figures matching a manual sum of the seeded stations' individual numbers (same pattern as the existing dashboard.spec.ts assertions).
- Regression: full existing backend + Playwright suites, unchanged in count or intent, must still pass — this phase only adds endpoints/pages, it doesn't touch an existing one.

## Proposed next step

Implement Phase 8a (plan-limit enforcement) and Phase 8b/8c (consolidated reporting + station switcher) as one coherent increment, following the same discipline as every prior phase: migration-free where possible, full regression before and after, production verification after deploy. Awaiting approval before writing any code.
