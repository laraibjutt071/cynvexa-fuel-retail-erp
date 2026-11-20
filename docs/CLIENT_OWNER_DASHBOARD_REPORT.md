# Client Owner Dashboard — Enhancement Report

Status: implemented and tested locally. **NOT PUSHED. NOT DEPLOYED.**

## 1. Existing dashboard architecture (before this work)

The Client Owner Dashboard already existed from Phase 8c: `frontend/app/dashboard/org/[orgId]/overview/page.tsx`, titled "Company Overview." It was **enhanced, not duplicated** — every file below is a modification of this existing page and its existing supporting endpoints, with one new backend endpoint added alongside the existing ones.

Before this work, it had:
- Four tabs: Overview (sales/revenue/expenses KPIs, payment-method breakdown, expense categories), Stock (book stock by grade + tank table), Attendance (StatCards + by-station table), Station Comparison (two `StationBarChart`s + a side-by-side table).
- A single shared `DateRangeFilter` in the page header, feeding every tab.
- Gated on `can("report:read")`, with `AccessDenied` otherwise.
- A stale-response guard (`cancelled` flag) in each tab's own `useEffect`, added in Phase 8c after a real race condition was found.
- Reused the existing Phase 8b org-wide report endpoints (`/organizations/{org}/reports/sales|revenue|expenses|stock|attendance|station-performance`) — none of these were duplicated.
- No per-station in-page filter (narrowing happens only by navigating to a different station's own page via the sidebar `StationSwitcher`).
- No live/auto-refreshing element of any kind.
- No supplier balance, pending-approvals, or recent-activity data anywhere on this page.

## 2. What was enhanced

All changes are inside the existing **Overview tab** (`OverviewTab` function) of the same existing page — the Stock, Attendance, and Station Comparison tabs are untouched. Platform Super Admin functionality (`/dashboard/platform/*`) is a completely separate route tree and was not touched in any way.

1. **Live, auto-refreshing daily sales trend chart** — new `DailySalesTrendChart` component (recharts `AreaChart`, same `useChartColors`/`chartAxisTickStyle`/`chartTooltipStyle` conventions as the existing `StationBarChart`), fed by a new backend endpoint (Section 4).
2. **60-second auto-refresh + manual "Refresh now" button + "Last updated" timestamp** for the entire Overview tab's data (sales, revenue, expenses, daily-sales, supplier balances, pending approvals) — see Section 5 for the exact mechanics and the race condition found and fixed while building it.
3. **Supplier Outstanding Balance KPI** — a 5th stat card, summing the existing (Phase 10b) `GET /organizations/{org}/suppliers/balances` endpoint's response. No new backend code; shown only to users who hold `supplier_ledger:read`, omitted otherwise.
4. **Pending approvals & attention centre** — a new card using the existing `GET /organizations/{org}/reports/pending-approvals` endpoint (already org-wide, already used elsewhere in the app per the audit that preceded this work), with each category linking to its real existing workflow page (Expenses tab, Suppliers page, or the Stations list for anything that's inherently per-station).
5. **Recent activity feed** — a new card using the existing `GET /organizations/{org}/audit-log` endpoint, limited to 8 entries, with action names humanized for a non-technical reader (e.g. `shift.approve` → "Shift approved") and actor names resolved from the existing `GET /organizations/{org}/users` list. Shown only to users who hold `audit:read`.

## 3. A real pre-existing bug found and fixed during this work

While auditing `pending-approvals` (needed for item 4 above, since this dashboard was about to surface it prominently), a genuine cross-tenant data leak was found: the `unapproved_meter_events` count in `backend/app/api/reports.py::pending_approvals_report` had **no organization or station filter at all** — it counted unapproved meter events across every organization in the entire database, not just the caller's own. Every sibling field in the same function correctly filtered by org/station; this one field had simply been missed.

**Fixed**: the query now joins to `Shift` and filters by `Shift.organization_id == organization_id`, plus the same station-visibility filter every other field in this function already applies. **No business logic changed** — this only restores the isolation every other field already had. A new regression test (`test_pending_approvals_unapproved_meter_events_is_scoped_to_the_caller_organization`) directly constructs a flagged, unapproved meter event in a separate organization via the ORM and asserts the caller's own org still sees `0` — it passes against the fix and would fail against the old code.

This was not count-of-sensitive-data exposure (no row-level detail leaked, only an integer), but it is a real tenant-isolation defect, and shipping this dashboard without fixing it would have made the leak more visible, not less — so it was fixed as part of this phase rather than deferred.

## 4. New backend endpoint

`GET /organizations/{organization_id}/reports/daily-sales` — `backend/app/api/org_reports.py`. **Read-only. No model or migration change.**

- Params: `date_from`, `date_to` (required), `station_id` (repeatable, optional) — identical signature to every sibling org-report endpoint.
- Permission: `report:read`, resolved via the exact same `resolve_authorized_station_ids` helper every sibling endpoint uses — a `station_id` filter only ever narrows an already-authorized set, never widens it.
- Calculation: reuses `approved_shifts_in_range` (existing) and a new `sales_by_day` function in `backend/app/core/org_aggregation.py`, which buckets by each shift's own `opened_at` date using the **identical two sources** `sales_by_grade_and_station` already uses (`compute_expected_fuel_revenue_by_grade` for revenue, the stock ledger's own `SALE` postings for litres) — just grouped by day instead of by grade/station. No parallel calculation of litres or revenue exists anywhere.
- Response: one row per calendar day in `[date_from, date_to]`, **zero-filled, never omitted**, so a flat stretch on the chart is a real "no sales" signal, not a silently-skipped gap.
- Schema: `OrgDailySalesDay { sales_date, litres_sold, expected_revenue }`, `OrgDailySalesReport { date_from, date_to, days[] }` — `backend/app/schemas/org_reports.py`.

## 5. Live graph and auto-refresh behavior — exact mechanics

- **Interval**: 60 seconds (`AUTO_REFRESH_INTERVAL_MS`), via `window.setInterval`, cleared in the effect's cleanup.
- **Manual refresh**: a visible "Refresh now" button, calling the same `load(false)` function the interval calls.
- **Overlap prevention**: a single `inFlightRef` boolean blocks a second fetch cycle from starting while one is already running (covers a manual click landing mid-interval).
- **Stale-response/stale-generation handling — the one real bug found and fixed while building this**: an initial implementation used one shared `cancelled`/`inFlightRef` pair across the whole tab's lifetime. This raced: if a background auto-refresh was in flight at the exact moment the date range changed, the new load could see the stale `inFlightRef` still `true` and silently no-op, leaving the OLD date range's data on screen indefinitely. Caught by the existing Playwright test `An empty date range shows a real empty/zero state, not an error`, which failed with the previous range's non-zero figure still showing. **Fixed** with a generation-token pattern: every date-range change increments a `generationRef` counter; every in-flight request captures its own generation number at start and discards its result if the counter no longer matches by the time it resolves. This is the same stale-response principle Phase 8c's own `cancelled` flag already used elsewhere on this page, extended to survive repeated background refreshes, not just a single request per effect run.
- **Last successful data preserved on a failed refresh**: a failed background refresh sets a dismissible `refreshError` state and leaves the previously-loaded `data` untouched — the dashboard never blanks itself or shows stale data mislabeled as fresh; it shows the old data plus an explicit warning that the last refresh attempt failed.
- **Cleanup on unmount**: the effect's cleanup clears the interval and bumps the generation counter, so any request still resolving after the component unmounts (or the date range changes again) cannot write to state.
- **"Live" claim, verified not just asserted**: the chart's data, the "Last updated" timestamp, and the refresh button's effect were all verified end-to-end against the real backend in a new Playwright test (Section 7) — a real expense was recorded via the API, "Refresh now" was clicked, and the Expense categories card's total was asserted to reflect the new figure. This is not a cosmetic refresh indicator; it re-fetches and re-renders real data.

## 6. Security and authorization

- The Overview tab's top-level gate is unchanged: `can("report:read")`, backend-enforced on every endpoint it calls (`require_permission(REPORT_READ)` on sales/revenue/expenses/daily-sales/station-performance; `require_permission(REPORT_READ)` on pending-approvals too).
- Supplier balances and the activity feed are each independently gated on their own real permission (`supplier_ledger:read`, `audit:read`) and simply omitted — not shown empty, not erroring — when the signed-in role doesn't hold it.
- Station authorization is unchanged and still fully backend-enforced: a station-scoped role's `station_id` query filter attempt outside their authorized set is rejected with `403` by the existing `resolve_authorized_station_ids`/`_authorized_stations` helper, exercised by the new endpoint exactly like every sibling one — verified by a new test (`test_daily_sales_rejects_an_unauthorized_station_filter`).
- Platform Super Admin is architecturally separate (`/dashboard/platform/*`, its own routes/permissions) and was not touched.
- No superuser bypass was introduced anywhere in this work — every new or modified query still goes through the same `require_permission`/support-session machinery every existing endpoint already uses.

## 7. Tests executed and exact results

**Backend** (`backend/tests/test_org_reports.py`, `backend/tests/test_reports.py`), run against the dedicated, guarded `cynvexa_test` database (per `docs/TEST_DATABASE_ISOLATION_REPORT.md` — never the development database):
- 3 new daily-sales tests: a shift attributed to its own day with every other day zero-filled; same-day shifts across two stations correctly combined; an unauthorized station filter rejected with `403`.
- 1 new regression test for the cross-tenant meter-event-count leak fix (Section 3).
- Full suite result recorded once the background run (started before this report was written) completes — see the companion commit message / final response for the exact passed/failed count, since this report was drafted while that run was still in progress to avoid blocking documentation on it.

**Playwright** (`frontend/e2e/company-overview.spec.ts`, `frontend/e2e/meter-events.spec.ts`), run against the real, already-running dev stack (the documented Playwright boundary — never claimed to use the dedicated test database):
- 1 new test proving a real race-condition bug (Section 5) that the *first* implementation attempt actually had — caught by this exact pre-existing test before any report was written claiming success.
- 3 new tests: the live chart + last-updated + manual refresh reflecting a real new expense; the Supplier Outstanding Balance KPI and Pending Approvals card both rendering for an authorized Owner; the Recent Activity feed showing real, humanized actions.
- 2 new Meter Events navigation tests (Part B of this phase): the sidebar link visible and navigable for an authorized Owner; the same link absent at a station the signed-in role isn't granted at.
- Full suite (56 tests across all spec files) run **concurrently** with the backend suite above — made possible for the first time by the test-database isolation fix from the prior phase — all 56 passed, and the development database's `alembic_version` was confirmed unchanged immediately afterward, proving the isolation holds under real concurrent use, not just in isolation.

**Typecheck/build**: `docker compose build frontend` → `next build` — compiled successfully, zero TypeScript errors, both times (once initially, once after the race-condition fix).

## 8. Missing metrics / backend gaps (honestly reported, not fabricated)

- **Physical Dip and Pending Stock Reconciliation** as distinct dashboard KPIs: the existing Stock tab already shows book stock vs. last physical dip side by side (never merged, per the existing, preserved rule) — not duplicated into the Overview tab's stat cards to avoid two places claiming the same figure differently. A dedicated "pending stock reconciliation" count was not added — no existing endpoint returns one as a standalone figure (the closest is `low_stock_inventory_items` in pending-approvals, a different concept, already surfaced in the new attention centre).
- **Profit/margin**: not shown anywhere, consistent with every prior phase's own documented reasoning (`StationPerformanceRow`'s existing docstring) — this system has no cost-of-goods-sold data to support one. Not invented here either.
- **Present/Absent/Late Employees as Overview-tab stat cards**: the existing Attendance tab already shows this in full detail (by day and by station); not duplicated as a 6th/7th/8th stat card on the Overview tab to avoid crowding the header KPIs with a redundant summary of a tab one click away.
- **Supplier outstanding balance, broken down by supplier** on the Overview tab: only the organization-wide total is shown here (the existing Suppliers page already has the full per-supplier breakdown, statement, and history — linked from the Pending Approvals card).

## 9. Performance considerations

- The new `daily-sales` endpoint reuses the same O(shifts-in-range) revenue calculation every sibling report already accepts as its performance profile (documented in `docs/PHASE_8B_ORGANIZATION_AGGREGATION_REPORT.md`) — not a new or worse cost, and the litres query remains a single batched query regardless of the number of days or stations, same as `sales_by_grade_and_station`.
- The Overview tab's auto-refresh fetches 4 required reports in one `Promise.all`, then 2 optional ones in a second `Promise.all` — at most 6 requests every 60 seconds per open dashboard tab, not 6 separate sequential round trips.
- No N+1 query pattern was introduced; the station comparison table (untouched by this phase) already avoided this per its own existing test (`test_org_sales_litres_query_runs_once_regardless_of_station_count`).

## 10. Files changed

**Backend**: `app/schemas/org_reports.py`, `app/core/org_aggregation.py`, `app/api/org_reports.py` (new endpoint + schema + aggregation function), `app/api/reports.py` (the leak fix), `tests/test_org_reports.py`, `tests/test_reports.py` (new tests).
**Frontend**: `app/dashboard/org/[orgId]/overview/page.tsx` (enhanced `OverviewTab`), `components/charts/DailySalesTrendChart.tsx` (new), `components/AppShell.tsx` + `lib/i18n/translations.ts` (Meter Events nav entry, Part B of this phase, documented separately), `e2e/company-overview.spec.ts`, `e2e/meter-events.spec.ts` (new tests).
**No migration.** No login page change. No change to Stock/Attendance/Comparison tabs, payroll, attendance deduction rules, or the 24-hour meter correction policy.
