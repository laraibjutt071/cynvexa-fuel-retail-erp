# CYNVEXA — Phase 6 Role Security, Cashier Permission Fix & Onboarding Report

**Date:** 2026-11-15
**Scope:** The owner-approved Cashier/Operator `tank:read`/`nozzle:read` fix (mandatory deliverable), the real role-based workflow matrix, and a review pass over onboarding/operational screens. The audit behind this report is `docs/PHASE_6_ROLE_ONBOARDING_AUDIT.md` — read that first.

---

## 1. Audit findings (summary — full detail in the audit doc)

- The Phase 5 finding was re-confirmed by re-reading the current code before any edit: `Cashier / Operator` held `shift:open`/`shift:close` but not `tank:read`/`nozzle:read`, so the Readings step's own tank/nozzle listing calls 403'd for that role.
- `Role`/`Permission` are global catalog tables, not per-organization — `app/seed.py`'s seed command is additive-only (never removes a permission a role already has), which is why this fix could be applied safely to every existing client organization's Cashier users via one idempotent command, not a migration.
- No separate "Operator" role exists — only one combined `Cashier / Operator` role, confirmed again this phase.
- Platform Administrator / Organization Owner / station-level employee separation was already correctly enforced both in the UI (`dashboard/platform/page.tsx` redirects non-superusers) and the backend (`require_superuser`) — re-verified, not a new fix.
- No guided onboarding wizard exists after self-service registration — re-confirmed, matching Phase 1/3's prior findings exactly.
- **New finding this phase:** the Attendance page's own title said "Attendance & Payroll" and its subtitle claimed "salary deduction rules" were part of it, but no payroll UI exists anywhere in the frontend (confirmed by a repository-wide search) despite the backend having a materially complete payroll API (`app/api/attendance.py`'s `payroll_router`: rules CRUD, salary generation, salary listing, salary finalization). This was a real, false completion indicator — fixed this phase (Section 4).

## 2. The Cashier/Operator permission fix — exact change

**File:** `backend/app/core/permission_codes.py`. Added `TANK_READ` and `NOZZLE_READ` to `SEED_ROLES["Cashier / Operator"]`, with an inline comment explaining why and what was deliberately *not* added (no `*_MANAGE`, no approval permission).

**Applied to the real, already-running database** (not just the seed source file) by re-running the existing idempotent command:
```
docker compose exec backend python -m app.seed permissions-roles
```
Verified directly in Postgres afterward — the live `Cashier / Operator` role's permission set is now exactly:
```
inventory_item:read, inventory_movement:read, inventory_movement:record,
nozzle:read, payment_method:read, shift:close, shift:open, shift:read,
shift_reconcile:record, station:read, tank:read
```
Every permission the role held before is still present — nothing was removed, confirmed by direct comparison with Phase 5's own recorded list. This is the real mechanism by which "existing client role assignments are handled safely": the seed command is incapable of removing a permission, so no existing organization's customized role (if any owner ever removed a default permission from this role through the Users & Settings UI) can be silently overwritten by this change — it can only gain the two new ones, same as every other organization using the default role.

**No database migration was created or needed** — `tank:read`/`nozzle:read` already existed as `Permission` catalog rows (other roles already reference them); this was one new `role_permissions` association row, which is exactly what the idempotent seed command is for. Step 8's "test migration upgrade/downgrade on a scratch database" does not apply here because there is no migration — this was verified by checking `alembic/versions/` for any new revision (none was created) and confirming the fix is visible after a normal container restart with no `alembic upgrade` step involved beyond what already runs automatically.

## 3. Frontend changes

**None were required for the fix itself.** `ReadingsSection.tsx`'s tank/nozzle tables already called the real `GET .../tanks` and `GET .../nozzles` endpoints unconditionally (Phase 5) and simply left `tanks`/`nozzles` as `null` forever when the call 403'd — there was no frontend-side permission gate blocking the *display* of this data, only the backend's own check. Once the backend grants the permission, the existing frontend code works correctly with zero changes, confirmed by the new Playwright test that loads the Readings tab as a real Cashier and finds real tank data instead of a permanent "Loading…" state (Section 6).

**One honest-copy fix, unrelated to the permission change:** `app/dashboard/org/[orgId]/station/[stationId]/attendance/page.tsx`'s title ("Attendance & Payroll") and subtitle (claiming salary rules exist on that screen) were corrected to describe only what the page actually does, per the audit's new finding (Section 1) and this phase's own Step 4 instruction not to show false completion indicators.

## 4. Regression tests added (Step 2's required list, all present)

New file: `backend/tests/test_phase6_cashier_tank_nozzle_access.py` (11 tests):

| Test | Proves |
|---|---|
| Cashier can read own station's tanks | The fix works |
| Cashier can read own station's nozzles | The fix works |
| Cashier cannot read a different station's tanks | Station scoping holds |
| Cashier cannot read a different station's nozzles | Station scoping holds |
| Cashier cannot read another organization's tanks | Org scoping holds |
| Cashier cannot create a tank | Still read-only |
| Cashier cannot edit a tank | Still read-only |
| Cashier cannot create a nozzle | Still read-only |
| Cashier cannot edit a nozzle | Still read-only |
| Cashier cannot approve a reading correction | No approval authority was granted alongside the read access |
| Owner/Station Manager tank-read and Station-Manager tank-*manage* (still denied) are unaffected | This phase only added to Cashier/Operator - every other role's existing access, including what it still correctly lacks, is unchanged |

New frontend tests in `e2e/daily-entry-roles.spec.ts` (replacing the test that previously documented the *bug* — the same file's own comment said updating it would be "progress, not a regression" once fixed):

| Test | Proves |
|---|---|
| Cashier's token can read station 3's tanks and nozzles via the real API | Backend fix, end to end |
| Cashier's Readings tab now shows tank/nozzle content instead of loading forever | The actual UI symptom from Phase 5 is gone |
| Cashier still cannot create a tank via a direct API call | No scope creep in the fix |

## 5. Role-based workflow matrix

See `docs/PHASE_6_ROLE_ONBOARDING_AUDIT.md` Section 3 for the full table (Cashier/Operator, Shift Supervisor, Station Manager, Accountant, Storekeeper/Technician, Auditor/Viewer, Owner, Platform Administrator × every major capability). Every cell is sourced directly from `app/core/permission_codes.py::SEED_ROLES`, not inferred from the UI, and cross-checked against the actual `require_permission()` dependency each backend endpoint uses.

## 6. Testing (Step 7, exact results)

### 6.1 Backend — full pytest suite
```
259 passed, 0 failed, 0 skipped, 0 errors
3 warnings (pre-existing, non-fatal - unchanged since Phase 2)
Exit code: 0
Duration: 775.61s (12 min 55 sec)
```
259 = 248 (Phase 5's count) + 11 new Phase 6 tests. Zero regressions.

### 6.2 Frontend — TypeScript and production build
```
npx tsc --noEmit  → 0 errors
npm run build     → Compiled successfully, 16/16 routes generated, exit code 0
```

### 6.3 Playwright — the two previously-known failures were investigated, root-caused, and fixed (not re-tracked, not weakened)

Step 7 explicitly asked for this investigation rather than another re-statement. Both were root-caused by actually reading the failing test and the real page it targets:

1. **Tank management page's "displays tank cards or empty message" test.** Root cause: the test checked `.isVisible().catch(() => false)` immediately after `page.goto()`, with no wait — a real race condition against the page's own async data fetch, not an application bug. It could land mid-"Loading…" and then time out waiting for an empty-state message that would never appear (because tanks genuinely exist in the seed data). **Fixed** by waiting for either real end state first (`tankCard.or(emptyState)`), removing the race without changing what's actually asserted.
2. **Credit customers page's "loads and shows credit customers heading" test.** Root cause: the page has an `<h1>` page title and a `<h2>` card title that legitimately share the same text ("Credit customers" page containing a "Credit customers" list card) — not a bug, a reasonable page structure the test simply wasn't scoped precisely enough to distinguish. **Fixed** by targeting `getByRole("heading", { level: 1, ... })`, which is what the test always meant to check.

A third test in the same file (`shows customer list or empty state`) had the identical unwaited-`.isVisible()` race condition and happened to pass this run by luck — hardened proactively with the same fix pattern rather than left fragile.

```
32 total: 32 passed, 0 failed
```

**Both long-standing failures tracked since Phase 2 are now genuinely resolved**, not just carried forward as "pre-existing" again. No test was deleted, skipped, or had its assertion weakened to achieve this — both fixes make the test check something more precisely true than before.

### 6.4 Cross-station and cross-organization security results
All new Phase 6 tests (Section 4) that assert station/org isolation passed. No existing cross-tenant or RBAC test (Phases 2–3's suites) regressed — confirmed by the identical 259-pass count including every one of those pre-existing files.

## 7. Onboarding and operational-screen review (Steps 4–6) — honest scope

**What this phase actually did:** re-verified the existing Platform Admin / Owner / station-employee separation (already correct, no change needed), fixed one real false-completion-indicator on the Attendance page (Section 3), and produced the role-based workflow matrix (Section 5) that makes "which role can do what" auditable going forward.

**What this phase did not do, named rather than hidden:** it did not build a guided onboarding wizard (Phase 1/3's already-identified gap remains open — a new owner still lands on an empty dashboard with no step-by-step setup checklist), and it did not build a payroll UI (the backend API is materially complete; the frontend has none — a real, sizable feature gap, not a quick fix). Building either is a feature-sized addition beyond this phase's mandate (the Cashier permission fix, the role matrix, and a review pass) and is recommended for a future phase (Section 10) rather than attempted partially here.

## 8. Files changed this phase

| File | Change |
|---|---|
| `backend/app/core/permission_codes.py` | Added `TANK_READ`, `NOZZLE_READ` to `Cashier / Operator`'s seed permissions |
| `backend/tests/test_phase6_cashier_tank_nozzle_access.py` | New - 11 tests (Section 4) |
| `frontend/e2e/daily-entry-roles.spec.ts` | Replaced the bug-documenting test with 3 tests proving the fix; updated the file's own header comment |
| `frontend/e2e/day2-pages.spec.ts` | Fixed the two long-standing failures at their root cause (Section 6.3) |
| `frontend/app/dashboard/org/[orgId]/station/[stationId]/attendance/page.tsx` | Corrected the page title/subtitle to stop implying payroll functionality that doesn't exist on this screen |

**Database migrations: none** (Section 2 explains why none was needed). **No other role's permission grant was changed.**

## 9. Remaining limitations (named honestly)

1. **No guided onboarding wizard** — a new owner still has to discover the fuel-grade → tank → dispenser → nozzle → payment-method → shift-template setup order themselves. Open since Phase 1/3.
2. **No payroll UI** — confirmed this phase to be a real gap, not merely "not verified" as Phase 1 put it. The backend API (`payroll_router`) is there; nothing in the frontend calls it.
3. **Accountant holds `shift_reconcile:record`** (the same permission Cashier/Shift Supervisor/Station Manager hold for recording a tender), which Phase 5 flagged as possibly wider than intended for that role — not changed, as narrowing it is a separate permission-model decision requiring its own approval, distinct from this phase's specific, narrow, pre-approved grant.
4. **No automated accessibility or responsive-viewport test suite** exists yet — unchanged since Phase 4/5's own honest notes on this.
5. **Design-system adoption (`DataTable`/`Skeleton`) remains partial** across the app — unchanged since Phase 4.

## 10. Decisions requiring owner approval (none exercised unilaterally this phase)

- Building a guided onboarding wizard (Section 7) — a real feature, not a quick fix.
- Building a payroll preview/management UI (Section 7) — same.
- Narrowing Accountant's `shift_reconcile:record` scope (Section 9, item 3) — a permission-model change, same approval bar as the Cashier fix had, not yet requested.
- Any of Phase 2/4's previously-flagged infrastructure items (distributed rate limiting, real HTTPS headers, a production domain) — unchanged, still gated on infrastructure that doesn't exist yet.

## 11. Recommended Phase 7

Given this phase closed the one specific, mandatory, owner-approved permission fix and also resolved two long-standing test flakiness issues, a reasonable next phase would focus on exactly one of Section 9's open items at a time rather than another broad sweep — most plausibly either the onboarding wizard (item 1) or the payroll UI (item 2), since both are the most visible remaining gaps between the backend's real capability and what a client can actually do through the product today.

## 12. Final verdict

**READY WITH DOCUMENTED LIMITATIONS.**

The mandatory deliverable — the Cashier/Operator permission fix — is implemented exactly as approved (two read-only permissions, no scope creep, verified against the real database and with 11 new backend tests plus 3 new frontend tests, all passing), safely reaches every existing client organization through the same idempotent, additive-only seed mechanism the project already relies on, and required no migration. The role-based workflow matrix is accurate and sourced from the real permission catalog. Two previously-unresolved test failures were genuinely fixed at their root cause rather than carried forward again. The honestly-reported gaps (no onboarding wizard, no payroll UI) are real, named, and recommended for a focused future phase rather than claimed as done or left unmentioned.
