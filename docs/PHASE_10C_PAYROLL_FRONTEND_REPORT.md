# Phase 10C — Payroll Frontend

Status: **implemented and locally tested. NOT DEPLOYED** — committed locally only, per the explicit instruction to stop before push/deploy.

## 1. Initial payroll backend audit (code-verified, not assumed from docs)

All payroll/salary/attendance code lives in one place: `backend/app/models/attendance.py` (models), `backend/app/schemas/attendance.py` (schemas), `backend/app/api/attendance.py` (both the attendance and payroll routers). There is no separate `payroll.py` model or service file.

### Models

- **`AttendanceRecord`**: `organization_id`, `station_id`, `user_id`, `attendance_date`, `status` (`AttendanceStatus`: `present`/`absent`/`late`/`half_day`/`leave`), `check_in_time`, `check_out_time`, `source` (always `"manual"`), `notes`, `recorded_by_user_id`. Unique `(station_id, user_id, attendance_date)`.
- **`PayrollRule`**: `organization_id`, `station_id`, `rule_name`, `shift_start_time`, `late_threshold_minutes` (default 15), `half_day_threshold_minutes` (default 120), `late_deduction_amount`, `absent_deduction_amount`, `half_day_deduction_amount` (all `Numeric(14,2)`), `is_active`. Unique `(station_id, rule_name)`. **`late_threshold_minutes`/`half_day_threshold_minutes` exist on the model but are never read anywhere in the salary-generation code** — attendance `status` is entered manually, not derived from check-in time by any backend logic found. The UI surfaces this honestly (see Section 3).
- **`SalaryRecord`**: `organization_id`, `station_id`, `user_id`, `period_start`, `period_end`, `base_salary`, `total_deductions`, `net_salary`, `days_present`, `days_absent`, `days_late`, `days_half_day`, `days_leave`, `notes`, `generated_by_user_id`, `is_finalized`. Unique `(station_id, user_id, period_start, period_end)`; `CHECK base_salary >= 0`, `CHECK total_deductions >= 0`.

**No employee salary-configuration entity exists anywhere** — `base_salary` is supplied fresh on every generate call, never persisted per-employee. **No payment-recording model** — `is_finalized` is the only lifecycle state past generation. **No leave-request/leave-balance entity** — `leave` is just one more attendance status with zero deduction effect. **No overtime field anywhere in the schema.**

### Existing salary calculation rules and deduction policy — exact code (`backend/app/api/attendance.py:277-289`)

```python
days_present = sum(1 for r in records if r.status == AttendanceStatus.PRESENT.value)
days_absent = sum(1 for r in records if r.status == AttendanceStatus.ABSENT.value)
days_late = sum(1 for r in records if r.status == AttendanceStatus.LATE.value)
days_half_day = sum(1 for r in records if r.status == AttendanceStatus.HALF_DAY.value)
days_leave = sum(1 for r in records if r.status == AttendanceStatus.LEAVE.value)

total_deductions = Decimal(0)
if active_rule:
    total_deductions += days_late * active_rule.late_deduction_amount
    total_deductions += days_absent * active_rule.absent_deduction_amount
    total_deductions += days_half_day * active_rule.half_day_deduction_amount
total_deductions = round_money(total_deductions)
net_salary = round_money(payload.base_salary - total_deductions)
```

**Confirmed: flat per-occurrence deduction, nothing else.** Each deduction type is `count × fixed_amount`, independently summed. No minutes, no hours, no percentage anywhere. Exactly one `PayrollRule` — the single `is_active=True` rule at the station — is applied; it is not matched per-employee. Leave days are counted (`days_leave`) but never subtracted. **This policy was not touched, not reinterpreted, and nothing in this phase calculates a deduction anywhere except the backend.** Confirmed by existing test evidence: `tests/test_attendance.py::test_salary_multiple_lates` (5 late days × 150.00 = exactly 750.00 deducted) and `test_salary_generation_with_deductions` (1 late@200 + 1 absent@1000 + 1 half-day@500 = 1700.00, independently summed).

### Capability matrix

| Feature | Existing endpoint | Existing service | Existing tests | Status |
|---|---|---|---|---|
| Employee payroll profile | — | — | — | **Not supported** — no dedicated entity; reuses `User` + role assignment |
| Salary configuration (persisted) | — | — | — | **Missing** — `base_salary` re-entered every generation, never stored |
| Payroll period | *(implicit in generate call)* | — | — | Partially — free-form `period_start`/`period_end`, no named period entity |
| Salary generation | `POST .../payroll/salary/generate` (`payroll:manage`) | `generate_salary` | `test_salary_generation_with_deductions`, `test_salary_multiple_lates`, others | Fully implemented — one employee at a time |
| Attendance integration | `POST/GET/PATCH .../attendance` | — | 10+ tests | Fully implemented |
| Late deduction | *(part of generate)* | flat, confirmed above | `test_salary_multiple_lates` | Fully implemented |
| Absence deduction | *(part of generate)* | flat, confirmed above | `test_salary_generation_with_deductions` | Fully implemented |
| Half-day calculation | *(part of generate)* | flat, confirmed above | `test_salary_generation_with_deductions` | Fully implemented — not prorated |
| Overtime | — | — | — | **Not supported** |
| Leave adjustment | *(counted only)* | — | — | Partially — counted, never deducted |
| Payroll approval | `PATCH .../salary/{id}/finalize` (`payroll:manage`) | — | `test_salary_finalize`, `test_double_finalize_rejected` | Partially — binary finalize only, no multi-step approval, no un-finalize |
| Payroll payment | — | — | — | **Not supported** — no model, no endpoint |
| Payroll history | `GET .../payroll/salary?user_id=` | — | — | Partially — only a `user_id` filter server-side |
| Salary statement | *(derived from the list)* | — | — | Partially — no dedicated endpoint |
| Payroll reports (org-wide) | — | — | — | **Not supported** — no cross-station aggregate exists |

### Permissions (`permission_codes.py`)

`ATTENDANCE_READ`, `ATTENDANCE_RECORD`, `PAYROLL_MANAGE` — held only by **Owner** (all permissions), **Station Manager**, and **Accountant**. Shift Supervisor, Cashier/Operator, Storekeeper/Technician, and Auditor/Viewer hold none of the three. **A single `PAYROLL_MANAGE` gates every payroll operation** — rules CRUD, generation, listing, and finalization all require the same permission; there is no separate view-only permission.

### Frontend before this phase

`frontend/lib/types.ts` already had `AttendanceRecord`, `PayrollRule`, `SalaryRecord` — field-for-field matching the backend, **no type changes were needed**. The existing attendance page (`.../attendance/page.tsx`) explicitly states *"Payroll rules are configured separately and are not part of this screen yet"* — confirming zero payroll UI existed before this phase.

## 2. Features implemented

A new station-scoped page, `/dashboard/org/{orgId}/station/{stationId}/payroll`, with four tabs:

- **Dashboard**: totals summed from this station's own salary records only (employees with a record, total gross, total deductions, total net, finalized vs. pending net) — explicitly labeled as a sum of listed records, not an organization-wide report (none exists).
- **Payroll Rules**: list, create, and edit flat per-occurrence deduction rules. The late/half-day *threshold-minutes* fields are editable (they're real schema fields) but each carries an explicit hint that they are **not yet used to auto-detect lateness** — attendance status is still entered manually, exactly matching the audited backend behavior.
- **Generate Salary**: employee + period + base salary + notes, a confirmation dialog before submission, and — after a successful generation — a deduction breakdown table (`count × flat amount = subtotal` for late/absent/half-day, using the exact backend-returned counts and the rule's own stored amounts) plus the backend's own `total_deductions`/`net_salary` figures. The breakdown is a display-only transparency aid built from two already-authoritative backend numbers multiplied together for presentation — nothing is sent back to the server, and it is only shown immediately after a fresh generation (see Section 5's limitation note on why it isn't reconstructed for historical records).
- **History**: filterable (employee, finalized/pending status, period-overlap date range — all client-side, since the backend only filters by `user_id`) list of salary records, a read-only "Statement" dialog (with a browser print button), and a "Finalize" action with its own confirmation dialog that correctly disappears once a record is finalized and handles the backend's own already-finalized rejection.
- **Nav integration**: a station-scoped "Payroll" item added to `components/AppShell.tsx`, gated on `payroll:manage`, following the exact pattern already used for "Attendance".

## 3. Features not implemented, and reasons

- **Employee salary configuration (persisted)** — not built; no backend entity exists to store it. Fabricating one client-side (e.g. in local storage) would create a second, unofficial source of truth for a number (`base_salary`) that must come from the backend at generation time — explicitly forbidden by "never fabricate salary figures."
- **Overtime** — not built anywhere in the UI; no field, no backend logic. Not invented.
- **Payroll payment recording** — not built; no model/endpoint exists. Building one would need a schema change (a payment model or fields on `SalaryRecord`), which Section 10 of the brief requires stopping for explicit approval on.
- **A richer "payroll approval" workflow beyond finalize** — the backend has exactly one lifecycle transition (`is_finalized: false → true`, one-way). The UI's "Finalize" action **is** the full approval surface this backend supports; nothing beyond it was added.
- **Org-wide payroll reports** — no backend endpoint aggregates payroll across stations; not built. The Dashboard tab is explicitly labeled as this station's own totals only.
- **Late-arrival auto-detection from check-in time, or any formula beyond `count × flat amount`** — explicitly forbidden by the brief and confirmed absent from the backend; not built under any name.
- **PDF export of the salary statement** — not supported by the backend; a frontend-only print-friendly view (`window.print()`) was built instead, which the brief explicitly allows ("A frontend print-friendly view may be implemented if it does not expose unauthorized information").
- **Roman Urdu translation** of the new page's content — not done, consistent with the same already-documented precedent noted in Phases 10a/10b.

## 4. Files created and modified

**Frontend (new)**:
- `frontend/app/dashboard/org/[orgId]/station/[stationId]/payroll/page.tsx` — the entire feature.
- `frontend/e2e/payroll.spec.ts` — 4 new Playwright tests.

**Frontend (modified)**:
- `frontend/components/AppShell.tsx` — added the "Payroll" nav item.
- `frontend/lib/i18n/translations.ts` — added the `nav.payroll` key.

**`frontend/lib/types.ts` — no changes.** `AttendanceRecord`, `PayrollRule`, `SalaryRecord` already existed and already matched the backend exactly.

**Backend: no files created or modified.** Confirmed via `git status --short backend/` before writing this report — empty.

## 5. Existing API endpoints reused (no new endpoints)

`GET/POST /organizations/{org}/users` (employee picker, reused from the existing Staff module), `POST/GET/PATCH /organizations/{org}/stations/{sid}/attendance` (attendance records, used read-only by this phase), `POST/GET/PATCH /organizations/{org}/stations/{sid}/payroll/rules`, `POST /organizations/{org}/stations/{sid}/payroll/salary/generate`, `GET /organizations/{org}/stations/{sid}/payroll/salary`, `PATCH /organizations/{org}/stations/{sid}/payroll/salary/{id}/finalize`.

## 6. Backend changes

**None.**

## 7. Database migrations

**None created, none needed.** No model or schema change was required for anything built in this phase.

## 8. Multi-tenant security verification

- Every payroll request goes through `authFetch` with the real bearer token; every backend endpoint still goes through `require_permission(PAYROLL_MANAGE)` resolving `organization_id`/`station_id` from the URL path — the frontend never computes or trusts a permission decision itself.
- The page is gated on `can("payroll:manage")` with the standard `AccessDenied` fallback; there is no separate read-only payroll view because the backend itself has no separate read permission (confirmed in the audit, not assumed).
- Support sessions are unaffected — this phase added no superuser bypass of any kind; `usePermissions` is the same shared hook every other phase since 8c already uses, with its existing support-session scope-matching behavior untouched.

## 9. Restricted-role testing (real roles, not just superuser)

Three Playwright tests specifically verify this, against real, non-superuser, role-scoped users seeded in `global-setup.ts`:
1. **Cashier / Operator** (holds none of `attendance:read`/`attendance:record`/`payroll:manage`) gets `Access restricted` on a brand-new station's payroll page.
2. **Station Manager** (holds `payroll:manage`, but granted only at station 1 and station 3 in the seed data) gets `Access restricted` at a brand-new, unrelated station — proving station-level isolation, not just organization membership.
3. The **same** Station Manager **does** see the real payroll page at station 1, where their role is actually granted — proving the restriction in test 2 is a real authorization boundary, not a broken page.

## 10. Backend test results

No backend code was changed. Full suite executed once, alone (see Section 14 for why): **362 passed, 3 warnings, 0 failures, 0 errors** in 1188.06s (0:19:48). The 3 warnings are the same pre-existing Pydantic decimal-serialization warnings noted in every prior phase's report, unrelated to payroll.

## 11. Playwright test results

New: `frontend/e2e/payroll.spec.ts` (4 tests) — the main end-to-end test creates a dedicated station and employee, records a controlled attendance mix (2 present, 1 absent, 2 late, 1 half-day, 1 leave) via the real API, creates a payroll rule (150/1000/500 flat), generates salary through the UI, and asserts the exact expected math: 2×150 + 1×1000 + 1×500 = **1,800.00** total deductions, net = 50,000.00 − 1,800.00 = **48,200.00** — verified both in the generation result and again in the History tab and Dashboard totals. Also asserts leave is never deducted, finalization locks the record, and the statement dialog shows the right employee.

Full suite (9 spec files, 51 tests total): **51 passed, 0 failed** at `--workers=3`. (The default 7-worker run was not used this phase, since the same pre-existing login-concurrency flake documented in Phases 10a/10b is already a known, unrelated issue — confirmed clean at reduced concurrency instead, consistent with how that flake has been handled every time it's appeared.)

One real test bug caught and fixed during this phase (not a product bug): the employee created via `POST /organizations/{org}/users` didn't appear in the payroll page's employee picker at first. Investigation showed `GET /organizations/{org}/users` **inner-joins on `UserStationRole`** — a user with no role assignment at all is excluded from this listing entirely, by design, matching how the pre-existing Attendance page already behaves. Fixed by granting the test employee a role at the new station, exactly as a real new hire would need anyway to ever log in or be assigned shifts. Worth noting as a **genuine, pre-existing UX subtlety** (not introduced by this phase): a petrol station owner must assign a role to a new employee before that employee can be selected for payroll, even though the payroll feature itself doesn't need the employee to have any login capability — documented in `REMAINING_RISKS.md`.

## 12. Test database isolation verification

Verified directly, not assumed:

```
docker compose exec backend printenv | grep DATABASE_URL
  -> postgresql+asyncpg://cynvexa:cynvexa@db:5432/cynvexa

grep DATABASE_URL docker-compose.yml backend/.env
  docker-compose.yml:  DATABASE_URL: postgresql+asyncpg://cynvexa:cynvexa@db:5432/cynvexa
  backend/.env:        DATABASE_URL=postgresql+asyncpg://cynvexa:cynvexa@localhost:5432/cynvexa
```

**Confirmed: isolation cannot be established in this environment.** `backend/tests/conftest.py` only falls back to a literal `cynvexa_test` URL when `DATABASE_URL` is *unset* (`os.environ.setdefault(...)`) — since this Docker Compose setup always sets `DATABASE_URL` to the real local dev database (`cynvexa`, same host, same container), pytest's session-scoped schema-reset fixture and the Playwright e2e stack are **not** isolated from each other. No `TEST_DATABASE_URL` or equivalent exists anywhere in this repo's configuration.

**Consequence hit during this phase** (a real incident, not a hypothetical): the Phase 10B pytest run's `DROP SCHEMA public CASCADE` / `Base.metadata.create_all` fixture — run against this shared dev database — recreated every table directly from the current ORM models, **bypassing Alembic entirely** and leaving the `alembic_version` table empty. On the next `docker compose up`, the backend container's entrypoint (`alembic upgrade head`) tried to run every migration from scratch against tables that already existed, crash-looping on `DuplicateTableError: relation "organizations" already exists`.

**Recovery** (non-destructive, verified safe): confirmed `alembic current` was empty while `alembic heads` showed the expected head revision, and the existing tables already matched the current ORM model shape (since `create_all` had just built them from those same models) — so `alembic stamp head` (records the revision without executing any DDL) was the correct fix, not a migration or a schema rebuild. Ran via `docker compose run --rm --entrypoint sh backend -c "alembic stamp head"`, confirmed `alembic current` then matched `alembic heads`, confirmed the backend container started and passed `/health` cleanly afterward, then re-ran `python -m app.seed permissions-roles` or confirmed. **No tables were dropped, no production system was touched** (this is purely the local Docker Compose dev stack; Render/Neon production is entirely separate infrastructure and was never reachable from this environment).

**Safe process followed for this phase, per the brief's instruction 5** ("if isolation cannot be confirmed, run the suites sequentially"): the full backend pytest suite was run completely alone — confirmed via process inspection inside the container (no Playwright process was touching the stack) — and only after it fully exited was the Playwright suite started, also alone. This was verified by literally checking the running process list inside the backend container before starting each suite, not assumed from timing.

**Recommendation, not auto-applied this phase** (a config change, out of scope for "payroll frontend"): add a dedicated `TEST_DATABASE_URL`-aware test database to `docker-compose.yml` (a second Postgres database or a second compose service) so this hazard cannot recur even if someone forgets to run the suites sequentially. Flagged in `REMAINING_RISKS.md` as a standing follow-up, not fixed here since it's an infrastructure change outside this phase's "payroll frontend" scope and wasn't requested.

## 13. Typecheck and build results

`docker compose build frontend` → `next build` (Next.js 16.4.3, Turbopack): **compiled successfully, TypeScript passed with zero errors**, `/dashboard/org/[orgId]/station/[stationId]/payroll` listed in the route output.

## 14. Git diff summary

```
docs/REMAINING_RISKS.md                 | modified (new Phase 10c section)
docs/PHASE_10C_PAYROLL_FRONTEND_REPORT.md | new (this file)
frontend/app/.../payroll/page.tsx       | new
frontend/e2e/payroll.spec.ts            | new
frontend/components/AppShell.tsx        | modified (nav item only)
frontend/lib/i18n/translations.ts       | modified (one key only)
```

Reviewed before commit: no backend files touched, no secrets, no unrelated changes. Existing login page, attendance functionality, and salary calculation policy are byte-for-byte unchanged — confirmed by `git diff` showing zero lines touched in `app/login/page.tsx`, `backend/app/api/attendance.py`, or any payroll-calculation code.

## 15. Local commit hash

Committed locally after this report — hash given in the final response, per the brief's Section 13 format.

## 16. Deployment status

**NOT DEPLOYED.** No push, no Render deploy, no production migration.

## 17. Remaining risks

New, from this phase:
- The 7 genuine backend gaps from the capability matrix (no persisted salary config, no overtime, no payment recording, binary-only finalize, station-only history filter, no dedicated statement endpoint, no org-wide payroll report) remain open — each is a real, scoped follow-up, most requiring a schema change and therefore explicit approval before implementation.
- **No test-database isolation exists in this Docker Compose setup** — now documented with a concrete recovery incident and recommendation in `REMAINING_RISKS.md`. Until a dedicated test database is configured, backend pytest and the Playwright stack must always be run sequentially, never concurrently, against this stack.
- An employee must already hold a role/station assignment to appear in the payroll employee picker (reusing the existing, pre-Phase-10C `GET /organizations/{org}/users` behavior) — not a defect introduced here, but worth a staff onboarding-order note.

## 18. Recommended next step

Review this report and the live page locally (`docker compose up`, `/dashboard/org/{orgId}/station/{stationId}/payroll` as Owner/Station Manager/Accountant). If approved: push, verify Render auto-deploy (health/ready + route-availability only, same limitation as every prior phase), and separately consider whether the test-database-isolation fix (a `docker-compose.yml`/config change, not a payroll feature) should be its own small, explicitly-approved follow-up before the next phase touches the backend test suite again.
