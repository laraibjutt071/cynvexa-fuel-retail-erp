# CYNVEXA — Final Product Audit (Phase 1)

**Date:** 2026-11-15
**Scope:** Phase 1 only — factual, evidence-based audit. No application code, schema, migrations, or permissions were changed while producing this document. No hosting, DNS, or paid services were purchased or configured.
**Method:** Every claim below is backed by one of: a command actually run against the real running stack (Docker Compose, real PostgreSQL 16), a file actually read, or an agent sub-task that read files and reported verifiable specifics (API paths, permission strings, line-level findings). Nothing is marked "complete" based solely on a file's existence.

---

## 1. Automated test results (exact)

### 1.1 Backend — pytest against real PostgreSQL 16

Run inside the actual `backend` container, against a dedicated `cynvexa_test` database on the same Postgres instance the app uses (not SQLite, not mocked).

```
230 passed, 0 failed, 0 skipped, 0 errors
3 warnings (non-fatal — see below)
Exit code: 0
Duration: 503.36s (8 min 23 sec)
```

The 3 warnings are Pydantic `UserWarning`s in `tests/test_attendance.py` (`test_duplicate_payroll_rule_name_rejected`, `test_update_payroll_rule`): a decimal field serializing an `int` value of `0` instead of `Decimal("0")`. Not a test failure, but worth a one-line fix (construct the default as `Decimal("0")`, not `0`) since this codebase otherwise enforces Decimal discipline strictly.

**This closes a HIGH-priority open risk** recorded in `docs/REMAINING_RISKS.md` ("Pilot Day 2" section): *"Backend tests not executed against a real database this session... run the full suite against a real Postgres before pilot launch."* That has now been done, with the result recorded here.

### 1.2 Frontend — TypeScript check

```
npx tsc --noEmit
```
Zero errors, zero output. Confirms the baseline's "0 TypeScript errors" claim — verified independently, not copied.

### 1.3 Frontend — production build

```
npm run build
```
```
✓ Compiled successfully in 2.8s
✓ TypeScript finished in 4.4s
✓ Generating static pages (8/8)
Exit code: 0
```
All 16 routes (15 page files + root `/`) built successfully — 8 static, 8 server-rendered-on-demand. This is a **separate, stronger check** than the typecheck alone: it also catches build-time import errors, invalid static-generation attempts, and bundler failures that `tsc` alone would miss. Both passed cleanly.

### 1.4 Dependency security scan

- **Frontend:** `npm audit --omit=dev` → **0 vulnerabilities**.
- **Backend:** `pip-audit` → **12 known advisories, all on one package: `starlette` 0.47.2** (fix versions 0.49.1 / 1.0.1 / 1.1.0 / 1.3.0 / 1.3.1). This is a **new finding**, not previously documented — `docs/REMAINING_RISKS.md` records a *prior* starlette bump (0.41.3→0.47.2) that fixed an earlier CVE set; newer advisories have since been published against 0.47.2 itself. Starlette is a transitive dependency of FastAPI, so the fix is a FastAPI version bump, not a direct pin — this needs its own verification pass (does the newer FastAPI/Starlette break anything the 230 tests cover?) before it's applied, which is Phase 2+ work, not this audit. **Flagged as a Critical/High item in Section 6.**

---

## 2. Live API surface (actual, not copied from the baseline)

Counted directly from the running backend's `/openapi.json`:

| Metric | Baseline claim | Actual (this audit) |
|---|---|---|
| Path entries | 108 | **126** |
| Operations | 173 | **169** |

Both numbers differ from the baseline report. Paths are higher (126 vs. 108) and operations are slightly lower (169 vs. 173) than claimed. This is not a red flag by itself — API surfaces grow between reports — but it confirms the baseline numbers should not be trusted without re-counting, which is why this audit re-counted rather than citing them.

---

## 3. Frontend page inventory — all 16 routes mapped to APIs, permissions, workflow

Fifteen page files exist under `frontend/app/` plus the root redirect. Each was read directly (not inferred) for its real `authFetch`/`fetch` calls, its `can()`/permission checks, and its actual rendering logic (loading state, error state, empty state, stubs).

| Page | Backend APIs called | Permission gates | Business workflow | Status |
|---|---|---|---|---|
| `app/page.tsx` | none | none | Redirects to `/dashboard` or `/login` based on session | **Complete and verified** |
| `dashboard/page.tsx` | `GET /organizations`, `GET /organizations/{id}/stations`, `POST /organizations` | `report:read`, `audit:read`, `supplier_ledger:read`, `credit_collection:read`, `expense:read`, `inventory_item:read`, `station:read`; org-create form is superuser-only | Lists orgs/stations; auto-redirects single-station owners to `/today` | **Complete and verified** |
| `dashboard/org/[orgId]/page.tsx` | `/reports/pending-approvals`, `/suppliers/balances`, `/credit-customers/balances`, `/expenses` (+approve/reject), `/audit-log` | `report:read`, `supplier_ledger:read`, `credit_collection:read`, `expense:read`, `expense:approve`, `audit:read` | Org-level dashboard: exceptions, supplier/credit balances, expense approval, audit trail | **Complete and verified** |
| `dashboard/org/[orgId]/credit-customers/page.tsx` | `GET/POST /credit-customers`, `/balances`, `/{id}/statement`, `/ageing` | `credit_customer:manage`, `credit_collection:read` | Manage credit accounts, statements, ageing buckets | **Complete and verified** |
| `dashboard/org/[orgId]/settings/page.tsx` | `/auth/password`, `/auth/sessions`, `/auth/logout-all`, `/subscription`+payments, `/expense-categories`, `/users`, `/roles`, `/stations`, `/users/{id}/roles` | `subscription:read`, `expense:approve`, `user:read`, `user:create`, `user:assign_role` | Account settings, billing view, expense categories, user/role management | **Complete and verified** |
| `station/[stationId]/page.tsx` | `/reports/daily-fuel-sales`, `/reports/tank-variance`, `/reports/shift-reconciliation`, `/inventory-items`, `/inventory-movements` | `report:read`, `inventory_item:read`, `inventory_movement:adjust`, `inventory_item:manage` | Station dashboard: sales/variance/reconciliation reports, inventory | **Complete and verified** |
| `station/[stationId]/today/page.tsx` | (station overview aggregation endpoints) | `report:read` | "Today's Overview" real-world dashboard cards | **Complete and verified** (pre-existing, confirmed working in earlier session) |
| `station/[stationId]/daily-entry/page.tsx` + `ReadingsSection`/`SalesSection`/`ExpensesSection`/`CashSection`/`ReviewSection` | `/shifts`, `/tank-readings`, `/nozzle-readings`, `/tenders`, `/payment-methods`, `/credit-customers`, `/expenses`, `/cash-movements`, `/reconciliation`, `/shifts/{id}/approve` | None at page level (relies on backend `require_permission`) | Guided 5-step shift workflow: readings → sales → expenses → cash → review | **Complete and verified** (see Section 4 for usability gaps — functional ≠ optimally guided) |
| `station/[stationId]/tanks/page.tsx` | `GET /tanks`, `GET /fuel-grades`, `PATCH /tanks/{id}` | `tank:manage` (gates Edit only) | View tanks, edit calibration/location | **Partially implemented** — no create form here (lives on station settings instead); duplicates the tank list already shown on settings, a redundant surface |
| `station/[stationId]/purchases/page.tsx` | `/tanker-receipts`, `/tanks`, `/suppliers`, `/tanker-receipts/{id}/record-unload`, `/{id}/approve` | **None visible in the UI** | Record tanker delivery → unload reading → approve into stock | **Partially implemented** — record/approve buttons render for every viewer regardless of role; relies entirely on a backend 403 rather than hiding the action |
| `station/[stationId]/reading-corrections/page.tsx` | `GET /shifts`, `GET/PATCH /reading-corrections/{id}/approve`, `/reject` | None visible | Approve/reject reading-correction requests | **Partially implemented** — **no UI exists to submit a correction request at all**, only to approve/reject one created elsewhere (API/future UI); uses `window.prompt()` to collect a rejection reason on a financial-audit-relevant action |
| `station/[stationId]/attendance/page.tsx` | `GET /users`, `GET/POST /attendance` | **None visible** | Record and view daily attendance | **Partially implemented** — no frontend permission gating at all (backend-only enforcement); despite the nav label implying "Attendance & Payroll," no payroll preview/calculation UI exists on this page or anywhere else |
| `station/[stationId]/settings/page.tsx` | Station profile `PATCH`, `/fuel-grades` CRUD, `/tanks` CRUD, `/shift-templates` CRUD, tolerance `PATCH` | **None visible** | Configure station profile, fuel grades, tanks, shift templates, tolerances | **Partially implemented** — no frontend permission gating; **no dispenser management UI, no nozzle management UI, no payment-method management UI anywhere in the frontend** (confirmed by repo-wide search — these are backend-only resources today) |
| `dashboard/platform/page.tsx` | `/platform/plans`, `/organizations`, `/platform/subscriptions`, `/platform/organizations/{id}/subscription`, payments | Route-gated: non-superusers redirected away | Platform admin manages plan catalog, org list, subscriptions/billing | **Complete and verified** |
| `login/page.tsx` | `POST /auth/login` | n/a | Sign-in | **Complete and verified** (redesigned this session; build + typecheck clean) |
| `register/page.tsx` | `GET /plans`, `POST /auth/register` | n/a | Self-service org + owner sign-up | **Complete and verified** — this **supersedes** `docs/SAAS_GAP_ANALYSIS.md`'s "not built" note on self-service registration, which is now stale (the feature shipped in a commit after that doc was written) |

### Cross-cutting findings from the page inventory

- **Permission gating is inconsistent across the frontend.** Org/station dashboards, credit-customers, settings, and tanks hide actions by permission. Purchases, attendance, station-settings, and reading-corrections show every mutating action to every viewer regardless of role and rely entirely on the backend returning 403. The backend boundary holds either way (confirmed by the dedicated isolation/RBAC test files), but the UI experience is inconsistent — a cashier can see an "Approve" button they'll be rejected for clicking, which is confusing for a non-technical user, directly contradicting the "no demonstration needed" goal.
- **`window.prompt()` / `window.alert()`** are used for real business actions (expense rejection reason, reading-correction rejection reason) rather than a proper form/dialog. Inconsistent with "premium ERP," and inaccessible on some mobile browsers.
- **Confirmed absent UI surfaces** (not partial, not stubbed — genuinely no code path exists): dispenser management, nozzle management, payment-method management, and reading-correction **request submission** (only approval/rejection of an existing request exists in the UI).

---

## 4. Daily Entry — the 5-step workflow, as it actually exists

`station/[stationId]/daily-entry/page.tsx` implements: **Readings → Sales → Expenses → Cash → Review**, with:
- A visible step progress bar (`DailyEntryProgress`, hand-rolled — not the shared `ProgressSteps` component)
- Per-section inline help text pulled from i18n (`dailyEntry.help.*`)
- An empty state ("Nothing recorded for this business date") with a clear call-to-action ("Start today's entry") when no shift exists yet
- A hard rule (confirmed in `docs/ASSUMPTIONS.md` #36) that a new entry can only be started for the station's actual "today" — a past empty date shows an explanatory message instead of a create button, preventing silent mis-dated shifts
- Station-timezone-aware business-day resolution (`stationDateIso`), not the browser's local date — a real defect found and fixed in a prior phase (`docs/REMAINING_RISKS.md` item 1)

**Real, verified usability gaps** (per the brief's own 10-step target workflow):
1. **No explicit "confirm station" step** — the station is implicit from the URL, with no on-screen confirmation before data entry begins. Low risk for a single-station owner, real risk for a multi-station user who navigated here from a bookmark or old tab.
2. **No explicit "review opening readings" step** — opening readings are shown inline inside the Readings section, not as their own confirmation step before closing entry begins.
3. **No discrepancy-resolution step in the guided flow** — variance/discrepancy handling exists elsewhere (reconciliation, reading corrections) but is not surfaced as part of this guided sequence, so a cashier hitting a variance has to know to look elsewhere.
4. **The progress bar and tab strip are two different hand-rolled UI patterns doing overlapping jobs** (a step list that doesn't let you jump, plus a tab strip that does) — not wrong, but not the shared `ProgressSteps` component, so it's inconsistent with whatever Phase 6 standardizes.
5. **One shift per business day is a frontend convention, not a backend rule** (`docs/ASSUMPTIONS.md` #34) — a station genuinely running two shifts a day will only see one of them here; the underlying per-shift pages still work but aren't linked from this guided flow.

This is a **materially more complete implementation than the brief's framing implied** — it is not a bare form, it already has guided structure, help text, and real validation-aware UX (e.g., it was previously fixed to reject a closing totalizer lower than the opening one, per `docs/REMAINING_RISKS.md` item 4). The gaps above are refinements, not a rebuild.

---

## 5. Roles and permissions (as seeded and enforced today)

Source: `backend/app/core/permission_codes.py::SEED_ROLES`, cross-checked against `docs/ASSUMPTIONS.md` #11.

| Role | Scope of permissions (summary) |
|---|---|
| **Owner** | Every permission in the system (`list(ALL_PERMISSIONS.keys())`) — full control |
| **Station Manager** | Station config, receipts (create+approve), shifts (open/close/approve), reading corrections (request+approve), reconciliation, supplier ledger, credit collections, expenses (record+approve), inventory, reports, attendance, payroll |
| **Shift Supervisor** | Narrower than Station Manager: receipts, shifts, reading corrections, reconciliation recording, inventory — **no** expense approval, no payroll, no supplier-ledger recording |
| **Cashier / Operator** | Shift open/close, recording-level actions only — confirmed **not** included in reading-correction authorization (`docs/ASSUMPTIONS.md` #38: "Station Manager, Shift Supervisor, Owner — NOT Cashier") |
| **Accountant** | Financial oversight: `shift_reconcile:approve`, `supplier_ledger:approve`, `expense:approve`, `subscription:read` — the only non-Owner role with cash-variance and supplier-payment approval authority, matching the blueprint's literal §12 text |
| **Storekeeper / Technician** | Physical-equipment master data (`tank:manage`, `dispenser:manage`, `nozzle:manage`) plus receipt creation |
| **Auditor / Viewer** | Read-only across the system — no mutating permission |

This is a reasonable, already-implemented match for the brief's Phase 7 role model (Platform Admin / Owner / Station Manager / Accountant / Cashier). One real gap: **the frontend does not yet expose a UI to manage dispensers, nozzles, or payment methods**, so the Storekeeper/Technician role and the payment-method configuration workflow are backend-complete but **frontend-incomplete**.

All seed roles are explicitly marked `OPEN (seed only, not final)` in `docs/ASSUMPTIONS.md` #11 — they are owner-editable defaults, not hardcoded, and the brief's Phase 7 role model should be treated as a refinement of this, not a replacement.

---

## 6. Design system adoption (confirmed by actual usage count, not file existence)

`frontend/components/ui/` contains a real, reasonably complete shared component set: `Badge`, `Button`, `DataTable`, `Dialog`, `DropdownMenu`, `EmptyState`, `Field`, `PageHeader`, `ProgressSteps`, `Skeleton`, `StatCard`, `Tabs`, `Toast`.

Actual usage across all `app/` page files:

| Component | Pages using it |
|---|---|
| `EmptyState` | 2 of 16 (daily-entry, purchases) |
| `StatCard` | 1 of 16 (today) |
| `DataTable` | **0 of 16** |
| `Skeleton` | **0 of 16** |
| `ProgressSteps` | **0 of 16** (daily-entry hand-rolls its own step bar instead) |

**This is a real, significant gap for Phase 6**, not a minor one. Every table in the app is a hand-rolled `<table>`, every loading state is an ad-hoc "Loading…" string rather than a skeleton, and the one multi-step workflow that would most benefit from the shared `ProgressSteps` component doesn't use it. The components exist and look complete in isolation — they are simply not wired into the product yet. Phase 6 should treat this as "adopt the existing system across pages," which is lower-risk than building a new one, but it is real work across ~14 pages, not a find-and-replace.

---

## 7. Onboarding / tutorial / contextual help — confirmed absent

Repository-wide search for onboarding, tutorial, walkthrough, and help-panel patterns across `app/`, `components/`, and `lib/` returned **zero genuine matches** — the only hits were Recharts `<Tooltip>` usage inside chart components (`components/charts/*.tsx`), which is an unrelated charting-library feature, not user-facing contextual help.

Confirmed present, short of a full onboarding system:
- Per-section inline help text on Daily Entry (i18n-driven, `dailyEntry.help.*`)
- Descriptive empty states in a few places (daily-entry, purchases, dashboard)
- `docs/REMAINING_RISKS.md` and `docs/ASSUMPTIONS.md` both independently and explicitly list "onboarding tour" as a known, not-yet-built gap (not a new finding — this audit confirms a gap the team had already named, rather than discovering a hidden one)

**Conclusion:** Phase 3 (onboarding) and most of Phase 4 (contextual help beyond Daily Entry) are genuinely greenfield work, not a tweak to something partially built. This matches the brief's own framing of Phase 3 as "highest priority."

---

## 8. Reconciliation with existing audit documents (not duplicated, cross-checked)

| Existing doc | What it already covers | What this audit adds/changes |
|---|---|---|
| `docs/REMAINING_RISKS.md` | 11 production-readiness findings (local-disk storage, migration races, single-instance rate limiter, missing indexes [fixed], CVEs [fixed then], file-upload validation [fixed], root containers [fixed], idempotency gaps, inventory valuation) | **Closes** the "tests not run against real Postgres" item (now run: 230/230 pass). **Adds** a new CVE finding: starlette 0.47.2 has 12 current advisories (the prior fix round is now itself outdated). Confirms the local-disk storage and single-instance rate-limiter risks are still open and unchanged. |
| `docs/SAAS_GAP_ANALYSIS.md` | Platform admin, subscription/billing, onboarding wizard (not built), plan-limit enforcement (not built), light/dark mode, real Urdu RTL, PDF/Excel export, notifications, marketing pages | **Updates one line as stale**: self-service org registration, listed as "Not built" in that doc (dated 2026-11-01), **is now built and verified** (`register/page.tsx`, confirmed working, matches the `git log` entry "Add self-service organization registration (sign-up)"). All other gaps in that doc remain open — not re-verified individually in this pass, since they weren't in this audit's required scope. |
| `docs/CLOUD_DEPLOYMENT_PLAN.md` | A concrete, budget-compliant (PKR 4,000/month) single-VPS architecture: Hetzner/DigitalOcean/Contabo options, Caddy reverse proxy with automatic HTTPS, port exposure table, production Docker Compose differences, backup strategy (daily `pg_dump -Fc`, 7-day rotation), VPS-level hardening checklist | Confirmed as **plan only** — explicitly stated in the doc itself, re-confirmed here: no VPS has been purchased, no domain registered, no DNS configured, nothing deployed publicly. This audit did not touch deployment infrastructure, per the brief's explicit instruction. |

---

## 9. Feature matrix (summary)

Status definitions used throughout: **Complete and verified** (read the code, confirmed real logic/API calls/error handling, and — where applicable — build/test passed), **Partially implemented** (real but incomplete — missing a sub-flow, missing permission gating, or missing a companion UI), **Missing** (no code path exists), **Broken** (exists but demonstrably doesn't work), **Not verified** (could not be confirmed without executing a workflow this audit didn't run).

| Area | Status | Basis |
|---|---|---|
| Multi-tenant org/station isolation | Complete and verified | Dedicated test file (200 lines), 230/230 suite green |
| RBAC enforcement (backend) | Complete and verified | Dedicated test file (148 lines), permission model read directly |
| RBAC enforcement (frontend UI gating) | Partially implemented | 4 of 16 pages gate actions by permission; the rest rely on backend-only enforcement (safe, but not user-friendly) |
| 24-hour reading-lock policy | Complete and verified | Code read confirms server-side UTC timestamps, exact deadline constant, no bypass path; `ASSUMPTIONS.md` #38 marks it CONFIRMED by owner |
| Fuel/tank/stock ledger core | Complete and verified | Covered by passing test suite; `ASSUMPTIONS.md` items #1–#9 document deliberate design choices, not gaps |
| Tanker receipts & suppliers | Partially implemented | Backend solid; frontend purchases page lacks permission-based UI gating (Section 3) |
| Credit customers | Complete and verified | Full CRUD, statements, ageing, limit enforcement confirmed (`ASSUMPTIONS.md` #22) |
| Expenses & approvals | Complete and verified (with a UX wart) | Functional; uses `window.prompt()` for rejection reason |
| Attendance | Partially implemented | Recording works; no frontend permission gating; "Payroll" implied by nav label but no payroll UI found |
| Payroll | Not verified | Backend migration (`b2c3d4e5f6g7_day4_attendance_payroll.py`) and model exist; no frontend page found exposing payroll calculation/preview — needs a direct check in Phase 2, not assumed broken |
| Reports | Complete and verified | Daily fuel sales, tank variance, shift reconciliation all called with real data from the station dashboard |
| Audit logs | Complete and verified | Filterable, exportable, confirmed on org dashboard |
| Reading corrections | Partially implemented | Approve/reject UI exists; **request-submission UI is missing entirely** |
| Dispenser/nozzle/payment-method management | Missing (frontend only) | Backend models and permissions exist; no page anywhere exposes CRUD for these |
| Self-service org registration | Complete and verified | Confirmed working; corrects a stale "not built" note in `SAAS_GAP_ANALYSIS.md` |
| Platform admin (plans/subscriptions) | Complete and verified | Dedicated page, route-gated, clean implementation per the fork's inspection |
| Onboarding / tutorial system | Missing | Confirmed by repo-wide search — zero matches beyond unrelated chart tooltips |
| Contextual help (beyond Daily Entry) | Partially implemented | Daily Entry has it; most other pages don't |
| Shared design system adoption | Partially implemented | Components exist; used in 0–2 of 16 pages depending on component |
| Login page | Complete and verified | Redesigned this session; build + typecheck clean |
| Playwright/e2e coverage | Not verified | `docs/REMAINING_RISKS.md` itself notes e2e tests exist for some workflows (7 passing, referenced) but not for reading-corrections, tanks, or credit-customers pages (added later); this audit did not re-run the Playwright suite (out of this pass's required scope — tests #1 and #2 of this brief named pytest/tsc/build specifically, not Playwright) |
| Cloud deployment | Not started (by design) | Plan exists and is budget-compliant; nothing purchased or deployed, per explicit instruction |
| Backup/restore | Not verified | `pg_dump` strategy is planned in `CLOUD_DEPLOYMENT_PLAN.md`; no backup has actually been taken or restored against this or any database — this is a real, unverified gap, not a "planned = done" claim |

---

## 10. Critical and high-priority gaps (ranked)

1. **[HIGH] Starlette 0.47.2 has 12 known current advisories.** Needs a FastAPI/Starlette version bump and a full test-suite re-run before pilot — not done in this audit (code-change-free by design), flagged for Phase 2.
2. **[HIGH] No onboarding or contextual-help system exists.** This is the brief's own stated highest priority (Phase 3) and is confirmed greenfield, not partially built.
3. **[HIGH] Inconsistent frontend permission gating.** Several pages (purchases, attendance, station-settings, reading-corrections) show every action to every role and depend entirely on a backend 403. Safe, but directly undermines "no demonstration needed for a non-technical user" — a cashier seeing a button they can't use is confusing, not self-explanatory.
4. **[HIGH] No UI exists to submit a reading-correction request.** Only approval/rejection exists. Without this, the carefully-built 24-hour correction policy (`ASSUMPTIONS.md` #38) has no front door for the people who'd actually use it under time pressure.
5. **[MEDIUM] No dispenser, nozzle, or payment-method management UI.** Backend-complete, frontend-absent — a station cannot be fully configured through the UI alone without someone calling the API directly.
6. **[MEDIUM] Shared design system (`DataTable`, `Skeleton`, `ProgressSteps`) is built but essentially unused.** Real Phase 6 work, not a polish pass.
7. **[MEDIUM] Payroll UI not found; needs a direct, dedicated check** (not assumed broken, genuinely not verified) before Phase 2 planning assumes it exists or doesn't.
8. **[MEDIUM] `window.prompt()`/`window.alert()` used in two real financial workflows.** Quick, low-risk fix once Phase 6 touches those pages.
9. **[LOW–MEDIUM, carried over, unchanged] Local-disk evidence storage, single-instance rate limiter, migration-on-boot race, no server-side idempotency key for create endpoints** — all previously documented in `docs/REMAINING_RISKS.md`, all still open, none newly discovered, none contradicted by this audit.
10. **[LOW, carried over] No backup has actually been taken or restored.** The plan is sound; it has not been executed even once, so "we can recover" is not yet an evidenced claim.

---

## 11. Deployment blockers (explicit)

None of these were touched, purchased, or configured in this audit, per instruction. Listed so Phase 11/12 planning starts from a clear, honest baseline:

- No VPS provisioned (provider choice — Hetzner/DigitalOcean/Contabo — needs owner decision per `CLOUD_DEPLOYMENT_PLAN.md`)
- No domain registered, no DNS configured
- No production secrets generated (JWT secret, DB password are dev values only)
- No HTTPS/TLS anywhere — current stack is plain HTTP on localhost
- No backup has ever been taken or restored against this data
- The starlette CVE set (Section 1.4) should be resolved before any public exposure, not after

---

## 12. Explicitly not verified in this audit

Being direct about the boundary of what was actually checked, per the instruction not to round up:

- **Playwright/e2e suite** — not re-run this pass (pytest/tsc/build were the three checks this audit's instructions named explicitly)
- **Payroll calculation/preview UI** — existence/correctness not directly confirmed; flagged, not assumed either way
- **Manual, click-through testing of any page in a real browser** — this audit read code and ran automated checks (pytest, tsc, build, OpenAPI introspection); it did not drive the UI with a mouse/keyboard this pass. The login page and dashboard were previously confirmed reachable via `curl` (HTTP 200) in an earlier session, not full interaction-tested here.
- **Mobile/tablet responsive behavior** — not tested this pass
- **WCAG/accessibility audit** — `docs/REMAINING_RISKS.md` already states this was never done beyond one spot-fix; not re-attempted here
- **Backup restore drill** — not performed
- **Load/performance testing** — not performed (prior index-benchmark evidence in `REMAINING_RISKS.md` is real but narrow, as that doc itself says)
- **Actual multi-replica behavior** — the known single-instance assumptions (rate limiter, migrations, local storage) were read and confirmed to still be true in the code, but not stress-tested against a real second replica

---

## 13. Recommended Phase 2–7 execution sequence

Based on the gaps actually found (Section 10), not the brief's original phase numbering, which assumed less was already built than turned out to be true:

1. **Phase 2 (login/brand)** — already materially done this session (redesign, build-verified). Remaining: none identified, pending the owner's visual sign-off.
2. **Phase 6a (quick wins first)** — replace `window.prompt()`/`alert()` in expense/reading-correction rejection flows with a real dialog; add frontend permission gating to purchases, attendance, station-settings, reading-corrections. Small, contained, immediately reduces client-confusion risk.
3. **Phase 7 (reading-correction request UI)** — build the missing "submit a correction request" form; without it, Phase 4/5 polish elsewhere doesn't matter if the core correction workflow has no front door.
4. **Phase 3 (onboarding)** — the brief's own highest priority; genuinely greenfield, size it as its own focused pass rather than folding it into Phase 6.
5. **Phase 6b (design-system adoption)** — roll `DataTable`/`Skeleton`/`ProgressSteps`/`EmptyState` across the 14 pages that don't use them yet. Do this *after* the quick wins above so it isn't redoing work.
6. **Phase 4 (contextual help elsewhere)** — extend the Daily Entry pattern (inline help text) to the other pages, once Phase 6b's layout pass stabilizes the pages it touches.
7. **Dependency/security pass** — resolve the starlette advisory set with a verified FastAPI bump and full re-test, timed independently of the UI phases since it touches the backend only.
8. **Direct verification of payroll** — a short, targeted check (not assumed, not deferred indefinitely) before any payroll-related client communication.
9. **Phases 11/12 (deployment/backup)** — only after 2–7 above, and only with explicit owner sign-off on provider/domain/budget, per the brief's own rule.

---

## 14. Verdict for this phase

**Phase 1 (audit) status: COMPLETE**, within the scope requested. The product is further along than the brief's framing assumed in several places (Daily Entry's guided flow, self-service registration, RBAC data model, a prior honest risk register) and has real, specific, named gaps in others (onboarding, UI permission-gating consistency, design-system adoption, one missing UI surface, one current CVE set). Nothing here says "ready" or "not ready" for production — that verdict belongs to Phase 14 of the original brief, after Phases 2–12 are actually done, not before.
