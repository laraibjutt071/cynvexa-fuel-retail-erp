# Phase 10B — Supplier Invoice & Payment UI

Status: **implemented and locally tested. NOT DEPLOYED** — committed locally only, per the explicit instruction to stop before push/deploy.

## 1. Initial audit findings (code-verified, not assumed from docs)

Models read: `backend/app/models/supplier.py`, `supplier_invoice.py`, `supplier_payment.py`. Endpoints read: `backend/app/api/suppliers.py`, `backend/app/api/supplier_ledger.py`, and the statement endpoint in `backend/app/api/reports.py`. Schemas read: `backend/app/schemas/supplier.py`, `supplier_ledger.py`, `reports.py`.

### Backend capability matrix

| Feature | Existing endpoint | Existing service/model | Existing tests | Status |
|---|---|---|---|---|
| Supplier listing | `GET /organizations/{org}/suppliers` | `Supplier` | none (gap) | Full |
| Supplier details | `GET /organizations/{org}/suppliers/{id}` | `Supplier` | none (gap) | Full |
| Supplier create | `POST /organizations/{org}/suppliers` (`supplier:manage`, Owner-only in the current seed) | `Supplier` | none (gap) | Full |
| Supplier update | `PATCH /organizations/{org}/suppliers/{id}` (`supplier:manage`) | `Supplier` | none (gap) | Full |
| Invoice listing | `GET /organizations/{org}/suppliers/{sid}/invoices` (per-supplier only) | `SupplierInvoice` | `test_supplier_ledger.py` (indirect) | Full, but per-supplier only |
| Invoice creation | `POST /organizations/{org}/suppliers/{sid}/invoices` (`supplier_ledger:record`) | `SupplierInvoice` | `test_supplier_ledger.py` | Full |
| Invoice details | *(no dedicated endpoint)* | — | — | **Missing** — not built; derived client-side from the list |
| Invoice approval | *(does not exist — invoices have no status field)* | — | — | **Missing** — not built, not fabricated |
| Payment listing | `GET /organizations/{org}/suppliers/{sid}/payments` (per-supplier only) | `SupplierPayment` | `test_supplier_ledger.py` | Full, but per-supplier only |
| Payment recording | `POST /organizations/{org}/suppliers/{sid}/payments` (`supplier_ledger:record`) | `SupplierPayment` | `test_supplier_ledger.py` | Full |
| Payment approval | `PATCH .../payments/{id}/approve` (`supplier_ledger:approve`) | `SupplierPayment` | `test_supplier_ledger.py` | Full |
| Payment reversal | `PATCH .../payments/{id}/reverse` (`supplier_ledger:approve`) | `SupplierPayment` | `test_supplier_ledger.py` | Full |
| Outstanding balance (per supplier) | `GET .../suppliers/{sid}/balance` | `app/core/supplier_ledger.py::get_supplier_balance` | `test_supplier_ledger.py` | Full |
| Outstanding balances (all suppliers) | `GET /organizations/{org}/suppliers/balances` + `/balances/export` (CSV) | same | `test_supplier_ledger.py` | Full |
| Supplier ledger / statement | `GET .../suppliers/{sid}/statement?date_from&date_to` | `app/api/reports.py::supplier_ledger_statement` | none (gap) | Full |

**Balance formula** (unchanged, backend-authoritative, never recomputed in the frontend): `sum(all invoices) − sum(approved, non-reversed payments)`.

### Genuine gaps found (documented, not silently invented)

1. **No per-invoice outstanding/paid amount.** `SupplierInvoice` has no `status`, `paid_amount`, or `invoice_id` link from `SupplierPayment` — payments are supplier-level only, never allocated to a specific invoice. The brief's spec asked for "paid amount, outstanding amount" per invoice; that data does not exist. **Not fabricated.** The UI instead shows each invoice's amount plainly and the supplier's one real outstanding balance separately and clearly labeled, exactly as Section H requires ("clearly distinguish invoice amount, paid amount, outstanding amount" — done at the supplier level, the only level the data actually supports).
2. **No invoice approval workflow.** Invoices are final the moment they're recorded — there is no status field to approve. Sections C/E's "invoice approval" asks have nothing to build against; no fake approve button was added.
3. **No single-invoice detail endpoint.** Not built — the per-supplier invoice list is small enough that the frontend's own fetched row data is the invoice detail; no backend change was needed or made.
4. **No `due_date` field on `SupplierInvoice` at all**, so "overdue invoices" (Section H) cannot be computed from real data. **Not fabricated.** No overdue indicator appears anywhere in the UI.
5. **No cross-supplier invoice/payment listing endpoint** — only `GET .../suppliers/{sid}/invoices` and `.../payments` exist, both scoped to one supplier. See Section 3 below for how this shaped the UI.
6. **Suppliers have no station concept at all** (`Supplier.organization_id` only, no `station_id` anywhere in the three models) — a "station filter" for suppliers/invoices/payments has no backing field. Confirmed, not assumed: `tanker_receipt_id` on `SupplierInvoice` is optional and never denormalizes a station onto the invoice.

**No backend code was changed in this phase.** Every page below is built entirely against the existing endpoints in the matrix. This was a deliberate choice (Section 9 of the brief: "Prefer frontend-only... if no backend/schema changes are necessary, do not create a migration") rather than adding a new cross-supplier aggregation endpoint purely for listing convenience — see Section 3.

## 2. Features completed

- **Supplier directory** (`Directory` tab): search (name/phone/email), active/inactive filter, each row's live outstanding balance, Add/Edit supplier (gated on `supplier:manage`).
- **Supplier workspace** (opened via "View" on a directory row): a per-supplier panel with its own outstanding-balance stat card and three sub-tabs:
  - **Invoices**: list + total invoiced + "Record invoice" form (amount, invoice date, reference, description — `tanker_receipt_id` deliberately omitted from the form, see Known Limitations).
  - **Payments**: list + status filter (pending/approved/reversed, computed client-side from `approved_at`/`reversed_at` — the backend's own real fields, not a fabricated status) + total approved + "Record payment" form + inline Approve (confirmation dialog) and Reverse (reason dialog, reusing the existing `ReasonDialog` component) actions.
  - **Statement**: date-range-filtered ledger (opening balance, running balance per entry, closing balance) reusing the existing `/statement` endpoint verbatim.
- **Balances tab** (page-level, cross-supplier): the real financial summary Section H asks for — total accounts payable, count of suppliers with an outstanding balance, a sortable per-supplier balance table, and the existing CSV export button.
- **Multi-tenant/security**: page gated on `supplier:read` (`AccessDenied` otherwise); Add/Edit gated on `supplier:manage`; Record invoice/payment gated on `supplier_ledger:record`; Approve/Reverse gated on `supplier_ledger:approve`. All enforcement is backend-first — every frontend gate mirrors a real `require_permission` dependency; the frontend gate is UX only, never the actual boundary (verified by the Cashier/Accountant Playwright tests below).
- **Nav integration**: a "Suppliers" item added to the main sidebar (`components/AppShell.tsx`), gated on `supplier:read`, using the existing `buildNav`/translation-key pattern (new `nav.suppliers` key in `lib/i18n/translations.ts`).

## 3. Features not implemented, and why

- **A single cross-supplier invoice/payment table** (Sections C/F's literal ask) was **not** built as a flat all-suppliers table. The backend has no such endpoint, and building an N+1 client-side merge (fetch every supplier's invoices/payments and concatenate) would either require a new backend aggregation endpoint (avoided per the "prefer frontend-only" instruction) or duplicate real backend work in the frontend for no architectural reason. Instead, invoice/payment listings are scoped per-supplier via the directory → workspace flow, matching the backend's own per-supplier endpoint design and the existing **Credit Customers** page's identical, already-shipped UX pattern (`frontend/app/dashboard/org/[orgId]/credit-customers/page.tsx`: pick a customer, see their own statement — no flat cross-customer ledger either). The **Balances tab** is this page's real cross-supplier financial summary, backed by a real endpoint, not an approximation.
- **Invoice approval workflow** — not built; no backend capability exists (see gap #2 above). Building one would mean adding a `status` column to `SupplierInvoice` (a migration), which Section 9 requires stopping for explicit approval on — not done without that approval.
- **Per-invoice paid/outstanding tracking** — not built, same reasoning (gap #1); would require an `invoice_id` FK on `SupplierPayment` plus allocation logic, a feature-sized backend change, not a UI task.
- **Overdue invoice indicator** — not built; no `due_date` field exists (gap #4).
- **Duplicate-invoice detection** — the backend has none; not fabricated client-side (a client-side-only check would be trivially bypassable and give false confidence).
- **Linking an invoice to its originating tanker receipt** (`tanker_receipt_id`) — the create-invoice form omits this optional field. Picking a specific existing receipt would need its own receipt-search UI; out of scope for this pass, and the field already defaults to `null` on the backend with no loss of correctness.
- **Roman Urdu translation** of the new page's content strings — not done, consistent with this project's already-documented precedent of several operational pages not yet being translated (`docs/REMAINING_RISKS.md`, Phase 7 UX-upgrade section). Only the one sidebar nav label was added to the translation dictionary (required by `AppShell.tsx`'s existing pattern), set to the same English string for both languages.

## 4. Files created and modified

**Frontend (new)**:
- `frontend/app/dashboard/org/[orgId]/suppliers/page.tsx` — the entire feature (directory, workspace, invoices/payments/statement panels, balances tab).
- `frontend/e2e/suppliers.spec.ts` — 3 new Playwright tests.

**Frontend (modified)**:
- `frontend/lib/types.ts` — expanded `Supplier` (added `contact_phone`, `contact_email`, timestamps — it was a partial stub before), and added `SupplierInvoice`, `SupplierPayment`, `SupplierLedgerStatementEntry`, `SupplierLedgerStatement`.
- `frontend/components/AppShell.tsx` — added the "Suppliers" nav item (`Package` icon, gated on `supplier:read`).
- `frontend/lib/i18n/translations.ts` — added the `nav.suppliers` key.

**Backend**: no files created or modified. Confirmed via `git status --short backend/` before writing this report — empty.

## 5. Backend APIs reused (no new endpoints)

Every endpoint in the capability matrix above with status "Full" — `GET/POST /organizations/{org}/suppliers`, `GET/PATCH /organizations/{org}/suppliers/{id}`, `GET/POST .../suppliers/{id}/invoices`, `GET/POST .../suppliers/{id}/payments`, `PATCH .../payments/{id}/approve`, `PATCH .../payments/{id}/reverse`, `GET .../suppliers/{id}/balance`, `GET .../suppliers/balances`, `GET .../suppliers/balances/export`, `GET .../suppliers/{id}/statement`.

## 6. Backend changes

**None.** No model changed, no migration created or needed, no new endpoint added. This was a deliberate scope decision (see Section 3) rather than an oversight.

## 7. Security and multi-tenant verification

- Every request goes through `authFetch`, which attaches the real bearer token; every backend endpoint still goes through its own `require_permission` dependency resolving `organization_id` from the URL path — the frontend never computes or trusts an org/permission decision on its own.
- Verified with real, non-superuser, role-scoped users (not just a superuser bypass test):
  - **Cashier / Operator** (no `supplier:read` at all in the seeded role) gets `Access restricted` on `/suppliers` — confirmed by a Playwright test hitting the real page, not a mocked permission.
  - **Accountant** (has `supplier:read`/`supplier_ledger:*` but not `supplier:manage`) can see the page and its data but has no "Add supplier" control — confirmed by a Playwright test asserting the button has zero matches, not just that it's disabled.
- Suppliers are organization-wide with no station concept in the data model (confirmed in the audit) — there is accordingly no station-isolation claim to make for this feature beyond the existing organization-membership check every endpoint already enforces; the persistent station switcher is unaffected and untouched by this phase.
- Payments are never auto-approved: the "Record payment" dialog's own description states this, the newly-recorded payment visibly shows a `pending` badge, and the approve action requires a separate explicit click plus `supplier_ledger:approve` — verified end-to-end in the Playwright test (balance stays at the pre-payment figure until the explicit approve step, then drops).

## 8. Backend test results

No backend code was changed, so no new backend tests were needed or added, but the full suite was still executed to confirm nothing broke:

```
361 passed, 3 warnings, 1 error in 802.38s (first run)
```

The 1 error (`test_login_success_returns_access_token_and_sets_refresh_cookie`, a `UniqueViolationError` on `ix_permissions_code`) was investigated, not dismissed: it was caused by running this pytest suite *concurrently* with the Playwright e2e stack against the **same** dev database. `backend/tests/conftest.py`'s session-scoped `_create_schema` fixture runs `DROP SCHEMA public CASCADE` against whatever `DATABASE_URL` is configured — and this container's `DATABASE_URL` points at the real local dev database (`cynvexa`), not an isolated test database, because no separate `TEST_DATABASE_URL` is configured in this Docker Compose setup. Running pytest while Playwright's `global-setup.ts` was also seeding data into the same database raced the two. **Re-ran in isolation** (no concurrent e2e run): `tests/test_auth.py` → **9 passed**. Full suite re-run afterward → **362 passed, 0 failed, 0 errors.** This is a real, previously-undocumented local-environment hazard (not a production issue — production never runs pytest against Render/Neon) — see the new `REMAINING_RISKS.md` entry.

## 9. Playwright test results

New: `frontend/e2e/suppliers.spec.ts` (3 tests) —
1. End-to-end: create a supplier, record a PKR 50,000 invoice, record a PKR 20,000 payment (balance stays at 50,000 while pending), approve it (balance drops to 30,000), confirm the statement shows both entries with the correct running balance, confirm the Balances tab shows the same figure.
2. Cashier sees `Access restricted`.
3. Accountant has no "Add supplier" control.

Full suite (8 spec files, 47 tests total): **47 passed, 0 failed** when run at `--workers=3`. At the default 7 workers, 10 tests intermittently failed on a login timeout (`expect(page).toHaveURL(/\/dashboard/)` never leaving `/login`) — this is the **same pre-existing, already-documented flake** from Phase 10a (`docs/PHASE_10A_METER_EVENT_UI_REPORT.md`: "running the full suite at 7 parallel workers intermittently fails 1–2 login-dependent tests... under concurrent-login load"). It affected `company-overview.spec.ts`, `daily-entry.spec.ts`, `daily-entry-roles.spec.ts`, `day2-pages.spec.ts`, `role-permissions.spec.ts`, `meter-events.spec.ts`, and `suppliers.spec.ts` this run — none of those files' own logic failed; every one of the 10 affected tests passed cleanly when the worker count was reduced. Not a Phase 10B regression.

## 10. Typecheck and build results

`docker compose build frontend` → `next build` (Next.js 16.4.3, Turbopack): **compiled successfully, TypeScript passed with zero errors**, `/dashboard/org/[orgId]/suppliers` listed in the route output.

## 11. Git commit hash

Committed locally. Hash and verification steps are run immediately after this report (see the final response for the exact hash) — `git diff`/`git status` were reviewed first for secrets and unrelated files; only the files listed in Section 4 are included.

## 12. Deployment status

**NOT DEPLOYED.** No push, no Render deploy, no production migration — none was needed, and none was run. Per the brief, this stops here for approval.

## 13. Remaining risks (full list, not just this phase's)

New, from this phase:
- The 6 genuine backend gaps listed in Section 1 (per-invoice outstanding/paid tracking, invoice approval workflow, single-invoice endpoint, overdue detection, duplicate-invoice detection, station concept for suppliers) remain open — each would be a real, scoped follow-up phase, not a quick addition.
- The local dev-environment DB-sharing hazard discovered in Section 8 (running backend pytest and the Playwright stack concurrently corrupts shared dev data) is now documented in `docs/REMAINING_RISKS.md` so it isn't rediscovered the hard way again.
- No Roman Urdu translation for the new page's own content (nav label only).

Everything else (production deploy credentials not available, TLS not tested end-to-end, load testing not performed, etc.) is unchanged from every prior phase's own stated limitations.

## 14. Recommended next step

Review this report and the live page locally (`docker compose up`, `/dashboard/org/{orgId}/suppliers` as an Owner/Accountant/Station Manager). If approved: push, verify Render auto-deploy for both services (health/ready + route-availability only, per the established limitation), and decide whether any of the 6 documented backend gaps should become their own phase (invoice approval and per-invoice payment allocation are the two most likely to matter for a real accounts-payable workflow, and both are schema changes requiring their own approval before implementation).
