# Phase 8c Implementation Report — Consolidated Multi-Station Dashboard

Follows `docs/PHASE_8_MULTI_STATION_SAAS_AUDIT.md` and `docs/PHASE_8B_ORGANIZATION_AGGREGATION_REPORT.md`. Frontend-only — no backend file changed, no migration.

## Step 1 — what was inspected before writing anything

- The six Phase 8b org-wide endpoints (`sales`, `revenue`, `expenses`, `stock`, `attendance`, `station-performance`) and their exact response shapes.
- `components/AppShell.tsx` (nav/sidebar structure, how `usePermissions` already gates nav items), `lib/permissions.ts`, `components/ui/{StatCard,DataTable,Tabs,EmptyState,AccessDenied,PageHeader}.tsx`, `components/DateRangeFilter.tsx`, `components/charts/{RevenueDonut,SalesOverTimeChart}.tsx`, `lib/useChartColors.ts`, and the existing org/station dashboard pages, to reuse rather than re-invent every visual primitive.
- `lib/types.ts` (`Me`/`StationRoleSummary`) and `app/api/organizations.py::list_organizations` (no permission gate beyond being signed in) - the basis for deriving "which stations can I switch to" and "what's this organization called" without a new backend endpoint.

**Real, pre-existing issue found and fixed as part of this audit** (flagged in Phase 8's own audit, §4): `lib/permissions.ts`'s `can()` still treated every superuser as an unconditional bypass - correct before Phase 5b, stale since. Fixed (see below) before building anything that depends on it, since this phase's own new UI (`Company Overview`, the station switcher) would otherwise have shipped with the same stale assumption baked in on day one.

## Frontend authorization fix

`usePermissions` no longer treats `is_superuser` as an unconditional "can do anything." A superuser now `can()` do something only when:
1. They hold an active support session matching the organization (and station, if the session is station-scoped) - mirrors `app/core/support_sessions.py::support_session_grants` exactly (new `lib/support-session.ts::sessionCoversScope`).
2. The requested permission code ends in `:read` - a session never grants a write, so a write-gated control (e.g. "Add station") correctly stays hidden for a superuser regardless of session state.

This is a UI-visibility fix only - the backend was already, and remains, the real boundary; nothing here changes what Phase 5b enforces server-side.

## Company Overview dashboard (`/dashboard/org/{orgId}/overview`)

Four tabs, reusing `Tabs`/`Card`/`StatCard`/`DataTable` throughout, all data from the Phase 8b endpoints only:
- **Overview**: total fuel sold, total revenue, cash collected (shown separately from total tendered, per Phase 8b's own guarantee), approved expenses; a revenue-by-payment-method breakdown (cash/card/digital/credit); expense categories.
- **Stock**: book stock by fuel grade, and a tank-by-tank table with book stock and the most recent physical dip reading as two distinct columns - never summed, matching Phase 8b's own guarantee.
- **Attendance**: total employee headcount, and a per-station present/late/half-day/leave/absent table - the per-day dedup rule is entirely the backend's (Phase 8b); the frontend only sums the already-deduplicated daily counts for a range total.
- **Station Comparison**: two bar charts (litres sold, expected revenue, one new reusable `StationBarChart` component) plus a sortable side-by-side table (litres, revenue, tendered, approved expenses, current stock, employee count) - **no profit/margin column**, matching Phase 8b's own station-performance schema exactly.

A shared `DateRangeFilter` (already used elsewhere in the app) drives Overview/Attendance/Comparison; Stock is a live snapshot with no date range, matching its backend endpoint.

**Real bug found and fixed while building this** (not a pre-existing issue - introduced and caught within this phase): the three date-range-driven tabs fetched on every `dateFrom`/`dateTo` change with no stale-response guard. Two quick date-field edits (as happens naturally when a person edits "From" then "To") could fire two overlapping requests, and if the *first* one's response (possibly an error, from the briefly invalid intermediate range) resolved *after* the second, correct one, it would overwrite the correct result with a stale error. Fixed with a `cancelled` flag in each effect's cleanup, the same pattern `AppShell`/other pages don't need but any multi-field-driven fetch in this codebase should use. Caught by the new Playwright test for date filtering, not by code review.

## Persistent station switcher

`components/StationSwitcher.tsx`, rendered in `AppShell`'s sidebar for every page under `/dashboard/org/{orgId}/...`:
- "All Stations" (routes to Company Overview) is offered **only** when the signed-in user holds a genuine org-wide grant (`UserStationRole.station_id === null`) or, for a superuser, an org-wide support session - never just because every station happens to be listed.
- Individual stations are derived from the signed-in user's own server-issued `station_roles` (from `/auth/me`, already trusted everywhere else in this app) intersected with the organization's real station list (`GET /organizations/{id}/stations`, for display names) - a station-scoped viewer's dropdown never even lists a station they can't access, let alone its data.
- Switching is a full route navigation (`router.push`), never a client-side data swap - there is no shared state between stations that a switch could leave half-updated.
- Every page it navigates to still re-validates access itself (same `require_permission` dependency as before) - the switcher is a navigation convenience, not a new security boundary.

New `lib/station-scope.ts::useAccessibleStations` and `lib/organization-name.ts::useOrganizationName` support it; a new `nav.companyOverview` nav item (gated on `report:read`, same convention as every other nav item) links to the same page.

## Individual station dashboard

Unchanged - reused exactly as it was. The switcher's "individual station" options route to the station's existing `/today` page, same as every other internal link in this app already does.

## Security

- Every number on every tab comes from a `require_permission`-gated backend call; nothing is rendered from client-side-only state.
- A requested station outside the caller's authority still 403s/404s at the API layer exactly as Phase 8b built it - the frontend fix here is that the switcher no longer even *offers* such a station, not a new enforcement point.
- No frontend Super Admin bypass was introduced; the one that existed before this phase was removed (see "Frontend authorization fix" above).
- Phase 5b's read-only support-session restriction is unchanged and is now correctly mirrored, not ignored, by `usePermissions`.

## Tests (9 new, `e2e/company-overview.spec.ts`)

Company Overview shows real combined figures (station 1's known, fixed seeded shift verified exactly in the comparison table, not a hardcoded total that could be thrown off by other specs' concurrent activity on stations 2/3); "All Stations" offered to the real org-wide Owner; a station-scoped Station Manager's switcher lists only their two authorized stations, never the third; direct navigation to an unauthorized station shows `AccessDenied`, not that station's settings; switching stations navigates to the right URL; an empty/invalid-for-the-seed-data date range shows a real "0 L", not an error (the stale-response bug above was caught here); the Attendance tab shows a real positive headcount; the Stock tab shows real tank rows; a role with no `report:read` at all (Cashier/Operator) sees `AccessDenied` on Company Overview.

One existing test needed a one-line fix, not a weakening: `daily-entry.spec.ts`'s `page.locator("select").first()` started matching the new sidebar station-switcher `<select>` instead of the Sales & Collections tab's own payment-method dropdown. Scoped to `page.locator("main select").first()` (excludes the sidebar), with a comment explaining why - the test's actual assertion is unchanged.

## Results

- Full Playwright suite: **42 passed**, 0 failed (33 pre-existing + 9 new).
- Backend: unaffected - no backend file was changed in this phase (`git status` confirms); the full 351-test backend suite was already green at the end of Phase 8b and was not re-run here, since nothing it covers changed.
- Frontend build/typecheck: clean (`docker compose build frontend`).

## Known limitations

- The station switcher offers no search/filter for an organization with a very large number of stations - a plain `<select>` is used; a typeahead combobox would be a follow-up UI refinement, not a correctness gap.
- Station Comparison's bar charts show at most two metrics (litres, revenue) as separate charts rather than one combined view - deliberate, to stay readable at phone width with more than a handful of stations.
- No automated viewport/responsive assertions were added (Playwright ran at its default desktop viewport) - the Tailwind classes used throughout (`grid-cols-1 sm:grid-cols-2 lg:grid-cols-4`, etc.) follow the same responsive conventions as every other page in this app, but a dedicated mobile-viewport Playwright pass wasn't done as part of this phase's testing.

## Deployment

To be pushed and verified in production after this report. No migration. Production verification will be limited to confirming the frontend deploys and the new `/overview` route renders without a client error, for the same reason stated in Phase 8a/8b: exercising real multi-station business figures against live production data isn't something this session has credentials or authorization to do.
