# Phase 5b Implementation Report — Super Admin Support Sessions

Follows `docs/PHASE_5B_SUPER_ADMIN_SUPPORT_SESSIONS_AUDIT.md`, which was presented and approved (with tightening) before any code changed. The owner's three revisions — strictly read-only (no write path at all, not even the originally-proposed `user:update`/`reading:correct_approve`), server-side-only scope resolution, and database-level concurrency hardening for the one-session-per-admin rule — are implemented exactly as specified in that audit's revision section.

## What changed

**The bypass.** `app/api/deps.py::require_permission` no longer treats `is_superuser` as blanket access. A superuser now gets through only via:
1. `ORGANIZATION_READ`/`ORGANIZATION_UPDATE` — unchanged, direct access (this is the Super Admin's own directory/governance data, not a tenant's business records; preserves the existing suspend/reactivate-while-suspended behavior and test).
2. A real `UserStationRole` grant — unchanged, same as any tenant user.
3. An active, scope-matching **support session** — new, and strictly read-only: `support_session_grants()` rejects any permission code that doesn't end in `:read` before even looking one up, so there is no code path by which a session can satisfy a write check.

Six other `is_superuser` bypass sites were audited and fixed individually:
- `audit.py`, `expenses.py`, `reports.py` (read-scope filters) — now resolve a superuser's visible stations from their active session's own scope, instead of unconditionally seeing everything.
- `inventory_movements.py` (stock adjustment), `users.py` ×2 (role assign/revoke), `invitations.py` (invite scope) — the bypass is simply removed. These are writes with no session-based replacement; a superuser needs a real tenant role for any of them, full stop.

## Support session design

- `SupportSession` (`app/models/support_session.py`): `superuser_id`, `organization_id`, optional `station_id`, mandatory `reason`, `expires_at` (server-computed from one of `[15, 30, 60]` minutes — never a client-supplied timestamp), `ended_at`. No write-grant column of any kind exists.
- **At most one active session per admin**, enforced twice: a `SELECT ... FOR UPDATE` on the admin's existing non-ended row at creation (closing it first if it's already expired), and a partial unique index (`superuser_id WHERE ended_at IS NULL`) at the database level, so two concurrent creation requests can't both succeed even when neither sees an existing row to lock. (Found and fixed during implementation: the index was only in the Alembic migration at first, so the test database — built from the SQLAlchemy models via `create_all`, not migrations — didn't have it and the concurrency test failed; it's now declared on the model itself too.)
- `GET /platform/organizations/{id}` (new) lets the Super Admin review a target org's identity before opening a session, without that lookup itself requiring one.
- API: `POST /platform/support-sessions` (create), `GET /platform/support-sessions/active`, `GET /platform/support-sessions` (own history), `POST /platform/support-sessions/{id}/end` — all `require_superuser`, independent of tenant RBAC.

## Frontend

The Super Admin organization detail page now gates its stations/users/roles sections behind an active session for that org: a locked message with a "Start support session" button when there isn't one, a loud warning-colored banner with a live countdown and "End support session" when there is, and a session-history card. The dialog currently offers organization-wide sessions only (no station picker) — picking a specific station up front isn't possible yet without that same lookup requiring a session, which is the exact circular dependency a support session exists to gate; narrowing to one station is deferred to a later UI pass. The login page and every client-facing page are untouched.

## Tests

- **28 new tests** (`tests/test_support_sessions.py`): creation (authorized/unauthorized/missing reason/invalid duration/nonexistent org or station/suspended-org policy), access (own org, wrong org, wrong station, expired, ended, another admin's session, missing context, query-string scope widening), privilege separation (owner/employee can't create one, can't reach platform config or escalate itself), write restrictions (user creation, role assignment, station update all denied; read still works), concurrency (one-active-session-per-admin, concurrent creation race, repeated requests against an expired session), and audit (creation/end recorded, denied cross-tenant access recorded).
- **3 existing tests re-pointed**, not weakened, each to the real equivalent of what it previously exercised via the bypass:
  - `test_station_code_can_repeat_across_different_organizations` — the second organization is now onboarded with its own real owner (`/platform/organizations`) instead of a bare superuser station-create call.
  - `test_audit_log_is_isolated_per_organization` — the superuser now opens a support session for `other_org` first; the assertion was corrected to expect that session's own `support_session.create` audit entry (a real, legitimate event for that org) rather than an empty list.
  - `test_create_station_for_nonexistent_organization_gives_404_not_409` — re-targeted at starting a support session for a nonexistent organization, since the original reachability path (a bare superuser bypass reaching a nonexistent org) no longer exists at all.
- **1 new Playwright test** (`e2e/support-sessions.spec.ts`): stations are locked, then visible after starting a session, then locked again after ending it — through the real UI, not just the API.
- `e2e/global-setup.ts` was substantially rewritten: it previously seeded all tenant fixture data (stations, fuel grades, tanks, shifts, users, etc.) through a second bare superuser account, relying entirely on the now-removed bypass. It now provisions the E2E organization through the real "Create Petrol Pump" onboarding flow and does all tenant-data seeding as that organization's real Owner — which also means the existing dashboard/daily-entry/day2 Playwright specs now exercise real role-based access instead of a superuser shortcut.

## Results

- Backend: **317 passed**, 0 failed (full suite, `cynvexa_test`).
- Frontend: `docker compose build frontend` — clean build and typecheck.
- Playwright: **33 passed**, 0 failed (full suite, real dev stack).
- Migration `g7h8i9j0k1l2` applies cleanly on top of `f6g7h8i9j0k1`.

## Remaining `is_superuser` references, and why each is safe

| Location | Why it's fine |
|---|---|
| `deps.py::require_superuser` | The platform-admin gate itself — not a tenant bypass. |
| `deps.py::require_permission`'s suspension exemption | Lets a superuser inspect/reactivate a suspended org; unrelated to tenant business-data access, which still requires a session. |
| `deps.py::require_permission`'s `ORGANIZATION_READ`/`ORGANIZATION_UPDATE` carve-out | Deliberate, documented in §3 of the audit; preserves existing, approved Super Admin directory behavior. |
| `organizations.py::list_organizations`/`update_organization`'s `is_active` check | Platform governance (suspend/reactivate, cross-org directory) — Phase 2's existing, correct design. |
| `platform.py` (stats, onboarding, plans, subscriptions, audit-log, the enriched directory) | Never used `require_permission` at all — these are `require_superuser`-only platform routes over platform-owned entities, not tenant business data. |
| `auth.py`/`schemas/auth.py` (`is_superuser` on the `/auth/me` response) | Informational only — tells the frontend who it's talking to; grants nothing by itself. |
| `seed.py` | CLI bootstrap for creating the first platform admin account — not a request-time check. |

## Known limitations / deferred

- No UI path yet to open a station-scoped session (backend fully supports it; see Frontend section above).
- No "support session" badge shown to the tenant's own users while one is open against their org — the brief allowed this ("where appropriate"); not built in this pass.
- Phase 5d (payroll/leave/overtime) remains a separate, not-yet-started phase.

## Deployment

Migration `g7h8i9j0k1l2` will be applied to the production Neon database before pushing to GitHub, following the established safe-deploy pattern (migration first, then push, then verify both Render services against the live site) — not yet done as of this report; see the final summary message for confirmation once complete.
