# Phase 3 — Super Admin Dashboard & Tenant Management

**Date:** 2026-11-18
**Architecture:** shared-schema multi-tenancy, as decided in Phase 1/2. No database-per-tenant work, no Neon API key requested, no change to how `organization_id`/`station_id` scoping works.

---

## 1. Audit of existing platform-admin capabilities (done before writing any code)

Before building anything, the existing `app/api/platform.py`, `app/dashboard/platform/page.tsx`, `/auth/register`, and `app/api/users.py` were read in full. What was already real and reused as-is, unchanged:

- `require_superuser` dependency — every new endpoint in this phase uses the exact same dependency `/platform/plans` already used, not a new auth mechanism.
- Plan/Subscription/SubscriptionPayment CRUD (`app/api/platform.py`) — untouched; moved to its own page in the frontend, logic unchanged.
- `GET /organizations/{id}/stations`, `GET /organizations/{id}/users`, `GET /organizations/{id}/users/{id}/roles` — all pre-existing, reused by the new organization detail page with zero backend changes.
- `POST /organizations/{id}/users` (`UserCreate` schema) — confirmed it has no `is_superuser` field at all, so a tenant owner already had no way to grant platform-admin privileges to anyone they create. Added a regression test for this (`test_user_create_payload_cannot_set_is_superuser`) rather than assuming it from reading the schema.
- Phase 2's suspension enforcement (`require_permission` checking `Organization.is_active`) — untouched, re-verified by this phase's own tests and live suspend/reactivate walkthrough.

**What was duplicated logic before this phase that is not anymore:** `/auth/register`'s entire org+station+owner+role+subscription creation block has been extracted into `app/core/tenant_provisioning.py::provision_organization_with_owner()`. Both `/auth/register` (self-service, auto-login) and the new `POST /platform/organizations` (Super Admin onboarding, no auto-login) call the same function. This was a refactor, not new business logic — `/auth/register`'s existing tests (`test_registration.py`) pass unchanged, proving its behavior didn't change.

---

## 2. What was implemented

### Backend

**Database (one additive migration, `d4e5f6g7h8i9`):** `organizations` gained five new nullable columns — `phone`, `address`, `city`, `province`, `country`. No existing column touched, no existing row affected, fully reversible (`downgrade()` drops them back). Applied to the local dev database and verified; **not yet applied to the production Neon database** — see Section 5.

**New endpoints:**

| Method & path | Auth | Purpose |
|---|---|---|
| `POST /platform/organizations` | `require_superuser` | The "Create Petrol Pump" workflow — one call provisions org + station + owner + Owner role + trial subscription, via the shared provisioning function. Returns org/owner identifiers, never an access token (the caller isn't the new owner). |
| `GET /platform/stats` | `require_superuser` | Real `COUNT(*)` metrics: total/active/suspended organizations, total owners (distinct users holding an org-wide role), total non-superuser users, 5 most recently created organizations. |
| `GET /platform/audit-log` | `require_superuser` | The same `audit_logs` table every org already has its own scoped view of, with the organization filter removed — a platform-wide recent-activity feed. |

**Changed endpoint:** `GET /organizations` now accepts optional `q` (name search, case-insensitive) and `status` (`active`/`suspended`) query parameters, for both the superuser branch and the existing multi-org-member branch.

**No permission-code changes.** Every new/changed endpoint is `require_superuser`-gated, the same pattern `app/api/platform.py` already used for Plans — nothing here needed a new entry in `permission_codes.py`.

### Frontend

All under a new, separate navigation shell (`app/dashboard/platform/layout.tsx`) — its own sidebar (Overview / Organizations / Plans), distinct from the tenant `AppShell`, matching the brief's "keep Super Admin navigation separate" requirement. The pre-existing `/dashboard/platform` route now resolves to the Overview page inside this shell rather than the old single-page Plans+Orgs screen.

| Route | What it does |
|---|---|
| `/dashboard/platform` | Overview — stat cards (real counts from `/platform/stats`), recently created organizations, recent platform activity feed. |
| `/dashboard/platform/organizations` | Searchable, status-filterable, sortable table of every organization (`DataTable`), with a "Create organization" button. |
| `/dashboard/platform/organizations/new` | The guided 3-step onboarding wizard (Business information → Owner account → Review & create). Nothing is created until the final step; a clear success screen shows the owner's email and links to the new org's detail page. |
| `/dashboard/platform/organizations/[orgId]` | Business info, Owner(s), Stations, All users, and Subscription management (moved from the old page) — plus the Suspend/Reactivate action, gated behind a `ConfirmDialog` (never a bare click), with real-time status badge updates. |
| `/dashboard/platform/plans` | The pre-existing Plan CRUD, moved here unchanged. |

**Login page:** not touched.

**UI components used, all pre-existing:** `DataTable` (sortable, built-in skeleton loading, empty state), `ConfirmDialog`, `Badge`/`StatusBadge`, `Field`/`TextInput`/`Select`, `Button`, `useToast`. No new design-system components were needed — this phase's job was composing what Phase 4's design pass already built, not inventing new UI primitives.

---

## 3. Permission changes

None. Every new capability in this phase is gated by the existing `require_superuser` dependency — the same one `app/api/platform.py`'s Plan/Subscription endpoints already depended on. No new permission code, no change to the 7-role tenant permission catalog, no change to what a tenant Owner/Manager/Cashier/etc. can do.

---

## 4. Security testing (Section 6 of the brief) — all verified with real tests, not assumed

| Scenario | How it's proven |
|---|---|
| Tenant owner cannot access platform administration | `test_tenant_owner_cannot_call_platform_onboarding`, `test_tenant_owner_cannot_access_platform_stats_or_audit_log` — real 403s against a real Owner token |
| Tenant owner cannot suspend their own organization | Phase 2's `test_owner_cannot_suspend_their_own_organization`, re-confirmed still passing |
| Tenant A cannot view Tenant B | Pre-existing `test_cross_tenant_isolation.py` + `role-permissions.spec.ts`, re-run and passing — untouched by this phase |
| Platform admin can view the organization registry | `test_organization_search_and_status_filter` |
| Suspended organization remains blocked | Phase 2's `test_suspended_organization_blocks_member_access`, plus a **live manual walkthrough this phase**: created a real test organization through the wizard, suspended it through the UI, confirmed its owner got a real 403 from a direct API call, reactivated it through the UI, confirmed access returned — screenshotted at every step |
| Authorized platform admin can reactivate it | Same walkthrough above |
| Unauthorized users cannot access tenant management APIs | Every `/platform/*` endpoint requires `require_superuser`; `test_tenant_owner_cannot_access_platform_stats_or_audit_log` proves it for a real (non-superuser) token, not just by reading the dependency |
| User creation cannot escalate privileges | `test_user_create_payload_cannot_set_is_superuser` — sends `is_superuser: true` in the create-user payload, confirms the created row is `is_superuser=False` regardless, because the schema has no such field to honor |

---

## 5. Test results

**Backend:** 262 pre-existing tests + 9 new (`test_platform_tenant_management.py`) + 3 from Phase 2 (`test_organizations.py`, re-confirmed) all passing. Run **against the dedicated `cynvexa_test` database** (`docker compose exec -T -e DATABASE_URL=...cynvexa_test backend python -m pytest`), explicitly, after the Phase 2 incident where an un-overridden `DATABASE_URL` pointed pytest at the dev database — this phase's own test runs were double-checked to use the correct database every time, and the dev database's own Alembic tracking was verified separately (its `alembic_version` advanced cleanly to the new migration, `d4e5f6g7h8i9`, with no errors).

**Frontend:** `tsc`/production build clean (`docker compose build frontend`), all new routes present in the build output. Full Playwright suite: 32/32 passing, confirming this phase's changes didn't regress any existing tenant-side flow.

**Manual/functional verification beyond automated tests:** registered a real organization through the new wizard end-to-end (business info → owner account → review → create), confirmed the new owner could sign in independently with no connection to the admin's own session, confirmed the organization detail page showed real business info/owner/station/subscription data, and ran a full suspend → verify-blocked (real 403 via direct API call) → reactivate → verify-restored cycle through the actual UI, not just via API calls.

---

## 6. Known limitations

- **The new `organizations` columns (phone/address/city/province/country) have not yet been migrated into the live production Neon database** — only the local dev database. They must be applied there (`alembic upgrade head` against the production connection string, the same careful one-off procedure used in earlier phases) before the Super Admin UI's business-info fields will show real data for the existing production demo organization, rather than blanks.
- The old bare `/dashboard` page (not part of this phase's scope) still shows a superuser a small, separate "Create organization" box that only creates a bare `Organization` row with no owner — strictly inferior to the new wizard, left untouched rather than risking an unrelated change; a superuser should use `/dashboard/platform/organizations/new` instead.
- "View owner details" shows the Owner's name/email/active-status; it does not yet show last-login or session history — no such data is currently tracked anywhere in the system (not a regression, a pre-existing gap).
- No pending-organization status exists (brief said "if supported") — this platform has no pending-approval workflow for new tenants today; every organization created through the wizard is immediately active.
- Payroll and attendance-hardware work was explicitly out of scope for this phase, per the brief, and nothing in that area was touched.

---

## 7. Remaining tasks (not started this phase, by design)

- Apply the new migration to production Neon.
- Phase 4 (per the original master brief's phase list): attendance hardware integration architecture.
- Phase 5: payroll policy engine (the brief's Section 9 per-minute/configurable-deduction calculation — Phase 1's audit found this doesn't exist yet; still true).
- A payroll frontend (still doesn't exist, confirmed absent again by this audit).
