# Phase 8b Implementation Report — Organization-Wide Aggregation

Follows `docs/PHASE_8_MULTI_STATION_SAAS_AUDIT.md` (§6, Phase 8b) and `docs/PHASE_8A_PLAN_LIMITS_REPORT.md`. No database migration — every new endpoint reads existing tables through existing calculation functions.

## Step 1 — what was inspected before writing anything

- `app/api/reports.py` in full: every single-station report (`daily-fuel-sales`, `tank-variance`, `shift-reconciliation`, `pending-approvals`, `expense-summary`, `inventory-stock`, `price-change-history`), their exact filters, and the one existing org-wide endpoint (`pending-approvals`) and how it resolves station visibility.
- `app/core/revenue.py` — `compute_expected_fuel_revenue`/`compute_expected_fuel_revenue_by_grade`: the only functions allowed to compute expected fuel revenue (litres × price, segmented across mid-shift price changes). Confirmed it never reads `ShiftTender`/`ShiftCashMovement`.
- `app/core/reconciliation.py` — confirmed `get_total_tender_amount`/`get_cash_tender_amount` are a *different* number from expected revenue by construction, and that `PaymentMethodCategory` is exactly `cash`/`card`/`digital`/`credit`.
- `app/core/stock.py::get_book_stock` — the only function allowed to compute book stock (ledger projection), and `app/core/variance.py` — confirmed physical dip readings (`ShiftTankReading`) are always a separate fact, never substituted for book stock.
- `app/models/expense.py`, and the existing `expense_summary_report`'s categorization logic — found that a *reversed* expense still counts toward `total_amount` but not any status bucket; this is existing, established behavior, not something to "fix" while reusing it.
- `app/models/attendance.py` — found the unique constraint is `(station_id, user_id, attendance_date)`, **not** `(user_id, attendance_date)` — meaning a multi-station employee can genuinely have two different statuses recorded on the same day at two different authorized stations. This directly drove the dedup rule below; I did not assume the two reports' "status" meant the same thing in both contexts.
- `app/core/report_scope.py` (pre-existing `get_station_visibility_scope`/`superuser_visible_station_ids`) and `app/api/deps.py::require_permission` — confirmed how station-scoped vs. org-wide role grants are already resolved, and that Phase 5b's support-session gate applies here unchanged.

## Step 2 — what was reused vs. newly written

Nothing recalculates a number a single-station report already produces:
- Sales/revenue litres and expected-revenue figures come from the exact same two sources `_build_daily_fuel_sales` already uses: `compute_expected_fuel_revenue_by_grade` per approved shift, and the stock ledger's own `SALE` postings for litres — summed across shifts from every authorized station instead of one.
- Payment-method breakdown reuses `ShiftTender`/`PaymentMethod.category`, the same tables `get_cash_tender_amount` already reads.
- Expense categorization reuses `app/api/reports.py`'s own bucketing logic, **extracted into `categorize_expenses()`** (a pure refactor — same inputs, same outputs, now called from both the single-station and the new org-wide endpoint, so the two can never define "approved expenses" differently).
- Stock reuses `get_book_stock` per tank, plus the most recent `ShiftTankReading` per tank as a separate, clearly-labeled field.
- The one genuinely shared piece of new logic, `app/core/report_scope.py::resolve_authorized_station_ids`, was also back-ported into the pre-existing `pending_approvals_report` (replacing its own copy of the same scope-resolution branch) so both paths are provably the same rule, not two copies that could drift.

## New endpoints

All under `/organizations/{organization_id}/reports/`, all `require_permission(REPORT_READ)` except attendance (`ATTENDANCE_READ`), all accept `date_from`/`date_to` (except `/stock`, which is a live snapshot) and an optional repeated `station_id` query filter:

| Endpoint | Response | Key fields |
|---|---|---|
| `GET /sales` | `OrgSalesReport` | `total_litres_sold`, `total_expected_revenue`, `by_fuel_grade`, `by_station` |
| `GET /revenue` | `OrgRevenueReport` | `total_recognized_revenue` (fuel litres × price) **and separately** `total_tender_amount`, `cash_amount`, `card_amount`, `digital_amount`, `credit_amount`, `by_station` |
| `GET /expenses` | `OrgExpenseReport` | `by_category` (reuses `ExpenseSummaryRow`), `by_station`, `grand_total`, `grand_approved` |
| `GET /stock` | `OrgStockReport` | `by_fuel_grade`, `tanks` (`book_stock` and `last_physical_dip_reading`/`_at` as two distinct fields, never summed) |
| `GET /attendance` | `OrgAttendanceReport` | `total_employees` (headcount, not a row count), `days` (per-day present/absent/late/half-day/leave), `by_station` |
| `GET /station-performance` | `OrgStationPerformanceReport` | one `StationPerformanceRow` per station: litres, expected revenue, tender, approved expenses, book stock, employee count — **no profit/margin field**, since this system has no COGS data to support one (`docs/ASSUMPTIONS.md` #28) |

## Revenue vs. cash collected — the specific guarantee

`OrgRevenueReport.total_recognized_revenue` is computed purely from `compute_expected_fuel_revenue_by_grade` and never touches `ShiftTender`. `total_tender_amount` and the four category amounts come from a separate query over `ShiftTender`/`PaymentMethod`. These are two independent numbers in the response; a credit-heavy shift makes them visibly different (verified: `test_revenue_is_never_conflated_with_cash_collected`, where half the recognized revenue was tendered on credit, not cash).

## Book stock vs. physical dip — the specific guarantee

`OrgStockTankRow` has `book_stock` (a live `get_book_stock` projection) and `last_physical_dip_reading`/`last_physical_dip_at` (the most recent `ShiftTankReading`, from any shift) as two separate fields. Nothing in this phase ever adds them together or substitutes one for the other.

## Attendance double-counting rule (documented, deliberate)

Because `AttendanceRecord`'s uniqueness is per-station, an employee covering two authorized stations on the same day can have two different statuses recorded that day. For the organization-wide **daily** present/absent/late/half-day/leave counts, each employee is counted **once per day**, resolved by priority: `present > late > half_day > leave > absent` (did they show up anywhere, outranking everything else). The **per-station breakdown** (`by_station`) is intentionally *not* deduplicated — it reflects each station's own attendance record as-is, matching what that station's own attendance page would show. `total_employees` is a headcount (distinct active staff with a role covering an authorized station), not derived from attendance rows at all.

## Security

- Every endpoint resolves `station_id` authorization via `resolve_authorized_station_ids`: the final set is always the intersection of "stations in this organization" and "stations this caller's role (or active, read-only Phase 5b support session) can see" — a requested `station_id` can only narrow that set, never widen it.
- A requested station id belonging to a **different organization** → 404 (the same generic message `get_station_or_404` already gives everywhere else — no new leak).
- A requested station id belonging to **this** organization but outside the caller's own visible scope → 403, naming no station (a station-scoped viewer learns nothing about what exists outside their scope).
- A superuser with **no active support session** gets 403 from every one of these endpoints, same as any other tenant business-data read since Phase 5b — verified explicitly (`test_superuser_needs_an_active_support_session_to_read_org_wide_reports`). With an active, read-only session, the same endpoints work exactly like a real org-wide role would (`test_support_session_grants_read_only_access_to_org_wide_reports`) — nothing here reintroduces an unconditional Super Admin bypass.

## Performance

- Litres-sold and payment-category totals are each a single `GROUP BY`-capable aggregate query across every authorized station's shifts, not one query per station (verified: `test_org_sales_litres_query_runs_once_regardless_of_station_count`).
- Expected-revenue computation (`compute_expected_fuel_revenue_by_grade`) and current book stock (`get_book_stock`) are each called once per shift / once per tank — this is the existing, established shape of these functions (the single-station reports already do this), reused rather than redesigned into a different, riskier calculation. For an organization with a very large number of shifts or tanks in range, this scales linearly with that count, same as it already does today per-station; a materialized/cached revenue figure is a larger, separate change this phase deliberately did not make.

## Tests (20 new, `tests/test_org_reports.py`)

Covers all 16 requested categories: single- and multi-station totals with combined-equals-sum verification against the real single-station endpoint; station-wise breakdown accuracy; cross-organization denial; unauthorized station-filter denial (using a station-scoped role that genuinely holds `report:read`, not one with no permission at all, so the test proves the scoping logic specifically); a cross-org station id giving 404; owner vs. station-scoped user visibility; revenue-vs-cash separation; book-stock-vs-dip separation; only-approved-shifts counted; reversed tenders and reversed expenses excluded correctly; Decimal precision on an odd litre amount; inclusive date boundaries and rejection of an invalid range; attendance dedup across two stations same day; empty-organization and empty-station zero responses; Super Admin supportsession read-only gating (both directions); and a query-count regression guard for the one part of this phase that is meant to be a single aggregate.

One test fixture choice was corrected during implementation, not weakened: two tests initially used `cashier_user` to prove station-scoping, but that role holds no `report:read` at all, so they passed for the wrong reason (denied by the outer permission check, not the scoping logic under test). Switched to `station_manager_user`, which holds `report:read` scoped to one station — the tests now actually exercise `resolve_authorized_station_ids`.

## Results

- `tests/test_org_reports.py`: **20/20 passed**.
- Full backend regression suite: **351 passed**, 0 failed (331 pre-existing + 20 new).
- No migration — `git status` confirms only new/modified Python files, no `alembic/versions/` entry.

## Known limitations

- `/stock` has no date-range filter — it is always a live snapshot (book stock and the latest physical dip are both "as of now" concepts; a historical stock-as-of-date view wasn't requested and isn't built).
- The per-shift revenue loop is O(shifts in range), not a single SQL aggregate — an intentional reuse-over-redesign tradeoff, not an oversight (see Performance above).
- Station-performance deliberately omits a profit/margin column; if cost-of-goods-sold data is ever added, that would be a new, separate decision, not an extension of this report.

## Deployment

- Local backend regression suite and new tests: passed (above).
- No migration required for Neon.
- To be pushed and verified in production after this report; production verification will be limited to endpoint availability/health, same stated limitation as Phase 8a, since exercising the actual business-data behavior would require either real platform-admin credentials not held in this session or creating test records against production data, neither of which this phase does.
