# Phase 10A — Meter Event Management UI

Status: **complete**, locally verified, deployed and health/route-verified in production (within the same limitation stated in every prior phase report: no real production business data was exercised, only health/readiness and route-availability).

## Why this phase existed

Phase 9's complete ERP gap audit (`docs/PHASE_9_COMPLETE_ERP_GAP_AUDIT.md`) found that meter events (replacement/reset/rollover) had full backend support — fields on `ShiftNozzleReading`, a close-time write path, and an approve endpoint — but **no usable frontend at all**: `ReadingsSection.tsx` only showed a passive warning paragraph with no form or button, and the Review tab provided no approve action either. A manager had to call the backend API directly to use the feature. This phase builds that missing UI, reusing every existing backend capability rather than inventing new write paths.

## Step 1 — Backend audit (read-only, confirmed before building anything)

- `ShiftNozzleReading` (`backend/app/models/shift_nozzle_reading.py`): a meter event is **not** a separate entity. It's optional fields on the same reading row — `meter_event_type` (`MeterEventType`: `replacement`/`reset`/`rollover`), `meter_event_pre_reading`, `meter_event_post_reading`, `meter_event_notes`, `meter_event_approved_by_user_id`, `meter_event_approved_at` — set atomically at the moment a nozzle reading is **closed**, never afterward.
- `backend/app/api/shifts.py`: `close_nozzle_reading` (validates both dispensed-litres segments are non-negative, sets the `meter_event_*` fields) and `approve_meter_event` (requires `SHIFT_APPROVE`, requires an existing flagged event, rejects a second approval) are the only write paths. Both already existed and needed no changes.
- `backend/app/schemas/reading_correction.py` / `backend/app/api/reading_corrections.py`: confirmed the **existing** Reading Corrections system already explicitly supports correcting `METER_EVENT_PRE`/`METER_EVENT_POST` values within the 24-hour window (or via amendment afterward) — but only for a value that's already non-null. This resolved the phase's key scoping question: a new meter event can only be *recorded* at close time (no new write path needed), and any **post-close correction** of an existing flagged event's values must go through the existing Reading Corrections workflow, not a new mechanism.
- **Missing backend capability confirmed**: there was no way to list meter events across shifts for a station — only per-shift nozzle-reading lists existed. This is the one real gap, built below.

### New backend capability

- `backend/app/schemas/meter_event.py` — `MeterEventRow`, a read-only Pydantic projection joining the reading with its shift, nozzle, dispenser, tank and fuel grade context.
- `backend/app/api/meter_events.py` — `GET /organizations/{org_id}/stations/{station_id}/meter-events`, gated on `SHIFT_READ`, filterable by `date_from`/`date_to` (max 366-day range), `event_type`, and `approved` (tri-state). Pure read, no new business logic, no model/migration change.
- Registered in `backend/app/main.py` (router import + include, alongside the existing `reading_corrections` router).

## Step 2 — Frontend implementation

All of this reuses the existing `close_nozzle_reading` and `approve_meter_event` endpoints, plus the new history endpoint above. No frontend code bypasses backend validation — every field still goes through the same Pydantic/business-rule checks the backend already enforced.

1. **Meter event history page** — `frontend/app/dashboard/org/[orgId]/station/[stationId]/meter-events/page.tsx` (new). Filterable table (date range, event type, approved/pending, text search), event-type badges, a details dialog (full reading/shift/approval context, notes, and an explicit link to the Reading Corrections page for any post-close value correction), and an inline approve action gated on `shift:approve`. Gated on `shift:read` with the standard `AccessDenied` fallback.
2. **Record a new meter event** — `ReadingsSection.tsx` (modified). The nozzle closing-reading block already warned ("if the meter was reset...") with no actual control. Now: if the typed closing value is lower than the opening reading, a caution banner appears; a checkbox ("This meter was reset, replaced, or rolled over mid-shift") reveals an inline form (event type, pre-event reading, post-event reading, notes) right where the closing reading is entered. Saving opens a confirmation dialog explaining the values become permanent (correctable only via Reading Corrections) and that approval is still required, then submits the existing `close` endpoint's payload with the `meter_event_*` fields included.
3. **Approval in the Daily Entry Review flow** — `ReviewSection.tsx` (modified). The Review tab's existing checklist already had a "No flagged meter events awaiting approval" item, but — exactly as Phase 9 found — no way to act on it. Added a conditional "Meter events awaiting approval" card listing each unapproved event (type, pre→post, notes) with its own "Approve event" button, gated on `shift:approve`; a user without that permission sees an explanatory note instead of the button. This card disappears as soon as every flagged event on the shift is approved, and the pre-existing checklist item (which already blocked final shift approval) now has a real action to clear it from the same screen, instead of requiring a trip to a separate page or a direct API call.
4. **Rollover / reset / replacement workflows**: all three share one recording form (event-type selector) and one approval action — there's no behavioral difference between them beyond the label and the dispensed-litres formula already used by the backend (`(pre − opening) + (closing − post)`), which the inline form's helper text explains.
5. **Station/tank/nozzle context**: every row (both in the inline form and the history table) shows dispenser/nozzle/tank/fuel-grade context, never a bare reading ID.
6. **Validation and error messages**: pre/post readings are required, non-negative numeric inputs; a rejected `close` call (e.g. a negative segment) surfaces the backend's own detail message in a toast, not a generic failure.

## Step 3 — Business and security rules (verified, not just assumed)

- **Org/station isolation**: the new history endpoint goes through the same `require_permission` dependency as every other endpoint, resolving `organization_id`/`station_id` from the URL path only — confirmed by a cross-org test (403) and a cross-station test for a station-scoped user (403).
- **RBAC respected**: history requires `shift:read`; approval requires `shift:approve`; both enforced backend-side (frontend gating is UX only, never the actual boundary) — confirmed by a Playwright test using a role granted only at a different station.
- **Historical readings never silently overwritten**: the close endpoint's existing behavior is unchanged; the new UI only ever calls it once, at the moment of closing, exactly as before.
- **24-hour correction policy preserved, no new deadline introduced**: a dedicated backend test (`test_a_meter_event_remains_visible_beyond_the_24_hour_correction_window`) sets a flagged event's shift/reading timestamps to 30 days in the past and confirms it still appears in history, unapproved-or-approved, exactly like a recent one. Correcting an already-recorded value still goes exclusively through the existing Reading Corrections / amendment mechanism — this phase added no competing correction path.
- **Frontend cannot bypass backend validation**: every field submitted by the new inline form goes through the same `close_nozzle_reading` Pydantic schema and business-rule checks (segment math, non-negative values) as before; the frontend's own pre-submit warning is advisory, not a substitute for the backend check.
- **Audit trails preserved**: `close_nozzle_reading` and `approve_meter_event` already write audit log entries; nothing in this phase changed that.

## Step 5 — Testing

### Backend — `backend/tests/test_meter_events.py` (11 new tests, all passing)

Covers: event appears in station history; approver recorded on approval; filter by event type; filter by approved status; date-range inclusion/exclusion; the 24-hour-window non-expiry test described above; invalid date range rejected (422); cross-organization access denied (403); station-scoped user cannot see another station's history (403); superuser needs an active support session (403 without one, 200 with one, read-only).

**Full backend regression**: `python -m pytest tests/ -q` → **362 passed**, 0 failed (ran inside the backend container against the real test database, not a subset). The only warnings are pre-existing Pydantic decimal-serialization warnings in `test_attendance.py`, unrelated to this phase.

### Frontend — Playwright

- **New**: `frontend/e2e/meter-events.spec.ts` (2 new tests):
  1. End-to-end: open a shift, flag a rollover at close time (closing value intentionally lower than opening, triggering the UI's own warning first), confirm the event blocks `Approve today's entry`, confirm the Review tab's new inline approve action clears it, then confirm the same event shows up approved on the dedicated Meter Events history page.
  2. A user with a role granted only at a different station gets `Access restricted` navigating directly to this station's Meter Events page (station-scoping on the frontend's own gate, independent of the backend 403 already covered on the backend side).
- **Full Playwright suite** (all 7 existing spec files + the new one): **44 passed, 0 failed**, including the pre-existing full day-in-the-life workflow (`daily-entry.spec.ts`) and every role-based/permission-isolation test — confirming no regression to existing meter/shift/daily-entry workflows.
- One real, caught-and-fixed issue during this phase: the new spec's first draft used `page.getByText("Meter events awaiting approval")` without `{ exact: true }`, which also substring-matched the pre-existing, unrelated checklist label "No flagged meter events awaiting approval" (Playwright's default text match is case-insensitive substring). This was a test-locator bug, not a product bug — confirmed by manually inspecting the live network responses, which showed the approval persisting correctly server-side throughout. Fixed by exact-matching the new card's title.
- One pre-existing flake unrelated to this phase: running the full suite at 7 parallel workers intermittently fails 1–2 login-dependent tests (`daily-entry.spec.ts`, `company-overview.spec.ts`) with a login timeout under concurrent-login load; both pass cleanly in isolation or with fewer workers. Not a Phase 10a regression — these tests don't touch any file this phase changed, and the second full run (same command, same 7 workers) completed 44/44 with no failures at all.

### Frontend build

`docker compose build frontend` → `next build` compiles and type-checks successfully (Next.js 16.4.3, Turbopack). One pre-existing type error was found and fixed during this phase in `meter-events/page.tsx` (a `ConfirmDialog`'s `description` prop could be `undefined`, which its type doesn't allow — defaulted to `""`).

## Deliverables / files touched

**Backend (new)**: `app/schemas/meter_event.py`, `app/api/meter_events.py`, `tests/test_meter_events.py`.
**Backend (modified)**: `app/main.py` (router registration only).
**Frontend (new)**: `app/dashboard/org/[orgId]/station/[stationId]/meter-events/page.tsx`, `e2e/meter-events.spec.ts`.
**Frontend (modified)**: `lib/types.ts` (`MeterEventType`, `MeterEventRow`), `app/.../daily-entry/ReadingsSection.tsx` (inline record-event workflow), `app/.../daily-entry/ReviewSection.tsx` (inline approve action).
**No migration required** — no model or column changed, only a new read-only endpoint over existing columns.

## Remaining limitations (honest, not claimed as done)

- No i18n/Roman Urdu translation was added for the new Meter Events page or the new Readings/Review strings, consistent with this project's existing precedent of not yet translating every operational page (`docs/REMAINING_RISKS.md`'s Phase 7 UX-upgrade section already documents this same gap for other pages).
- The Meter Events history page's own filters are client-triggered re-fetches, not debounced — fine at the data volumes this app is built and tested against, not evaluated at a much larger per-station event volume.
- As with every prior phase, production verification was limited to route/health availability after deploy — no real tenant business data was exercised against the live production database.
