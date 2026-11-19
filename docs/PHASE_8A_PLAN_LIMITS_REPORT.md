# Phase 8a Implementation Report — Subscription Plan Limit Enforcement

Follows `docs/PHASE_8_MULTI_STATION_SAAS_AUDIT.md`'s §6 (Phase 8a), approved by the owner with additional requirements. This phase is backend-only, requires no database migration, and does not touch the multi-station architecture itself — only the existing `Plan.max_stations`/`max_users` columns, which previously existed but were never read.

## What counts toward each limit (as required: documented precisely)

- **A station** counts the moment it's created, **regardless of `is_active`**. There is no station-delete feature in this app, so a deactivate-then-recreate loop would be a real loophole if deactivated stations stopped counting — a station is a physical business location, not a seat that naturally frees up.
- **A user** counts only while genuinely active: `User.is_active = True` **and** holds at least one active `UserStationRole` in the organization. Deactivating staff is a normal, supported operation and correctly frees the seat — unlike a station, there's a real supported way to release this kind of slot.
- **A pending invitation** (not yet accepted, not revoked, not expired) **also reserves a seat the instant it's created** — otherwise an organization at its limit could send unlimited invitations, each racing to accept into an already-full organization. The reservation converts into the real seat it already reserved on acceptance (never an additional one), and is released the moment the invitation is revoked or expires.
- **No subscription at all → unrestricted**, matching every organization that predates the subscription model (`docs/REMAINING_RISKS.md`'s existing note on this).
- **Platform-governance actions are never subject to a tenant's own limit.** Onboarding a brand-new organization (`POST /platform/organizations`) always creates exactly one station and one owner, which is inherently within any sane plan — it is not re-checked against a *different* organization's limits, and a superuser's own platform actions are unaffected by this feature entirely (tested explicitly — see §Tests, requirement #11).

## Enforcement points (every creation path)

| Path | Check | `counting_pending` |
|---|---|---|
| `POST /organizations/{id}/stations` (direct creation) | `enforce_station_limit` | — |
| `POST /organizations/{id}/users` (direct creation) | `enforce_user_limit` | `True` — reserving a new seat |
| `POST /organizations/{id}/users/{id}/roles` (role grant) | `enforce_user_limit`, but **only if the target user doesn't already hold an active role here** | `True` |
| `POST /organizations/{id}/invitations` (invite) | `enforce_user_limit` | `True` — reserving a new seat |
| `POST /invitations/accept` (public) | `enforce_user_limit` | `False` — consuming the seat this invitation already reserved, never an additional one |

A bare `POST /organizations/{id}/users` call creates a user with no role yet (an existing, pre-Phase-8a design — see Phase 4's report), so it isn't itself a counted "active user" until a role is granted. The check at creation is early feedback for the common case (the "Add employee" UI flow does both in one action); the check at role-assignment is the one that actually matters, and it also catches a role being granted later to an older, previously-unassigned user — not just a freshly created one.

## Concurrency safety (no migration)

Every check locks the `Organization` row (`SELECT ... FOR UPDATE`) before counting, inside the same transaction as the insert that follows — identical to the pattern Phase 5b already established for one-active-support-session-per-admin. A second concurrent request for the same organization blocks on that lock until the first commits or rolls back, then re-counts against the now-current total. No `CHECK` constraint or trigger was needed or added.

## Errors

Both limits raise a 409 with a plain-language message naming the plan, the limit, and what to do (`"This organization's plan (Starter) allows up to 1 station(s), and that limit has been reached. Ask your platform administrator to upgrade..."`). For users, the message also mentions deactivating an unused account, since (unlike stations) that's a real way to free a seat.

## Existing/over-limit organizations

Nothing about this feature touches existing rows. An organization already over its plan's limit (e.g. after a downgrade) keeps every station and user it already has — the lock-then-count-then-insert sequence only ever blocks the *next* creation attempt, verified explicitly (`test_an_already_over_limit_organization_keeps_its_existing_stations`).

## Tests (14 new, `tests/test_plan_limits.py`)

1. Station limit reached → blocked; up to the limit → allowed.
2. No subscription → unrestricted.
3. Over-limit organization (seeded with 2 stations, then the plan tightened to 1) → both existing stations remain, only a third is blocked.
4. Direct user creation blocked at the limit.
5. Role assignment blocked at the limit, even for a user created earlier with no role (isolates the real seat-consuming check from the create_user pre-check).
6. A second role for an already-active user never needs a free seat.
7. Deactivating a user frees a seat for a new hire.
8. Super Admin's own platform onboarding of an unrelated organization is never subject to another organization's limit (requirement #11).
9. Concurrent station creation for the one remaining slot — exactly one of two simultaneous requests succeeds (requirement #3).
10. Invitation creation reserves a seat and is itself blocked once full.
11. Invitation acceptance doesn't double-count its own reservation.
12. Invitation acceptance is correctly rejected if the plan is downgraded between invite and acceptance — the realistic version of "seats filled in the meantime": the reservation system itself already prevents a same-plan race between a pending invitation and a direct creation (tested and confirmed not independently reachable), so the one real way an already-valid pending invitation can end up over limit by acceptance time is the plan shrinking in between.
13. A plain sanity check that seeding a plan/subscription through this feature's own test helper doesn't disturb `Plan`'s `Decimal` price columns.

One existing test needed a one-line fix, not a weakening: `test_station_code_can_repeat_across_different_organizations` (`test_organizations.py`) onboards a second organization whose plan allowed only 1 station — but onboarding itself already creates one ("ST-1"), so the test's own explicit second-station creation was now correctly rejected by this very feature. Raised the test's seeded plan to `max_stations=2`, with a comment explaining why; the test's actual subject (station codes can repeat across organizations) is unchanged and still verified.

## Results

- `tests/test_plan_limits.py`: **14/14 passed**.
- Full backend regression suite: **331 passed**, 0 failed.
- Full Playwright suite: **33 passed**, 0 failed, after pointing `e2e/global-setup.ts` at a new, dedicated `e2e-unlimited` plan (`max_stations`/`max_users` both `null`) instead of the real `starter` plan it had been using — that `starter` plan is genuine pre-existing seed/demo data (`max_stations: 1`, created 2026-11-17, before this phase), and Phase 8a now actually enforces the limit it always nominally had; the E2E suite seeds more stations/users than a 1-station demo plan is meant to accommodate, so it now provisions against a plan built for that purpose instead.
- Docker builds: clean.

## Deployment

No database migration — nothing to apply to Neon before pushing. Production verification will check that an org already at/near its real plan's station or user count still behaves correctly (existing data untouched) after the deploy.
