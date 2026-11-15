# CYNVEXA — Phase 5 Daily Entry & Operational Usability Report

**Date:** 2026-11-15
**Scope:** Usability, clarity, and permission-gating improvements to the existing 5-step Daily Entry workflow (Readings → Sales → Expenses → Cash → Review). No API contract, business calculation, database schema/migration, or existing role permission grant was changed. The audit behind this report is `docs/PHASE_5_DAILY_ENTRY_AUDIT.md` — read that first for what was found before anything was changed.

---

## 1. Executive summary

Every fix in this phase traces to a specific, named finding in the Step 1 audit — nothing was changed speculatively. The headline result is not a new feature; it's a **real, previously-undiscovered permission gap found by actually driving the workflow as a Cashier**, not by reading a permission table in isolation: the Cashier/Operator role can open and close a shift (`shift:open`/`shift:close`) but cannot list the tanks or nozzles to record a reading against (missing `tank:read`/`nozzle:read`), so the Readings step is currently unusable for that role. This is documented, test-proven, and **not silently fixed** — changing a seeded role's permissions needs owner approval per this phase's own rules, so it's flagged in Section 7 instead.

Beyond that finding, this phase fixed: a progress indicator that marked steps "complete" just for being opened (the brief's own named anti-pattern); zero frontend permission gating across all five sections (every save/approve/authorize action rendered for every role); inconsistent financial-number formatting (three running totals, six reconciliation figures); no confirmation before the two most consequential actions in the whole workflow (closing readings, approving the day, authorizing a discrepancy); and a Review screen that showed only checkmarks, never the actual sales/expense/reconciliation figures being approved.

---

## 2. Existing behavior (confirmed, not assumed — see the audit for full detail)

- Each of the 5 sections already does real, immediate API calls per action (no fake batched "draft" existed or was claimed).
- Double-submit guards already existed on every submit handler (`if (submitting) return` + the `Button` component's own `busy`-disables-itself behavior) — confirmed working, not touched.
- Success was already only ever shown after a real `resp.ok` — confirmed, not touched.
- The 24-hour reading-correction policy lives entirely outside Daily Entry (a separate page, Phase 3) and nothing in this phase's changes touches it, reads it, or duplicates its logic.
- Decimal-safe values from the backend were already never parsed into floating point for anything other than a display-only client-side sum (Sales/Expenses running totals) — unchanged.

---

## 3. Changes made, mapped to the audit's findings

### 3.1 Real step completion, not "opened" (Step 3)

`components/ui/ProgressSteps.tsx` gained an optional `completedSteps?: Set<number>` prop — when provided, a step only shows its checkmark if its index is in that set; `currentStep` now only controls which step is highlighted as active. Existing callers that don't pass it keep the old behavior unchanged (nothing else in the app uses this component yet, so this was a safe, additive change).

`daily-entry/page.tsx` now computes real completion from actual data: Readings complete only once `shift.status !== "open"` (the backend already refuses to close a shift with any reading missing); Cash complete only once a reconciliation record genuinely exists (fetched once at the page level specifically for this signal); Review complete only once the shift is `approved`. Sales and Expenses have no independent "finished" state in this business process (entries can be added any time before cash closing, and Review's own checklist never required a minimum count of either) — they read as complete only once the whole day is approved, matching that checklist rather than inventing a new rule.

### 3.2 Frontend permission gating added across all 5 sections (Step 7 groundwork)

None of the 5 sections had any `usePermissions` call before this phase. Added, each verified against the real backend permission code it mirrors (never guessed):

| Section | Action gated | Permission | Behavior when missing |
|---|---|---|---|
| Readings | Opening dip/totalizer inputs | `shift:open` | "Waiting for an authorized user to record this" |
| Readings | Closing dip/totalizer inputs | `shift:close` | Same |
| Readings | "Close today's readings" | `shift:close` | Button hidden entirely |
| Sales | Record-collection form | `shift_reconcile:record` | Form hidden |
| Sales | "Reverse" link | `shift_reconcile:approve` | Link hidden |
| Expenses | Record-expense form | `expense:record` | Form hidden |
| Cash | Cash-movement approve link | `shift_reconcile:approve` | Link hidden |
| Cash | Discrepancy "Authorize" button | `shift_reconcile:approve` | Replaced with an explanatory message naming who can |
| Review | "Approve today's entry" | `shift:approve` | Replaced with `AccessDenied` naming who can |

The backend remains the only real security boundary in every case — these are UX improvements on top of an already-correct backend (confirmed again this phase: see Section 6's new Playwright tests proving the backend independently rejects what the UI now hides).

### 3.3 Consistent financial formatting (Step 2 / Step 5)

Applied `lib/format.ts`'s `formatMoney()` (built in Phase 4) to every previously-unformatted figure found in the audit: Sales' and Expenses' running totals (were `total.toFixed(2)`, no thousands separator), and all six of Cash's reconciliation tiles (expected revenue, total collected, expected cash, actual cash, shortage/excess, revenue variance) — previously raw backend strings. **No value, rounding, or calculation changed** — only display formatting. The six reconciliation figures were already, and remain, genuinely distinct (revenue ≠ cash ≠ card ≠ credit was already true in the data model; this phase only made the numbers easier to read, not more separated than they already were).

### 3.4 Required-field clarity (Step 2)

Readings' four numeric inputs (tank opening/closing dip, nozzle opening/closing totalizer) gained `required`, `min="0"` (real HTML5 validation strengthening, not weakening — previously these had neither), a visible `*` in the placeholder, and an `aria-label` naming exactly which tank/nozzle the field belongs to (previously identifiable only by table position, not announced to assistive tech at all).

### 3.5 Confirmation before the workflow's three most consequential single-click actions (Step 6)

All three use the pre-existing `ConfirmDialog` component (built Phase 3), not a new pattern:
- **Closing today's readings** — previously fired on one click; now confirms first, with a plain-language explanation of what it blocks afterward.
- **Approving the day** — same; the dialog explicitly tells the signer this locks every record for the day.
- **Authorizing a cash/revenue discrepancy** — previously fired on one click despite being exactly the kind of override Step 6 asks to confirm; now confirms first.

### 3.6 The Review screen now shows what it's approving, not just checkmarks (Step 6)

`ReviewSection.tsx` now fetches the same tenders/expenses/reconciliation data the Sales/Expenses/Cash sections already show, and renders a real summary card above the approve action: sales collected, expenses recorded, and (once cash is closed) expected revenue, actual cash counted, shortage/excess, and revenue-vs-collections variance — all `formatMoney()`-formatted, all genuinely fetched for this screen, none estimated or duplicated from a hardcoded value.

### 3.7 Preventing silent data loss when switching tabs (Step 4)

The audit found that `page.tsx` unmounts whichever section isn't active, silently discarding a typed-but-unsaved value. Fixed with a real, verifiable mechanism, not a claimed "autosave" (nothing is persisted - this only warns):
- Each section now reports its own "has unsaved input" state up to the page via an `onDirtyChange` callback (computed from its actual form state - e.g. Sales is dirty only while `amount` has text; Cash is dirty while either its movement form or its closing form has text).
- Each `record*`/save function now clears its own input's tracked value on a successful save, so a saved reading doesn't keep registering as "unsaved" afterward (a real bug caught and fixed during this phase's own implementation, not shipped and found later).
- Switching tabs while the active section is dirty now opens a confirmation dialog ("Leave without saving?") instead of silently discarding the input.
- A `window.beforeunload` handler warns on an actual browser/tab close while any section is dirty.

**Honest limitation, not hidden**: this does not make switching tabs preserve the unsaved value — it only warns before the loss happens, same as most real-world forms that don't have true autosave. A full architectural fix (keeping all 5 sections mounted simultaneously) was judged too large a structural change for this phase's "do not rewrite the Daily Entry module" rule.

---

## 4. The critical finding: Cashier cannot use the Readings step at all

Found by actually logging in as a real, non-superuser Cashier/Operator account and driving the UI — not by reading the permission table and assuming it worked:

- Cashier/Operator's seeded permissions (`app/core/permission_codes.py::SEED_ROLES`) include `shift:open` and `shift:close` (the permissions that gate *recording* a reading) but **not** `tank:read` or `nozzle:read` (the permissions that gate *listing* the tanks/nozzles to record one against — `app/api/tanks.py`, `app/api/nozzle_overview.py`).
- Confirmed directly: `GET /organizations/{id}/stations/{id}/tanks` with a real Cashier token returns `403 {"detail": "You do not have permission to perform this action."}`.
- Effect: the Readings tab's tank and nozzle tables never load for this role — not a slow load, a permanent one, because the underlying fetch 403s every time. A Cashier signed in today cannot see anything to enter a reading against, even though the role is clearly meant to be able to (it holds the permission to actually record one).
- **Not fixed this phase.** Phase 2's non-negotiable rules require owner approval before changing a seeded role's permissions, and this phase's own rules repeat "preserve role and tenant restrictions." This is flagged as the single highest-priority item for the owner to review (Section 7), with the exact two permissions (`tank:read`, `nozzle:read`) that would resolve it if approved.
- Proven with a real, passing Playwright test (`e2e/daily-entry-roles.spec.ts`) that asserts the *current* (broken) behavior — written so that if the permission is later added, that specific test starts failing as a deliberate signal to update it, not a silent pass-through.

---

## 5. Financial and stock clarity (Step 5) — status

Revenue, cash, card, digital, credit, expenses, book stock, and physical dip were **already** modeled as genuinely distinct values before this phase (confirmed again by re-reading the Cash section's reconciliation fields and the Readings section's book-stock-vs-dip display) — this was not a gap to close, it was already correct in substance. This phase's real contribution here is formatting consistency (Section 3.3) and surfacing those same real figures on the Review screen (Section 3.6), not a new separation that didn't exist before.

**Confirmed unchanged, as required:** no stock or financial formula was touched. `book_stock` (ledger-derived) and a tank's physical dip reading remain two separate fields, displayed side by side, never overwritten into each other — this was already true and nothing in this phase's diff touches `app/core/revenue.py`, `app/core/reconciliation.py`, or any stock-ledger code.

---

## 6. Testing (Step 8, exact results)

### 6.1 Backend — full pytest suite (no backend file touched this phase; re-run per the brief's explicit instruction)
```
248 passed, 0 failed, 0 skipped, 0 errors
3 warnings (pre-existing, non-fatal - same as Phases 2-4, unrelated)
Exit code: 0
Duration: 603.84s (10 min 3 sec)
```

### 6.2 Frontend — TypeScript and production build
Re-run after every structural change this phase:
```
npx tsc --noEmit  → 0 errors (every run)
npm run build     → Compiled successfully, 16/16 routes generated, exit code 0
```

### 6.3 Playwright — full suite, including new role-based and regression-caught fixes

**A real regression was introduced by this phase's own confirmation-dialog additions, caught by the existing suite, and fixed** - not hidden: the pre-existing full-workflow test (`daily-entry.spec.ts`) clicked "Close today's readings" and "Approve today's entry" expecting an immediate state change; both now open a confirmation dialog first (Section 3.5). The test was updated to click through the dialog (a real, intentional UX change, not a weakened assertion) and to expect `"28,000.00"` instead of `"28000.00"` for the reconciliation tiles now formatted by Section 3.3 — the same category of accepted test-maintenance already on record from Phases 2 and 4.

```
30 total: 28 passed, 2 failed
```

The **2 failures are the same pre-existing, unrelated ones tracked since Phase 2** (`day2-pages.spec.ts`'s tank empty-state text, and its credit-customers locator ambiguity) — re-confirmed unchanged, not touched, not hidden.

**New tests this phase** (`e2e/daily-entry-roles.spec.ts`, 7 tests, all passing), using real role-scoped users seeded against a new, dedicated station (station 3 — station 1's shift is pre-approved for report tests, station 2 is used by the existing full-workflow test, so a third was needed to avoid racing either):

| Test | Verifies |
|---|---|
| Shift Supervisor starts today's entry and records a reading | Entry-level permissions work for the role that actually has them |
| Shift Supervisor sees the real Approve button | Review/approval permission (Step 7) |
| Approve button stays disabled until the checklist passes | The gate is real, not decorative |
| Cashier sees Access restricted on Review, not the Approve button | Review-permission restriction (Step 7) |
| **Cashier's role is missing `tank:read`/`nozzle:read`** | The critical finding in Section 4, proven against the real API |
| Cashier's token is rejected (403) on a direct shift-approve API call | Backend independently rejects what the UI hides |
| Cashier cannot read shifts for a fabricated organization id | Station/tenant isolation for a real role |

This required extending `e2e/global-setup.ts` with a third station and a second per-role station-scoped assignment (role users already had one at station 1 from Phase 3, for that file's own tests) — additive, not a change to any existing assignment.

### 6.4 What Step 8 asked for that was not separately built
- **Dedicated standalone "validation tests" / "duplicate submission tests"** were not written as their own isolated unit tests — the double-submit guards were confirmed by code read (Section 2) and exercised incidentally by the existing and new Playwright flows, not by a dedicated test designed to hammer a button twice. Named here rather than claimed as separately covered.
- **Dedicated "financial display precision" tests** beyond what already exists: the Phase 4-era precision bug class (formatting silently rounding a decimal) was specifically re-checked by hand against every new `formatMoney()` call site added this phase (none round incorrectly - `formatMoney` always shows exactly 2 decimals, and none of this phase's additions touch `formatLitres`, which is where the earlier precision bug lived). Not re-proven with a new automated test this phase.

---

## 7. Remaining issues (ranked, named honestly)

1. **[CRITICAL — requires owner approval]** Cashier/Operator's seeded role is missing `tank:read` and `nozzle:read`, making the Readings step unusable for that role today (Section 4). Recommended fix (not applied): add both permissions to the seeded `Cashier / Operator` role in `app/core/permission_codes.py::SEED_ROLES`, then re-run `python -m app.seed permissions-roles` against the real database. This is a two-line, low-risk change once approved - it was not made unilaterally because this phase's rules require approval for any role-permission change.
2. **[Design limitation, named in Phase 4 and unchanged]** `DataTable`/`Skeleton` are still not adopted inside Daily Entry's own tables - this phase touched financial formatting and permissions, not the table-rendering pattern itself, to keep the diff reviewable and avoid a second large simultaneous change.
3. **Tab-switching still loses unsaved input if the user proceeds past the new warning** (Section 3.7) - the warning is real, the underlying unmount-on-switch behavior is not architecturally fixed, by design (avoiding a Daily Entry rewrite).
4. **No dedicated duplicate-submission or precision unit tests** were added this phase (Section 6.4) - existing guards were verified by read and incidental test coverage only.
5. **Sales/Expenses permission gating uses the same permission for recording and viewing the record form** - e.g., Accountant holds `shift_reconcile:record` too (per the seed role list), so an Accountant would also see the Sales recording form, which may or may not match the owner's actual intent for that role; not changed, since narrowing it is itself a permission-model decision requiring the same approval as item 1.

---

## 8. Final acceptance

**Not fully met, and this report does not claim it is.** The brief's own final acceptance line is: *"A cashier should be able to complete the supported Daily Entry workflow without needing a developer to explain each field."* This phase found, by actually testing as a Cashier, that the Readings step cannot currently be completed by that role at all (Section 4) - a real blocker to that exact acceptance criterion, not a polish gap. Sales, Expenses, and Cash recording (the permissions Cashier does hold: `shift_reconcile:record`) are now clearer (formatting, required-field indicators, confirmation dialogs) and are genuinely usable without a developer's help. Review is informative for roles that can reach it. The one missing piece is specific, proven, and squarely in the owner's hands to approve, not a vague "needs more work."

---

## 9. Final verdict

**READY WITH DOCUMENTED LIMITATIONS.**

The usability and permission-gating work completed this phase is real, test-verified, and traced to specific audit findings - not a cosmetic pass. It also surfaced a genuine, previously-unknown, and currently-blocking permission gap for the Cashier role, which is reported prominently rather than smoothed over, exactly because the honest answer to "is this ready" depends on the owner's decision about item 1 in Section 7. Backend is unchanged and fully re-verified (248/248); frontend typecheck and build are clean; Playwright is 28/30 with the 2 failures being the same pre-existing, unrelated ones from every prior phase, plus 7 new passing tests using real role accounts, one of which exists specifically to prove the critical finding rather than hide it.
