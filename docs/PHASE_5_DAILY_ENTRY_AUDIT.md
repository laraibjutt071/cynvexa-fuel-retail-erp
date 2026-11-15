# CYNVEXA — Phase 5 Daily Entry Audit (Step 1)

**Date:** 2026-11-15
**Method:** Direct code read of all 5 section components (`ReadingsSection.tsx`, `SalesSection.tsx`, `ExpensesSection.tsx`, `CashSection.tsx`, `ReviewSection.tsx`) and the orchestrator (`page.tsx`), cross-checked against the real backend permission catalog (`app/core/permission_codes.py`) and the actual endpoints each one calls. Nothing below is inferred from the UI alone.

---

## 1. Readings

| | |
|---|---|
| **Fields** | Tank opening/closing dip (per tank); nozzle opening/closing totalizer (per nozzle) |
| **Required** | Implicitly (empty string blocks the save call client-side: `if (!value) return;`), but **no visual required-indicator or inline validation message** — a user who clicks Save with nothing typed just sees nothing happen, no error |
| **Validation** | One real check: closing totalizer lower than opening shows a caution message suggesting a meter-event correction. No minimum (`min="0"`) on any numeric input. No check that a value actually changed. |
| **Permissions** | **None at the frontend.** No `usePermissions` call anywhere in this file — every signed-in user who can reach the page sees every save button, regardless of role. Backend enforces `shift:open`/`shift:close` separately (safe), but the UI doesn't reflect it. |
| **API requests** | `GET tanks`, `GET nozzles` (overview), `GET tank-readings`, `GET nozzle-readings` on load; `POST tank-readings/{opening\|closing}`, `POST nozzle-readings`, `PATCH nozzle-readings/{id}/close`, `PATCH shifts/{id}/close` |
| **Error states** | Shows the backend's real `detail` message via toast; a close-reading-specific fallback message mentions meter-event correction. No inline field-level error — all errors are toast-only. |
| **Draft/submission** | Each reading is its own immediate `POST`/`PATCH` on its own Save click — not a batched draft. A typed-but-unsaved value in a text box is held only in local React state and is **lost if the user switches to another Daily Entry tab**, because the parent (`page.tsx`) conditionally renders only the active section, unmounting the others. This is real and was not previously documented. |
| **Calculations** | None performed client-side; `dispensed_litres` is server-computed and only displayed. |
| **Usability gaps found** | No required-field marker; no units shown next to the input itself (only in the column header); switching tabs silently drops an unsaved reading; close-shift action has no confirmation step despite ending the station's ability to edit further readings. |

## 2. Sales (Collections)

| | |
|---|---|
| **Fields** | Payment method (select), amount, credit customer (conditional on a credit-category method), reference (optional) |
| **Required** | Payment method and amount are `required` on the `<input>`/`<select>` (real HTML5 validation, not fake); credit customer required only when the method's category is `credit`. |
| **Validation** | Browser-native (`required`, `type="number"`) only; no explicit min, no duplicate-amount warning. |
| **Permissions** | **None at the frontend.** Recording (`shift_reconcile:record`) and reversal (no separate check — see below) both render unconditionally. |
| **API requests** | `GET payment-methods`, `GET credit-customers`, `GET tenders` on load; `POST tenders`; `PATCH tenders/{id}/reverse` |
| **Error states** | Toast with real backend `detail`. |
| **Draft/submission** | Real double-submit guard (`if (submitting) return`, button `busy`-disabled). Form clears only after a confirmed `resp.ok`. Reversal already uses the Phase 3 `ReasonDialog` (not a native prompt) — correctly gated behind an explicit reason, correctly shows a non-reversible warning. |
| **Calculations** | `total` is summed client-side from the already-loaded tenders (excluding reversed ones) purely for display — not sent anywhere, not a source of truth. **Found this phase:** displayed via `total.toFixed(2)`, not `formatMoney()` — inconsistent with the rest of the app's Phase 4 formatting pass. |
| **Usability gaps found** | No frontend permission check on recording or reversal; running total not formatted consistently; no indicator of which payment categories (cash/card/digital/credit) sum to how much — only a single combined total. |

## 3. Expenses

| | |
|---|---|
| **Fields** | Category (free text), description, amount |
| **Required** | All three marked `required` via the `Field` component (visible, labeled, consistent with the rest of the app — this section already does it correctly). |
| **Validation** | Browser-native only. |
| **Permissions** | **None at the frontend** (`expense:record` backend-only). |
| **API requests** | `GET expenses?station_id=...` (client-side filtered to the business date — a real, if slightly wasteful, pattern: it fetches up to 100 org-wide expenses and filters in the browser rather than filtering server-side by date); `POST expenses` |
| **Error states** | Toast with real backend `detail`. |
| **Draft/submission** | Real double-submit guard, same pattern as Sales. |
| **Calculations** | `total` excludes rejected/reversed expenses, client-side sum for display only. Same `total.toFixed(2)` formatting inconsistency as Sales. |
| **Usability gaps found** | No frontend permission check; the client-side date-filter means a station with many expenses does more work than necessary (not a correctness bug, a minor inefficiency, not fixed this phase — out of scope, not a usability issue a cashier would notice). |

## 4. Cash

| | |
|---|---|
| **Fields** | Cash movement: type (select), amount, reason (required). Closing: actual physical cash (required, with an existing hint), explanation (optional). |
| **Required** | Movement amount/reason are `required`; closing's actual-cash field is `required` with a hint already present (`cash.actualCashHint`) — among the better-explained fields in the whole workflow already. |
| **Validation** | Browser-native only. |
| **Permissions** | **None at the frontend for two real actions**: approving a decreasing cash movement (backend: `shift_reconcile:approve` — Accountant/Owner only) and authorizing a tolerance-exceeding discrepancy (same permission) both render unconditionally for every role, including Cashier. |
| **API requests** | `GET cash-movements`, `GET reconciliation` on load; `POST cash-movements`; `PATCH cash-movements/{id}/approve`; `POST reconciliation`; `PATCH reconciliation/authorize` |
| **Error states** | Toast with real backend `detail`, including a dedicated message for the authorize failure path. |
| **Draft/submission** | Real double-submit guard on both forms. |
| **Calculations** | **All real, backend-computed, already correctly separated** — this is the one section that already does Step 5's "financial clarity" correctly in substance: `expected_fuel_revenue` (revenue), `total_tender_amount` (cash+card+digital+credit collected), `expected_physical_cash` (cash-only expectation), `actual_physical_cash` (counted), `cash_shortage_excess`, `revenue_variance`/`revenue_variance_percent` are six genuinely distinct figures, never conflated. **Found this phase:** none of the six are passed through `formatMoney()` — raw backend strings, inconsistent with the rest of the app. |
| **Usability gaps found** | Two approval-type actions with no frontend permission gating; six key financial figures displayed unformatted; the discrepancy-authorization action (overriding a tolerance breach) has no confirmation step despite being exactly the kind of "significant action" Step 6 asks to confirm. |

## 5. Review

| | |
|---|---|
| **Fields** | None entered here — a checklist plus one action. |
| **Required** | N/A. |
| **Validation** | A 5-item checklist (readings closed, meter events approved, cash movements approved, cash closed, discrepancy authorized) — real, each backed by actual fetched data, not hardcoded. The **final approve button is disabled** until every check passes (`disabled={!allDone}`) — a real, working gate, not decorative. |
| **Permissions** | **None at the frontend.** `shift:approve` is Station Manager/Shift Supervisor only (confirmed in `permission_codes.py` — **not** Cashier, **not** Accountant). The button renders for every role. |
| **API requests** | `GET nozzle-readings`, `GET cash-movements`, `GET reconciliation` on load; `PATCH shifts/{id}/approve` |
| **Error states** | Toast with real backend `detail`. |
| **Draft/submission** | Real double-submit guard. Success toast only fires after `resp.ok`. |
| **Calculations** | None — and this is the biggest gap found this phase: **the brief's Step 6 requirement that the review screen show "sales totals, expense totals, payment breakdown, reconciliation differences" is not met at all.** This screen shows only pass/fail checkmarks, never the actual numbers behind them — a cashier approving the day cannot see, on this screen, what they're actually approving. |
| **Usability gaps found** | No permission gating on the one action that most needs it (final approval); no financial summary of any kind; no confirmation step before an irreversible-in-practice action (approval moves the shift to a state with no further edit path, per the existing one-way state machine — `docs/ASSUMPTIONS.md` #7). |

---

## 6. Cross-cutting findings (apply to all 5 sections / the orchestrator)

1. **`ProgressSteps` marks a step "complete" purely because its tab was opened**, not because anything was actually finished (`isComplete = i < currentStep` in the component's own logic, driven by `page.tsx` passing the *viewed* tab index as `currentStep`). This is the exact anti-pattern the brief's Step 3 explicitly warns against ("Do not mark a step complete merely because the user opened it") — found, not assumed, by reading both files together.
2. **No frontend permission gating anywhere in Daily Entry.** Every save/approve/authorize action across all 5 sections renders for every signed-in user regardless of role; the backend correctly rejects what it should (confirmed by Phase 2/3's own test suites), but the UI gives no indication a cashier's "Approve" click will fail until the toast appears.
3. **Switching tabs silently discards unsaved typed input** in whichever section was open — a real data-loss case Step 4 explicitly asks to prevent, caused by `page.tsx`'s conditional-render-per-tab structure unmounting the inactive sections.
4. **No `beforeunload` warning** exists anywhere — closing the browser tab or navigating away mid-entry with an unsaved field loses it silently.
5. **Inconsistent number formatting**: three running totals (`Sales`, `Expenses`) and six reconciliation figures (`Cash`) are not passed through the `lib/format.ts` helpers built in Phase 4, unlike the tables in the same sections that already were.
6. **No confirmation dialog** before the two most consequential single actions in the whole workflow: closing the shift's readings (ends further reading edits) and approving the day (ends further edits of any kind). Both currently fire on a single click.
7. **What already works well, confirmed not to need changing**: double-submit guards (every submit handler checks its own `submitting`/`busy` flag and the `Button` component disables itself); success is never shown before a real `resp.ok`; error messages are the backend's real text, never a generic placeholder; the 24-hour reading-correction policy is untouched by any of this (it lives in a separate page, not in Daily Entry's own flow, and nothing here duplicates or bypasses it); Decimal-safe values are never parsed into floating-point for anything other than a display-only sum.

---

## 7. What this audit does *not* claim

This audit covers the 5 Daily Entry section components and their direct API calls only. It does not re-verify the backend endpoints themselves (already covered by the passing Phase 2 test suite), does not re-litigate the 24-hour reading-correction policy (unchanged, out of scope, verified in Phase 2/3), and does not claim every possible real-world petrol station workflow is represented — only what these five screens actually do today.
