# Phase 4 — Tenant Owner Dashboard & Staff Management

**Date:** 2026-11-18
**Architecture:** shared-schema multi-tenancy, unchanged. No new permission codes, no change to Phase 2's suspension enforcement or Phase 3's platform-admin separation.

---

## 1. Audit — what already existed before this phase touched anything

Read in full before writing any code: `docs/PHASE_1_MULTI_TENANT_SAAS_AUDIT.md`, `docs/PHASE_3_SUPER_ADMIN_TENANT_MANAGEMENT_REPORT.md`, `app/api/users.py`, `app/api/stations.py`, `app/models/user.py`/`user_station_role.py`, and the existing `today/page.tsx` dashboard and `settings/page.tsx` staff UI.

**The owner dashboard (Section 1) was already ~90% built**, across Phases 4–7 of the earlier redesign work: today's fuel sales, litres sold, tank-wise stock, cash/card/digital/credit, expenses, cash variance, pending approvals, and operational alerts were all already real, database-backed, and organized into Overview/Operations/Analytics/Reference sections. **Genuinely missing:** current shift status, a recent-transactions list, and an attendance overview — added this phase (Section 3 below).

**Staff management (Section 2) existed only as a cramped card** inside Org Settings: list (name/email/active only), create-user form, and a separate role-assignment panel. **No search/filter, no deactivate control in the UI (the backend already supported `is_active` via `PATCH`, just nothing called it), no edit form, no employee profile fields at all** (no employee code, job title, or phone anywhere in the data model), and no dedicated employee-profile page.

**Role/permission infrastructure (Section 3) needed no changes** — the 7-role catalog, `require_permission`, and `actor_can_grant_scope` (station-scope grant restriction) were already correct and already tested (`tests/test_rbac.py`). This phase adds zero new permission codes, exactly as instructed.

**Station management (Section 4):** full CRUD (`POST`/`GET`/`PATCH /organizations/{id}/stations`) already existed with zero frontend gaps in the API — but **no station list page existed**; a station was only reachable by already being inside its own URL. Added this phase.

**A real, load-bearing discovery made while writing this phase's own tests:** `POST /organizations/{id}/users` creates a `User` row with **no role assignment** — and every other user-scoped endpoint (`GET`/`PATCH` on a single user, and the list endpoint itself) requires at least one `UserStationRole` row to even see that user. A newly created employee is invisible and inaccessible until a role is granted. This is correct tenant-scoping, not a bug, but it meant the old "Add user" form (create, then separately go find them and assign a role) left a user in a broken, half-visible state in between. **Fixed in the new "Add employee" flow** (Section 3 below), which creates the user and assigns their role/station in one guided action.

---

## 2. What was implemented

### Backend

**One additive migration (`e5f6g7h8i9j0`):** `employee_code`, `job_title`, `phone` added to `users` — nullable, no existing row touched. "Joining date" deliberately has **no new column** — `UserStationRole.created_at` (when a role was granted in this org) already answers it accurately, so nothing was invented for it.

**Schema changes:** `UserCreate`/`UserUpdate`/`UserRead` now carry the three new fields; `RoleAssignmentRead` now includes `created_at` (needed to show "joined" on the new profile page — it already existed on the row, just wasn't exposed).

**`GET /organizations/{id}/users` now takes `q` (name/email/employee-code search), `status` (`active`/`inactive`), and `station_id` filters** — the same pattern Phase 3 added to the organization list. `create_user` now accepts and persists the new profile fields. `update_user`'s audit-log before/after was generalized to reflect whichever fields actually changed (previously hardcoded to only `full_name`/`is_active`), a small correctness fix made while touching this function.

**No new endpoints were needed for stations** — the existing CRUD was already complete; only a frontend list view was missing.

### Frontend

All new tenant-side pages live inside the existing `AppShell` (unchanged, still fully separate from the Platform Admin shell Phase 3 built) — the owner never sees Super Admin navigation, and nothing here touches the login page.

| Route | What it does |
|---|---|
| `/dashboard/org/[orgId]/staff` | Employee list (`DataTable`, sortable), search, status filter, station filter, "Add employee" dialog that creates the user **and** assigns their first role/station in one action. |
| `/dashboard/org/[orgId]/staff/[userId]` | Employee profile — contact info, employee code, job designation (editable), all role/station assignments with join dates, assign/revoke roles, and Activate/Deactivate behind a `ConfirmDialog`. |
| `/dashboard/org/[orgId]/stations` | Station list (`DataTable`) with an "Add station" dialog reusing the existing station-creation endpoint. |

**Dashboard additions** (`today/page.tsx`, in the existing Operations section): **Current shift status** (real open shifts from `GET .../shifts?status=open`), **Attendance today** (present/late/absent/on-leave counts from today's real attendance records — the card simply doesn't render if the viewer lacks `attendance:read`, no error shown), **Recent transactions** (the day's real tenders, already-fetched data, now also shown as a timestamped list, not just aggregated into totals).

**Navigation:** `Staff` and `Stations` links added to `AppShell`'s sidebar, permission-gated (`user:read` / `station:read`) exactly like every other nav item.

**The old bare `/dashboard` route was audited, not changed.** It already auto-redirects a single-org/single-station owner straight to `/today`, and shows a picker only when there's a real choice to make (multiple orgs/stations) — a genuinely different purpose from the new Staff/Stations pages, not a duplicate. Left as-is per the brief's own "implement a redirect only after checking all dependencies" instruction; changing it wasn't warranted.

---

## 3. Permission changes

None. Every new/changed endpoint uses `USER_READ`/`USER_CREATE`/`USER_UPDATE`/`USER_ASSIGN_ROLE`/`STATION_READ`/`STATION_CREATE` — all pre-existing codes, already held by the correct roles in the existing seed. No second permission system was created.

---

## 4. Database changes

One migration (`e5f6g7h8i9j0`): `users.employee_code`, `users.job_title`, `users.phone` — all nullable, additive. No existing table structurally changed, no data migration needed, fully reversible.

---

## 5. Security testing — Section 7 of the brief

| Scenario | How it's proven |
|---|---|
| Tenant A cannot read Tenant B | Pre-existing `test_cross_tenant_isolation.py`, re-run and passing — untouched |
| Tenant A cannot edit Tenant B | Same suite, PATCH-side cases, untouched |
| Owner cannot create platform administrators | `test_owner_cannot_create_platform_administrator_via_staff_creation` (new this phase, via the actual Staff creation path specifically, not just the generic Phase 3 case) |
| Manager cannot perform owner-only operations | Pre-existing `test_rbac.py` scope tests, re-run and passing |
| Cashier cannot access financial management without permission | Pre-existing `role-permissions.spec.ts` Playwright suite, re-run and passing |
| Suspended organization remains blocked | Phase 2's tests, re-run and passing — untouched |
| Inactive users cannot continue accessing protected APIs | **New, real, end-to-end test** (`test_deactivated_employee_cannot_access_protected_apis`): a real staff member's token works, gets deactivated through the actual `PATCH` endpoint, and the *same already-issued token* is then rejected with 401 on the next real API call |
| Station assignments are enforced | Pre-existing `test_rbac.py` (`test_cashier_scoped_to_one_station_cannot_read_a_different_station`), re-run and passing; new `test_filter_users_by_station` confirms the new station filter itself respects org-wide vs. station-scoped assignment correctly |

No existing test was weakened or deleted to make this phase pass.

---

## 6. Test results

**Backend:** 271 pre-existing + 7 new (`test_staff_management.py`) = 278, run against the dedicated `cynvexa_test` database (never the dev or production database), all passing.

**Frontend:** `tsc`/production build clean; all new routes (`/staff`, `/staff/[userId]`, `/stations`) present in the build output. Full Playwright suite: 32/32 passing, confirming no regression to any existing tenant workflow.

**Manual verification:** real browser screenshots of the Staff list (search/filter working against real seeded users), the Add Employee dialog, the Stations list (all 3 real seeded stations), and the redesigned dashboard showing all three new widgets with real data (an empty "no shift open" / "no attendance yet" state, correctly rendered, and a real recent-transaction entry).

---

## 7. Known limitations

- **Attendance records today are still created manually** (no hardware integration — unchanged from Phase 1's finding, and explicitly out of scope for this phase per the brief).
- The new "Attendance today" dashboard widget only appears for a viewer who holds `attendance:read` — this is correct, permission-respecting behavior, not a bug, but it means an Owner without that specific permission combination assigned to themselves wouldn't see it (Owners hold every permission by default, so this only matters for a custom role).
- Employee code/job title have no uniqueness constraint — two employees can share the same code today. This was a deliberate choice (see Section 4 of this report and the migration's own docstring): codes are free-text HR labels here, not a system identifier anything else depends on.
- No employee photo/avatar upload exists (not requested, not built).
- The Job designation field is free text, not a controlled list — no "designation catalog" was requested or built.

## 8. Production deployment status

Not yet deployed as of writing this report — migration and code are verified locally (dev DB + dedicated test DB) and ready. Deployment (push → Render auto-deploy → apply migration to production Neon) is the next step, following the exact same careful, non-destructive procedure used in Phases 2 and 3.
