# Post-Lock Nozzle Amendment: Decision Required

## Current Behaviour

When a nozzle reading correction is submitted **after** the 24-hour correction
window has expired (`is_post_lock = True`), the system creates a
`ReadingCorrection` record with `is_post_lock = True`. On approval:

- The correction record is marked **APPROVED**.
- The **original nozzle reading is never modified** (the value in
  `shift_nozzle_readings` stays as-is).
- **No `dispensed_litres` recalculation** occurs.
- **No stock ledger adjustment** is created.

The correction is therefore **audit-only**: it records that a discrepancy was
identified and acknowledged, but it has no financial or stock effect.

## The Gap

If a nozzle closing reading of 50,000 was recorded but the true value was
49,500, the 500-litre difference shows up in the audit trail but:

1. `dispensed_litres` for that nozzle remains overstated by 500 L.
2. The daily fuel sales report overstates litres sold by 500 L.
3. The stock ledger's SALE posting for that shift is 500 L too high.
4. The tank variance report will show a 500 L positive physical surplus
   (more fuel in the tank than book stock says), which is misleading.

The owner must decide how to handle this.

---

## Option A: Audit-Only (Current Behaviour — No Code Change)

**What happens:** The approved post-lock amendment is a permanent record that
explains the discrepancy. The original reading, `dispensed_litres`, stock
ledger, and all downstream reports remain unchanged.

**Pros:**

- Simplest to maintain — no new code paths.
- The original shift's numbers are exactly reproducible at any time.
- Auditors can see both the original and the correction in the amendment trail.
- No risk of cascading recalculation errors.

**Cons:**

- Every downstream report that uses `dispensed_litres` or the stock ledger
  SALE entry is permanently overstated/understated by the error amount.
- The tank variance report will show a phantom surplus or deficit that the
  station cannot resolve through any operational action.
- The owner must mentally adjust every report by the amendment amount, or
  accept the permanent inaccuracy.

**When this makes sense:** Small, infrequent errors where the reporting
inaccuracy is immaterial, or where regulatory requirements demand that
original shift records are never retrospectively changed.

---

## Option B: Compensating Stock Ledger Entry

**What happens:** When a post-lock nozzle amendment is approved, the system:

1. Marks the correction as APPROVED (same as today).
2. Does **NOT** modify the original `shift_nozzle_readings` row (preserving
   the original record).
3. Creates a new `StockLedgerEntry` with:
   - `movement_type`: `ADJUSTMENT_POSITIVE` (if original overstated sales) or
     `ADJUSTMENT_NEGATIVE` (if original understated sales).
   - `quantity`: the absolute difference between original and corrected value.
   - `reference_type`: `"ReadingCorrection"`.
   - `reference_id`: the correction record's UUID.
   - `tank_id`: the tank connected to the corrected nozzle.
4. The audit log records the stock adjustment alongside the correction approval.

**Pros:**

- Book stock is corrected going forward — the tank variance report will be
  accurate from the next shift onward.
- The original shift record is still untouched (no retroactive rewriting).
- The stock ledger's append-only invariant is preserved (it's a new entry,
  not a modification).
- Reports that aggregate from the stock ledger (`get_book_stock()`,
  `daily-fuel-sales`) will reflect the correction.

**Cons:**

- Adds a new code path that must be tested (stock entry creation on
  amendment approval).
- The original shift's `dispensed_litres` column remains unchanged, so a
  per-shift drill-down still shows the uncorrected nozzle figure — the
  correction only appears as a separate stock adjustment entry.
- More complex to audit: an auditor must cross-reference the stock adjustment
  entry back to the reading correction to understand the full picture.
- If multiple corrections accumulate, the stock ledger has adjustment entries
  that were not caused by physical events (receipt, sale, loss) but by
  administrative corrections.

**When this makes sense:** Errors are large enough to materially affect
stock tracking and financial reporting, and the owner wants the system's
book stock to match physical reality as closely as possible.

---

## Recommendation

For a pilot deployment, **Option A** is the safe default — it introduces no
risk of cascading errors and keeps the system simple. The amendment trail
gives the owner full visibility into what happened.

If the owner finds that post-lock corrections are frequent or large enough to
distort reports, **Option B** can be implemented as a Day 5+ enhancement with
no schema migration required (the stock ledger already supports
`ADJUSTMENT_POSITIVE` / `ADJUSTMENT_NEGATIVE` movement types and
`ReadingCorrection` as a reference type).

## Stock and Financial Consequences Summary

| Consequence | Option A (Audit-Only) | Option B (Compensating Entry) |
|---|---|---|
| Original nozzle reading | Preserved | Preserved |
| `dispensed_litres` column | Stays incorrect | Stays incorrect (original shift) |
| Stock ledger | No change | New ADJUSTMENT entry corrects book stock |
| Tank variance report | Phantom surplus/deficit | Corrected from next shift onward |
| Daily fuel sales report | Overstated/understated | Corrected via stock ledger aggregation |
| Append-only ledger invariant | N/A | Preserved (new entry, no UPDATE/DELETE) |
| Audit trail | Correction record only | Correction record + stock adjustment entry |
| Complexity | None (current code) | One new code path on approval |

## Decision

> **Owner: please select Option A or Option B.**
>
> This document will be updated with your decision, and implementation (if
> Option B) will proceed in the next approved work phase.
