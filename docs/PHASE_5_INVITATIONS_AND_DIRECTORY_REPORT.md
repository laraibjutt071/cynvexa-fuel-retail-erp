# Phase 5a/5c Implementation Report — Invitation-Based Onboarding & Enriched Super Admin Directory

Follows the decisions recorded in `PHASE_5_MARKET_READINESS_AUDIT.md`. Of the five gaps found there, this report covers the two lower-risk pieces implemented now: **5a** (secure token-based staff invitations) and **5c** (richer Super Admin organization directory). **5b** (scoped, time-limited Super Admin access, replacing the current unrestricted `is_superuser` bypass) and **5d** (payroll frontend, leave requests, overtime tracking) remain deliberately deferred to their own future phases — both were flagged as high-risk/large-scope in the audit and the user confirmed that scoping.

## 5a — Invitation-based staff onboarding

**Problem:** every existing account-creation path required the creator to type a password directly for the new user. There was no invite-a-colleague flow, and no email infrastructure exists (nor was any approved — the user chose "token/link, shared manually" over building email sending).

**What was built:**
- `Invitation` model + migration (`f6g7h8i9j0k1`) — organization, email, full name, role, optional station, a SHA-256 token hash (same pattern as `RefreshToken`), 72-hour expiry, and accepted/revoked timestamps.
- `POST /organizations/{org_id}/invitations` — creates an invitation, generates a 32-byte URL-safe token, stores only its hash, returns the raw token exactly once. Gated by the same `USER_CREATE` permission and `actor_can_grant_scope` check as direct user creation, so a station-scoped manager still cannot invite someone into an org-wide role.
- `GET /organizations/{org_id}/invitations` — lists invitations for the Pending Invitations UI.
- `DELETE /organizations/{org_id}/invitations/{id}` — revokes a not-yet-accepted invitation.
- `GET /invitations/{token}/preview` (public, no auth) — lets the invited person see which organization/role they're joining before setting a password. Never leaks anything beyond name/org/role/station when the token is invalid, expired, or already used.
- `POST /invitations/accept` (public, rate-limited) — creates the user, assigns the role, marks the invitation accepted, writes an audit log, and signs the new user in immediately via the same `_issue_tokens` helper `/auth/login` and `/auth/register` use.
- Frontend: a "Invite employee" button on the Staff page (alongside the existing "Add directly" flow), an `InviteEmployeeDialog` that shows the one-time acceptance link with copy-to-clipboard, a "Pending invitations" card with per-invitation revoke, and a new public page at `/invite/[token]` (preview → set password → auto-login → redirect to dashboard). This page is entirely separate from `/login` and does not modify it.

**Tests (9, all passing):** token issued once; preview before accepting; full accept-and-login flow; accepted tokens can't be reused; expired tokens rejected; revoked tokens rejected; invalid tokens rejected (404); a role with no `user:create` permission is rejected (403); cross-tenant invitation attempts rejected (403).

**Known limitation:** no email is sent. The inviter must copy the link from the dialog and send it themselves (Slack/WhatsApp/etc.) — this was the explicit, approved scope.

## 5c — Enriched Super Admin organization directory

**Problem:** the Super Admin's `GET /organizations` list was missing the brief's requested owner name/email, station count, employee count, and last-activity columns.

**What was built:**
- `GET /platform/organizations` (superuser-only) — same `q`/`status` filtering as the existing endpoint, plus owner name/email (the org-wide Owner role holder), station count, active employee count, and most-recent audit-log timestamp per organization. Implemented with a constant number of aggregate queries (not one query per organization) to stay performant as the tenant count grows.
- Frontend: `/dashboard/platform/organizations` now calls this endpoint and renders the new columns.

**Tests (2, all passing):** a seeded organization's row shows its real owner/station/employee counts and a non-null last-activity timestamp after a real audit-logged action; a tenant owner is rejected (403) from this endpoint.

## Verification

- `docker compose build backend` / `docker compose build frontend` — both succeed; the new `/invite/[token]` route compiles and type-checks cleanly.
- Full backend regression suite against the dedicated `cynvexa_test` database: **289 passed**, 0 failed (pre-existing, unrelated pydantic serializer warnings only).
- Full Playwright suite against the running dev stack: **32 passed**, 0 failed.
- Migration `f6g7h8i9j0k1` applies cleanly on top of the existing chain (verified via container restart logs).

## Not yet done (out of scope for this phase)

- Phase 5b: scoped, reason/expiry/audit-logged Super Admin support sessions, replacing the current always-on `is_superuser` bypass.
- Phase 5d: payroll frontend, leave-request workflow, overtime tracking.
- Sending invitation links by email (would require adding an email provider — not approved).
