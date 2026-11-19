# Phase 5b Audit — Super Admin `is_superuser` Bypass and Support-Session Design

## 1. Every `is_superuser` bypass location today

| # | File / line | What it bypasses | Category |
|---|---|---|---|
| 1 | `app/api/deps.py::require_permission` (`allowed = current_user.is_superuser or await user_has_permission(...)`) | **The core gate.** Used as a FastAPI dependency on essentially every tenant-scoped route: stations, users/roles, fuel grades/suppliers/tanks/dispensers/nozzles, fuel prices/receipts, shifts, reading corrections, payment methods, credit customers, reconciliation, supplier ledger, expenses, inventory, reports, attendance/payroll, audit log, invitations, and `organizations.py`'s own `ORGANIZATION_READ`/`ORGANIZATION_UPDATE`. | Tenant business data — **the main bypass** |
| 2 | `app/api/deps.py::require_permission` — suspension check (`if not current_user.is_superuser: ... org.is_active is False -> 403`) | Lets a superuser inspect/reactivate a suspended org even though the org is suspended for everyone else. | Platform governance — legitimate, unrelated to RBAC bypass |
| 3 | `app/api/audit.py::_apply_visibility_scope` | Superuser sees every station's audit rows in an org unfiltered. | Tenant business data (read-scope) |
| 4 | `app/api/expenses.py::list_expenses` | Superuser sees every station's expenses unfiltered. | Tenant business data (read-scope) |
| 5 | `app/api/reports.py::pending_approvals_report` | Superuser sees every station's pending-approval counts unfiltered. | Tenant business data (read-scope) |
| 6 | `app/api/inventory_movements.py::record_inventory_movement` | Superuser can record a stock *adjustment* without holding `inventory_movement:adjust`. | Tenant business data (write) |
| 7 | `app/api/users.py::assign_role` | Superuser can grant a role at **any** scope (org-wide or any station), bypassing `actor_can_grant_scope`'s escalation check. | Tenant business data (write, privilege-escalation-relevant) |
| 8 | `app/api/users.py::revoke_role` | Same as #7, for revocation. | Tenant business data (write) |
| 9 | `app/api/invitations.py::create_invitation` | Superuser can create an invitation at any scope, same escalation bypass as #7. | Tenant business data (write) |
| 10 | `app/api/organizations.py::list_organizations` | Superuser branch sees every organization (cross-tenant list). | **Platform governance, not a bypass** — this is the Super Admin's own directory; it operates on the `Organization` entity itself, same spirit as the already-approved `/platform/organizations` (Phase 5c). |
| 11 | `app/api/organizations.py::update_organization` — `is_active` field | Only a superuser may suspend/reactivate. | **Platform governance, not a bypass** — explicit, intentional, pre-existing, and exactly what Phase 2 built. Must be preserved exactly as-is. |
| 12 | `app/api/platform.py` (stats, onboarding, audit-log, plans, subscriptions) | All gated by `require_superuser` directly — never go through `require_permission`/`user_has_permission` at all. | **Platform governance, not a bypass** — these operate on `Organization`/`Plan`/`Subscription` rows the platform itself owns, not a tenant's operational business data. |

**The real problem is #1**, plus its downstream echoes (#3–#9): one boolean flag, checked with no reason, no expiry, no station restriction, and no audit trail, grants unrestricted read **and write** access to every tenant's stations, fuel, shifts, financial records, inventory, attendance, users/roles, and audit log, at any time, forever. That is precisely what the brief asks to replace.

**#2, #10, #11, #12 are legitimate, already-reviewed platform-administration capabilities** (Phase 2/3/5c) that operate on platform-owned entities (`Organization`, `Plan`, `Subscription`) rather than a tenant's business records. The brief's "Do not accidentally remove platform administration capabilities" applies squarely to these — they must keep working exactly as they do today, without requiring a support session.

## 2. Session, token and audit infrastructure already in place (to be reused)

- **Hashed-token pattern**: `RefreshToken`/`Invitation` already store only a SHA-256 hash of a `secrets.token_urlsafe(32)` value, never the raw token. Not needed for support sessions themselves (they're identified by their own UUID primary key, validated server-side on every request — no bearer token of their own to leak), but the same discipline (server-generated, never client-supplied) applies to `expires_at`.
- **`write_audit_log`**: append-only, must be committed in the same transaction as the event it records. I'll make one deliberate, documented exception — a denied/cross-tenant attempt has no "mutation" to share a transaction with, so that one audit write is committed immediately, by itself.
- **`actor_can_grant_scope`**: the existing escalation guard for role grants — untouched; superuser just stops bypassing it (see finding #7/#8/#9).
- **`get_station_visibility_scope`**: the existing read-scope resolver for org-wide vs. station-scoped role holders — extended with an equivalent resolver for an active support session's scope.
- **Permission-code naming convention**: every read permission in `app/core/permission_codes.py` ends in `:read` (verified against all 45 codes); every other code is a write/action permission. This gives a clean, mechanical "is this a read?" test with no new taxonomy to maintain.

## 3. Why organization-profile read/update stays outside the support-session gate

`test_suspended_organization_blocks_member_access` (`backend/tests/test_organizations.py`) already asserts, deliberately: *"A superuser is exempt, so the org can still be inspected/reactivated while suspended"* — a bare `GET /organizations/{id}` with no session, expecting 200. This is the Super Admin's own organization-directory capability (the same data `/platform/organizations` already exposes), not "inspecting a client's ERP." Folding `ORGANIZATION_READ`/`ORGANIZATION_UPDATE` into the support-session requirement would break this existing, intentional test and remove a platform-admin capability the brief says to preserve.

**Decision**: `ORGANIZATION_READ` and `ORGANIZATION_UPDATE` (for non-`is_active` fields — `is_active` already has its own explicit superuser-only check) keep today's unconditional superuser bypass. Every other permission code — station config, users/roles, fuel, shifts, financial, inventory, attendance, reports, audit log, invitations — moves behind the new support-session gate. This draws the line exactly where the brief draws it: the organization's own identity record is platform-administrable; everything the organization's *staff* actually does with the ERP is tenant business data.

## 4. Existing tests that assume the bypass (will need updating, not weakening)

| Test | Today's assumption | Why it breaks | Resolution |
|---|---|---|---|
| `test_station_code_can_repeat_across_different_organizations` (`test_organizations.py`) | Bare superuser creates a station directly in a second org, no role needed. | `STATION_CREATE` is a tenant write with no role and no session — now denied. | Onboard the second org via the existing `/platform/organizations` flow (creates a real owner) and have that real owner create the station. Tests the same thing (station codes are scoped per-org) through the proper tenant path instead of the bypass. |
| `test_audit_log_is_isolated_per_organization` (`test_audit.py`) | Bare superuser reads `other_org`'s audit log directly, expects 200 + `[]`. | `AUDIT_READ` now requires a session. | Start a support session for `other_org` first, then make the same assertion — strictly stronger: it now also proves the support-session path itself is correctly isolated per-organization. |
| `test_create_station_for_nonexistent_organization_gives_404_not_409` (`test_qa_defects.py`) | Bare superuser hits a *nonexistent* org id, reaching a DB-level FK-violation defect the old bypass alone made reachable (no real `UserStationRole` can ever reference a nonexistent org, so this path only existed via the blanket bypass). | That reachability path no longer exists at all once the bypass is closed — not even a superuser can act on an org that doesn't exist. | Re-target the same "nonexistent org → 404, never something misleading" intent at the new architecture's equivalent entry point: creating a support session for a nonexistent organization must itself 404. |

No test is deleted or weakened — each is re-pointed at the real, still-reachable equivalent of what it was protecting.

All other `is_superuser`-referencing tests (suspend/reactivate, plan/subscription management, platform onboarding, cross-org isolation at the subscription/audit level with a *real* org) are either about the legitimate platform-governance paths (§1, findings #2/#10/#11/#12) or already log in as `owner_user`/other real role-holders, not the bypass — unaffected.

## 5. Proposed support-session architecture

**New model `SupportSession`** (`app/models/support_session.py`), additive migration only:

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `superuser_id` | FK → `users.id` | the admin who opened it |
| `organization_id` | FK → `organizations.id` | required |
| `station_id` | FK → `stations.id`, nullable | org-wide if null |
| `reason` | `String`, required, min length enforced in the schema | why access was needed |
| `created_at`, `expires_at`, `ended_at` | `DateTime(timezone=True)` | `expires_at` is always `created_at + a server-validated duration`, **never a client-supplied timestamp**; `ended_at` covers both a voluntary "End Support Session" and an auto-close of a stale expired row found at the next creation attempt — one field, since nothing in this phase introduces a second admin who revokes someone else's session |
| `ip_address`, `user_agent` | nullable strings | captured from the request at creation |

Status is **computed**, never stored as a separately-maintained enum that could drift: `active` if `ended_at is None and expires_at > now()`, `ended` if `ended_at is not None`, `expired` otherwise.

No `write_enabled`/`write_permissions` column exists at all — per the owner's revision, a support session is **strictly read-only**, so there is nothing to store beyond the scope and timing fields above.

**Constants** (`app/core/support_sessions.py`):
- `SUPPORT_SESSION_ALLOWED_DURATIONS_MINUTES = [15, 30, 60]`, max 60 — "short configurable lifetime... strict maximum," server-validated against this list, never a client-chosen arbitrary value.
- A support session grants **only** permission codes ending in `:read`, within its org/station scope. No write code of any kind — including `user:update` and `reading:correct_approve`, which this audit originally proposed — is reachable through a support session. A superuser gets no write path into tenant business data at all without a real tenant role. This is a hardening relative to today (where the bypass covered everything), stated explicitly so it isn't mistaken for an oversight.
- At most **one active session per superuser at a time**, enforced both at the application layer (auto-closing an expired row, then re-checking) and at the database layer (a partial unique index on `superuser_id WHERE ended_at IS NULL`, so two concurrent creation requests cannot both succeed) — this keeps "which session is this request using" unambiguous without trusting a client-supplied session id for authorization, and satisfies "no automatic renewal without a new authorization process."

**Core helper, `app/core/support_sessions.py`**:
- `get_active_support_session(db, *, superuser_id, organization_id)` — the superuser's current non-ended, non-expired session for that org, or `None`.
- `support_session_grants(db, *, current_user, organization_id, station_id, permission_code)` — returns the session if it grants access (station match, and read-vs-`write_permissions` check), else `None`.
- `superuser_visible_station_ids(db, *, current_user, organization_id)` — mirrors `get_station_visibility_scope`'s return shape (`None` = unrestricted, else the one station) for the three read-scope call sites (#3/#4/#5 above).

**`require_permission` becomes**:
```
allowed = await user_has_permission(...)
if not allowed and current_user.is_superuser and permission_code not in (ORGANIZATION_READ, ORGANIZATION_UPDATE):
    session = await support_session_grants(db, current_user=..., organization_id=..., station_id=..., permission_code=...)
    allowed = session is not None  # support_session_grants itself only ever returns a session for a :read code
if not allowed:
    if current_user.is_superuser:
        write_audit_log(..., action="support_session.access_denied", ...)
        await db.commit()
    raise PermissionDeniedError()
```
(`ORGANIZATION_READ`/`ORGANIZATION_UPDATE` keep the direct bypass per §3; the suspension-exemption check right above it is untouched. `support_session_grants` rejects any `permission_code` that doesn't end in `:read` before even looking up a session, so there is no code path by which an active session can satisfy a write check.)

#3/#4/#5 (audit log, expenses, reports) swap their `if not current_user.is_superuser:` scope-filter branch for `superuser_visible_station_ids`. #6/#7/#8/#9 (inventory adjustment, role assign/revoke, invitations) simply **drop** the `current_user.is_superuser or` clause outright — per the curated write-list decision above, there is no session-based replacement for these; a superuser needs a real role for any of them, same as anyone else.

## 6. Permission matrix (support session)

| Capability | Without a session | With an active support session |
|---|---|---|
| View org profile, suspend/reactivate | ✅ (unchanged, direct superuser) | ✅ |
| View stations, users, fuel, shifts, financial, inventory, attendance, audit log, reports (in the session's org/station) | ❌ | ✅ (read-only) |
| Edit/deactivate a user account, assign/revoke a role, create an invitation, approve a fuel receipt/expense/reconciliation/reading correction, set a fuel price, adjust inventory, manage payroll — **any** tenant business-data write | ❌ | ❌ — **no support-session path to any write, ever, in this phase** |
| Access a different organization or station than the one the session was opened for | ❌ | ❌ |

## 7. Database/migration plan

One additive migration: `create_table("support_sessions")` with the columns above, FKs (`superuser_id`/`organization_id`/`station_id` `ondelete="CASCADE"`, matching `Invitation`'s pattern), a **partial unique index** `ix_support_sessions_one_active_per_admin ON support_sessions (superuser_id) WHERE ended_at IS NULL` (the concurrency guard from the owner's revision), and a plain index on `(superuser_id, organization_id)` (the hot lookup path). Full downgrade (`drop_index` x2, `drop_table`). No existing table or column touched.

## 8. API surface

- `POST /platform/support-sessions` — create (reason, duration, optional station). Validates the organization (and station, if given) exist and the station belongs to that organization; auto-closes the caller's own already-expired session (if any) before deciding; 404 if org/station doesn't exist, 409 if the caller already has a still-active session.
- `GET /platform/support-sessions/active` — the caller's current active session, or `null`.
- `POST /platform/support-sessions/{id}/end` — voluntary end; 403 if it's not the caller's own session.
- `GET /platform/support-sessions` — the caller's own session history.
- `GET /platform/organizations/{organization_id}` — single-row read (reuses the Phase 5c aggregate query), so the Super Admin can review the target org's identity *before* opening a session, without that lookup itself requiring one.

All five are `require_superuser`, independent of `require_permission`/tenant RBAC — they're platform-level, same as the rest of `platform.py`.

## 9. Frontend changes

- Super Admin organization detail page (`/dashboard/platform/organizations/[orgId]`): add "Start Support Session" (reason, duration, optional station — no write toggle; there is nothing to toggle), an unmistakable active-session banner (target org, countdown, "End Support Session"), and a session-history list. Tenant-data sections of this page (stations/users/roles) only load once a session is active.
- No change to `/login` or any existing client-facing page. Client users never see support-session controls and are never misrepresented as being impersonated.

## 10. Compatibility risks

- The write-up in §4 covers every test I found that assumes the bypass; each gets updated to exercise the same intent through a still-valid path, not weakened or deleted.
- `#2` (suspension exemption) and `ORGANIZATION_READ`/`ORGANIZATION_UPDATE` (§3) are explicitly carved out, preserving the existing suspend/reactivate-while-suspended behavior and the Super Admin directory/detail flow's basic org lookups.
- Removing the bypass from #6–#9 (inventory adjust, role assign/revoke, invitations) means a bare superuser with no tenant role can no longer do these at all, in any organization, under any circumstance — this is an intentional hardening (these are exactly the actions most adjacent to privilege escalation or financial risk), called out so it isn't mistaken for a regression if a platform admin ever relied on it.

## Revision after owner review (2026-11-19)

The owner reviewed this audit and tightened the design before approving implementation:

1. **Support sessions are now strictly read-only — no write path at all.** `write_enabled`, `write_justification`, and `write_permissions` (and the `SUPPORT_SESSION_WRITE_PERMISSIONS` curated list, including `user:update` and `reading:correct_approve`) are dropped entirely from the design in §5/§6 below. A support session grants exactly the permission codes ending in `:read`, within its org/station scope, and nothing else. Any future need for a support-initiated write becomes its own, separate, narrowly-scoped and separately-audited workflow — not part of this phase.
2. **Session-scope validation is server-side and absolute**: organization_id is mandatory on every session; station_id, if present, narrows it further; nothing in a request body or query string can widen or redirect that scope — only the URL's own path parameters (already true of `require_permission`) are ever consulted.
3. **Concurrency hardening for the one-active-session-per-admin rule**: a partial unique index (`superuser_id` WHERE `ended_at IS NULL`) at the database level, plus `SELECT ... FOR UPDATE` on the admin's existing non-ended row (if any) during creation, so two concurrent creation requests cannot both succeed — one always loses, either to the row lock (existing session) or to the unique-index violation (first-ever session, both racing to insert). An existing session that has already expired is auto-closed (`ended_at` set) within that same locked transaction before deciding whether a new one may be created, so a stale expired row can never block a legitimate new session indefinitely.
4. Every one of the six additional `is_superuser` bypass sites (audit log, expenses, reports, inventory adjustment, role assign/revoke, invitations) is addressed, not just `require_permission` — classified in §1 above as tenant-read-scope (audit/expenses/reports, fixed via the session-aware station-scope resolver) or tenant-write-authorization (inventory/role/invitation, fixed by removing the bypass outright now that there is no write grant to replace it with).

§5/§6/§8/§9 below are written to already reflect this revision.

## Implementation plan (pending approval)

1. `SupportSession` model + migration.
2. `app/core/support_sessions.py` (constants + helpers).
3. Rewrite `require_permission` per §5; update audit.py/expenses.py/reports.py read-scope filters; drop the bypass in inventory_movements.py/users.py (x2)/invitations.py.
4. New `app/api/support_sessions.py` + `GET /platform/organizations/{id}`.
5. Update the three tests identified in §4.
6. New automated tests per the brief's §11 (session creation, access, privilege separation, write restrictions, concurrency/expiry, audit) and the full existing suite re-run.
7. Frontend: support-session UI on the org detail page.
8. Full regression (backend pytest + Playwright), migration applied to Neon before push, production verification — same discipline as Phase 5a/5c.

Final report at `docs/PHASE_5B_SUPER_ADMIN_SUPPORT_SESSIONS_REPORT.md` once all of the above is verified, not before.
