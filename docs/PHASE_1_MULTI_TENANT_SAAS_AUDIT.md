# Phase 1 — Multi-Tenant SaaS Audit (Existing Codebase vs. the Master Brief)

**Date:** 2026-11-17
**Method:** Read-only review of the actual code (models, API routers, migrations, frontend routes, tests) — nothing in this document is assumed from the brief's wording. Builds on `docs/SAAS_GAP_ANALYSIS.md` (2026-11-01), which already audited the platform/subscription layer; this document extends that into the specific asks of the new brief (database-per-tenant, attendance hardware, payroll policy engine) rather than repeating it.

**No code was changed to produce this document**, per the brief's own instruction to audit before implementing.

---

## 1. What "multi-tenant" means in this codebase today

**This is a single shared database, not database-per-tenant.** One Postgres database, one SQLAlchemy `engine` created once at startup (`backend/app/database.py`), one `DATABASE_URL`. Every tenant's rows live in the same tables, distinguished by an `organization_id` (and usually `station_id`) foreign key column.

**Tenant isolation is real and already tested**, just not at the database level:
- Every mutating and almost every read endpoint resolves `organization_id`/`station_id` from the **URL path only**, never the request body, through the shared `require_permission` dependency (`app/api/deps.py`).
- `backend/tests/test_cross_tenant_isolation.py` and this session's own Playwright suite (`role-permissions.spec.ts`, `daily-entry-roles.spec.ts`) both exercise real cross-tenant rejection — not a superuser shortcut, a real role-scoped token trying to read another organization's data and getting rejected.
- This is the hardest part of multi-tenancy to get right, and it already works. **The brief's Section 14 "test malicious scenarios" list is already substantially covered by existing, passing tests** — re-verified in Section 8 below.

**What does NOT exist today:** any concept of a tenant having its *own database*. `Organization` is a row, not a database. `User.is_superuser` is a boolean on the same `users` table every tenant's staff sit in — a platform admin and a petrol-pump cashier are rows in the same table, distinguished by a flag, not by which database they're connecting to.

---

## 2. The central/control-plane concept — partially built already

Per `docs/SAAS_GAP_ANALYSIS.md` (2026-11-01 pass), a *logical* platform layer already exists, inside the same database:

| Brief's ask | Current reality |
|---|---|
| Tenant registry | `organizations` table — name, `is_active`, created_at. No status enum (pending/active/suspended/deactivated), no DB connection reference, no provisioning status. |
| Subscription plan metadata | `plans`, `subscriptions`, `subscription_payments` tables — real, migrated, tested (`test_subscriptions.py`, 6 tests). Manual payment recording only, no gateway. |
| Platform-level audit | Same `audit_logs` table as everything else, filterable by a superuser. No separate platform-only audit store. |
| Super Admin dashboard | `/dashboard/platform` page exists — Plans management + organizations/subscriptions list. This is a fraction of Section 4's ask (no tenant provisioning monitor, no database-health view, no platform user management, no tenant creation workflow with owner invite). |
| Platform roles (Super Admin vs. Support Admin) | Does not exist. Only `is_superuser: bool`. No granular platform-level role system. |

---

## 3. Database-per-tenant — the critical feasibility question (read before Phase 2)

The brief asks for one isolated Postgres database per petrol pump, provisioned automatically when Super Admin creates a tenant. Before touching any code, here is what that actually requires against **this project's real, current hosting** — not a hypothetical:

**What's live right now:** one Neon Postgres project (free tier), one connection string, holding the single shared database described above. This is what `docs/PRODUCTION_RUNBOOK.md` documents as the live deployment.

**What automated provisioning would need:**
1. **A Neon API key**, not just a database connection string. Creating a *new* database/branch/project programmatically is a Neon **management-API** operation — the connection string this session has only lets us read/write rows inside the one existing database, not create new ones. **This session does not hold a Neon API key.** Without it, "Super Admin clicks Create Tenant → a new database is provisioned" cannot be automated today; it would require either (a) the owner obtaining and supplying a Neon API key, or (b) a manual database-creation step per tenant, which is not what the brief is asking for.
2. **Neon's free-tier limits**, researched and documented in `docs/PHASE_7_FREE_HOSTING_COMPARISON.md`: 100 projects, 1 GB storage **per project**, 100 CU-hours **per project**, shared across the whole account. Mapping one tenant to one Neon project is *structurally possible* on paper (up to 100 tenants), but every tenant's compute and storage draws from the same account-wide free allowance in practice, and this was never verified against real concurrent multi-tenant load.
3. **Per-tenant connection pooling.** `backend/app/database.py` creates one engine, one pool, at process start. N tenant databases means either N separate engines/pools held in memory simultaneously (real memory/connection-count cost on a free-tier single instance — the same single-instance constraint already documented in `docs/REMAINING_RISKS.md` item 2) or a connect-per-request pattern that defeats pooling entirely.
4. **Per-tenant migrations.** `alembic upgrade head` currently runs once, against one database, automatically on container boot (`docker-entrypoint.sh`). With N tenant databases, every schema change means running Alembic N times, and a failure partway through leaves tenants on different schema versions — a real operational hazard the brief itself calls out in Section 3.

**Bottom line, stated plainly rather than hedged:** database-per-tenant is *buildable* within the free-tier constraint (Neon's project limit allows it numerically), but it trades a security property this codebase already has (proven row-level isolation) for a new, real operational burden (N migrations, N pools, N backup targets) — and the one piece that makes it *automatic* rather than manual (programmatic provisioning) needs a credential this session doesn't have. **This is a decision for the owner, not something to default into silently** — see the question at the end of this document.

---

## 4. Attendance — what's real vs. what the brief assumes

**Backend model** (`backend/app/models/attendance.py`) is real and migrated: `AttendanceRecord` (status, check-in/out time, source, notes), `PayrollRule` (per-station, shift start time, late/half-day thresholds in *minutes*, but deduction *amounts* are flat), `SalaryRecord` (days present/absent/late/half-day/leave, base salary, deductions, net salary, finalization flag).

**What the data model has that the logic doesn't use yet:**
- `PayrollRule.late_threshold_minutes` and `half_day_threshold_minutes` exist as columns, but `generate_salary()` (`app/api/attendance.py`) **never computes actual late minutes from `check_in_time` vs. `shift_start_time`** — it only counts how many days already carry the string status `"late"`. That status is supplied by whoever calls `POST /attendance` (a human decides "late" today), not derived from the punch time. The brief's Section 9 example ("check-in 09:25, grace 10 min → 15 deductible minutes") **is not implemented** — the fields exist, the arithmetic doesn't.
- Deductions are flat amounts per occurrence (`late_deduction_amount × days_late`), not the configurable per-minute / per-occurrence-after-N policies the brief describes. This is a real gap, not a documentation gap.

**Frontend:** one page exists (`frontend/app/dashboard/org/[orgId]/station/[stationId]/attendance/page.tsx`) — manual present/absent/late marking, per `docs/STAFF_GUIDE.md` Section (attendance). **No payroll frontend exists at all** — confirmed absent in `docs/PHASE_7_INITIAL_AUDIT.md` and still true; `generate_salary`/`list_salary_records`/`finalize_salary` are callable only via direct API today.

**Hardware integration: zero.** A full-repository search for device/biometric/vendor-adapter code (ZKTeco or otherwise) found nothing — no adapter interface, no device model, no event receiver, no webhook endpoint. `AttendanceRecord.source` is a free-text string defaulting to `"manual"`, which is the *only* hook that exists today for a future non-manual source — everything in the brief's Section 7 (provider/adapter architecture, device registry, event normalization, deduplication, replay protection) would be built from nothing, not extended from something partial.

---

## 5. Roles — current reality vs. the brief's two-tier ask

Current roles (`backend/app/core/permission_codes.py`, 7 roles, 56 permissions, unchanged since Phase 6): **Owner, Station Manager, Shift Supervisor, Cashier/Operator, Accountant, Storekeeper/Technician, Auditor/Viewer.** Owner holds every permission; the rest are deliberately scoped subsets — see `docs/PHASE_7_CLIENT_USER_GUIDE.md` Section 4 for the full capability table.

This already matches most of the brief's "Tenant Roles" list conceptually (Manager → Station Manager, Fuel Operator → Cashier/Operator, HR/Attendance Manager → closest existing is Accountant, who already holds `attendance:read`/`payroll:manage`). **What's missing:** a distinct "Attendance/HR Manager" role separate from Accountant, and — as above — any **platform-level** role distinct from the single `is_superuser` boolean.

---

## 6. Frontend routes — what exists, what Section 11 asks for

Already built and redesigned this engagement (Phases 3–7, most recently the dashboard/reports reorganization): Dashboard (Today's Overview), Daily Entry, Fuel Stock/Reports (4 tabs, each now with KPI strip + graph), Purchases, Credit Customers, Attendance (manual), Reading Corrections, Station Settings, Org Settings (Users, Billing, Payment Methods, Expense Categories), Platform Admin (Plans + Orgs list), Audit History, Approvals.

**Does not exist:** a dedicated Super Admin *section* with its own navigation shell (today's `/dashboard/platform` is one page, not a navigation context); Tenant Management (create/suspend/reactivate/provisioning-status/database-health screens); Payroll frontend (any of it); Device Management screen; a visually distinct "which petrol pump / which account" context switcher the brief's Section 11 asks for (today there's no ambiguity because there's one DB, but the brief's multi-database vision would need this).

**Login page:** unchanged in this audit, as instructed.

---

## 7. Business-rule invariants — re-verified, not re-litigated

The brief re-states a long list of existing rules (Decimal-only money/litres, append-only stock ledger, effective-dated prices, the 24-hour reading-correction lock, station/tenant scoping). All of these were already built and are already covered by passing tests from earlier phases — nothing in this audit found a violation. The 24-hour correction policy specifically (`backend/app/models/reading_correction.py`, `CORRECTION_WINDOW_HOURS = 24`) is unchanged and was not touched by this audit, per the brief's own non-negotiable rule.

---

## 8. Security scenarios from Section 14 — already tested vs. net-new

| Scenario | Status |
|---|---|
| Tenant A reads Tenant B's data | **Already tested and passing** (`test_cross_tenant_isolation.py`, `role-permissions.spec.ts`) |
| Tenant A changes an ID in a request to reach another org | **Already tested** — `require_permission` resolves IDs from the URL only |
| Tenant user tries to create a platform admin | **Partially covered** — no endpoint lets a tenant user set `is_superuser`; not explicitly regression-tested as its own case |
| Manager attempts an owner-only action | **Already tested** (`role-permissions.spec.ts` partial-access tests) |
| Suspended tenant calls the API | **Not enforced today** — `Organization.is_active = false` exists as a column but nothing checks it on every request; a "suspended" org can still transact. Real gap. |
| Invalid device submits attendance | **N/A — no device ingestion exists yet** |
| Duplicate hardware events replayed | **N/A — no device ingestion exists yet** |
| One tenant exports another's payroll | **No payroll export exists yet to test** |

---

## 9. Test baseline (unchanged by this audit)

Backend: 259 passing. Playwright: 32 passing. Both re-confirmed working as of the last deploy (`docs/PRODUCTION_RUNBOOK.md`). This audit changed no code, so this baseline stands as the starting point for Phase 2 onward.

---

## 10. Recommended phasing adjustment

The brief's Section 16 phase list is reasonable, with one structural fork to resolve before Phase 2 can start honestly: **Section 3 above**. Two real paths forward:

**Option A — Database-per-tenant, as literally specified.** Requires the owner to obtain a Neon API key (or equivalent management credential) for automated provisioning, accepts the new operational burden in Section 3 (N pools, N migrations, N backups), and is the architecture the brief's wording assumes throughout Sections 4–7.

**Option B — Strengthen the existing shared-schema multi-tenancy instead.** Keep one database (what's actually running in production today), close the real gaps found in this audit (suspended-org enforcement, platform role granularity, a proper Tenant Management UI operating on `organization_id` rather than a separate connection), and get the same *user-facing* outcome (Super Admin manages tenants, each tenant is fully isolated, provisioning is instant with no new database to create) without the new operational risk or the missing API credential. This is what the already-proven isolation tests in Section 8 are built on.

**This document does not choose between them.** That is the owner's call, consistent with the brief's own "do not blindly rewrite" instruction — recorded here as the one open question blocking Phase 2.
