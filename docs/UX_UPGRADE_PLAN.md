# UX Upgrade Plan — Premium Black/Blue Redesign & Daily-Ops UX

This is an **upgrade** of the existing CYNVEXA frontend/backend, not a rebuild. Per the brief's own rule: do not rebuild working modules, do not replace real API data with mock data, do not weaken authorization, do not touch correct financial calculations. Nothing in this plan proposes any backend business-logic change — it is a frontend design-system, i18n, and UX pass over an already-working app (see `ARCHITECTURE.md`, `docs/IMPLEMENTATION_PLAN.md`).

## 1. Audit of the existing system (before changing anything)

**Backend** — nothing missing for the work planned here. Fuel ledgers, shift operations, financial reconciliation, permissions/approvals, audit trail, inventory, suppliers, credit customers, and dashboard/report endpoints all already exist and are exercised by 176+ backend tests. The one gap relevant to this upgrade: **no `User.preferred_language` field** (or equivalent) exists yet, so there is no backend mechanism to persist a language choice server-side today. Confirmed by reading `backend/app/models/user.py` and grepping the whole `models/` tree for `language`/`locale` — no matches.

**Frontend** — Next.js App Router + React 19 + TypeScript + Tailwind v4, a real design-token system (`app/globals.css`), a small reusable component set (`components/ui/Button.tsx`, `Badge.tsx`, `Field.tsx`, `EmptyState.tsx`, `Toast.tsx`, `components/Card.tsx`), a permission-aware sidebar (`components/AppShell.tsx`), and a genuine Daily Operations workflow (`app/dashboard/org/[orgId]/station/[stationId]/daily-entry/*`) already wired to the real backend end-to-end (confirmed passing: 7/7 Playwright e2e tests before this pass started).

### Real defect found during the audit (not cosmetic — functionally broken CSS)

`app/globals.css` declared `--color-ink`, `--color-ink-soft`, `--color-ink-faint`, `--color-surface`, `--color-surface-muted`, and `--color-border` only inside `:root`, but **never re-declared them inside the `@theme inline` block**. Tailwind v4 only generates utility classes for tokens registered under `@theme` — a plain `:root` custom property is invisible to its class generator. Verified directly, not assumed: grepped the previous production build's compiled CSS chunk for `.text-ink`, `.bg-surface-muted`, `.border-border` — **zero matches**, while `.bg-brand-50` (which *was* registered) was present. This means `text-ink`, `bg-surface-muted`, `bg-surface`, `border-border`, `text-ink-soft`, and `text-ink-faint` — used throughout `Button.tsx`, `Field.tsx`, `EmptyState.tsx`, `Toast.tsx`, `Badge.tsx`, `AppShell.tsx`, and several daily-entry/today-overview screens — were silently rendering as unstyled (browser-default text color, transparent/no background, no visible border) the entire time. This is fixed as part of Stage 2 below (every token the component library uses is now registered under `@theme inline` and verified present in a real production build's compiled CSS).

### Other pre-existing inconsistencies found and folded into the Stage 2 fix

- 17 files (mostly the Phase 6-era dashboard pages — `app/dashboard/page.tsx`, `app/dashboard/org/[orgId]/page.tsx`, `.../station/[stationId]/page.tsx`, `app/login/page.tsx`) used raw Tailwind palette classes (`bg-white`, `text-slate-900`, `border-slate-200`, `bg-slate-900`, `text-teal-700`, `text-red-700`, `text-emerald-700`, `text-amber-700`, `focus:ring-teal-500`, etc.) instead of the design-token classes, defeating the point of having a centralized palette. The newer Daily Entry / Today's Overview screens (built in the prior UI phase) were already fully token-based and needed no change.
- "Success" reused the brand/primary color (there was no distinct success token) — conflates "this is the primary action color" with "this succeeded," which the new spec explicitly treats as two different semantics.
- Native form controls (date inputs, selects) had no `color-scheme` declared, so in a dark theme they would render with the browser's light-mode UA styling.

## 2. New design system — premium black/blue (Stage 2, implemented)

All tokens are defined once in `frontend/app/globals.css` and re-exposed under `@theme inline` so every one of them is a real, verified Tailwind utility (confirmed again after this change: grepped the new production build's compiled CSS for `.text-ink`, `.bg-surface-muted`, `.border-border`, `.bg-sidebar`, `.text-accent`, `.bg-success-100`, `.bg-brand-500` — all present).

| Token | Value | Use |
|---|---|---|
| `background` | `#080D18` | Page canvas |
| `sidebar` | `#0C1424` | Nav rail only |
| `surface` | `#111C30` | Cards / panels |
| `surface-elevated` | `#17243A` | Hover states, elevated/nested panels |
| `surface-muted` | `#0A1120` | Recessed zones: disabled inputs, subtle fills |
| `border` | `#22304A` | All borders/dividers |
| `ink` / `ink-soft` / `ink-faint` | `#F8FAFC` / `#94A3B8` / `#64748B` | Primary / secondary / faint text |
| `brand-50…700` | translucent blue → `#2563EB` → `#1E40AF` | Primary action color + its tint scale |
| `accent` | `#38BDF8` | Electric-blue highlight (active nav label, links) |
| `success-50/100/600` | translucent green → `#22C55E` | Approved/good — now decoupled from `brand` |
| `warning-50/100/600` | translucent amber → `#F59E0B` | Pending / needs attention |
| `caution-50/100/600` | translucent orange → `#FB923C` | Second warning tier (kept from the previous palette; the new spec doesn't call for two tiers, but several existing screens already rely on the distinction, e.g. "closing reading lower than opening") |
| `danger-50/100/600` | translucent red → `#EF4444` | Real errors/discrepancies only |

`color-scheme: dark` was added so native date inputs/selects/scrollbars render dark by default.

**Hover direction rule applied consistently:** hovering a surface element now always lightens (`surface → surface-elevated`), never darkens — the previous light-theme code occasionally hovered *toward* `surface-muted`, which would have read as "dimming," the wrong affordance on a dark canvas. Fixed in `AppShell.tsx`, `Button.tsx`, and the daily-entry section tabs.

**Files changed this stage:**
- `app/globals.css` — full palette rewrite + complete `@theme` registration.
- `app/layout.tsx`, `app/dashboard/org/[orgId]/layout.tsx` — page canvas now `bg-background`, not a hardcoded light shade.
- `components/AppShell.tsx` — sidebar uses the new dedicated `sidebar` token (previously shared the `surface` token with cards); active nav item now uses `accent` for contrast; all hover states corrected to lighten.
- `components/Card.tsx`, `components/ui/Button.tsx`, `components/ui/Badge.tsx`, `components/ui/Toast.tsx`, `components/ExportButton.tsx`, `components/DateRangeFilter.tsx` — recolored onto tokens; `Badge`'s "success" tone now uses the new `success` token instead of borrowing `brand`.
- `app/page.tsx`, `app/login/page.tsx`, `app/dashboard/page.tsx`, `app/dashboard/org/[orgId]/page.tsx`, `app/dashboard/org/[orgId]/station/[stationId]/page.tsx`, `app/dashboard/org/[orgId]/station/[stationId]/daily-entry/page.tsx` — every raw Tailwind palette class swept onto the token system (mechanical, verified with a full-repo grep showing zero remaining raw-color classes in `app/` or `components/`).
- Login's and `DateRangeFilter`'s raw `<input>` elements (which don't go through the shared `Field`/`TextInput` component) now get an explicit `bg-surface-muted text-ink`, since unstyled native inputs would otherwise inherit no background at all.

**Not touched:** no business logic, no API calls, no permission checks, no component prop signatures, no route structure. This was a pure visual/token pass.

## 3. Verification performed (real, not claimed)

- `npx tsc --noEmit` → clean.
- `npm run lint` (eslint) → clean.
- `npm run build` → succeeds; inspected the actual compiled CSS output and confirmed by grep that every token used by the component library now generates a real class (the Section 1 bug is fixed, not just reworded).
- Rebuilt the frontend Docker image (`docker compose up -d --build frontend`) and ran the **full existing Playwright suite against the real backend** (not a mock): `dashboard.spec.ts` (6 tests) + `daily-entry.spec.ts` (1 full open→close→reconcile→approve workflow) — **7/7 passed**, confirming the visual change caused zero functional regression.

## 4. Stage 3 — Centralized English / Roman Urdu translations (implemented)

New files: `lib/i18n/translations.ts` (a flat key → `{en, ur}` dictionary, ~150 keys), `lib/i18n/context.tsx` (`LanguageProvider` + `useLanguage()`, wraps the whole app in `app/layout.tsx`). Roman Urdu is written in Latin characters throughout, per the brief's own instruction, and never used for database fields, enums, or financial calculations.

**Persistence:** client-only (`localStorage`, wrapped in `try/catch` so a blocked/private-mode browser just stays on English) — see `docs/ASSUMPTIONS.md` #37 for why, and what a real per-account default would need.

**Coverage:** the sidebar (`AppShell.tsx`, including a new language-toggle button), the login page, the entire Today's Overview dashboard, and the entire Daily Entry workspace (business-date picker, the 5 section tabs, a new step-progress indicator, and every field label/button/status string inside `ReadingsSection`, `SalesSection`, `ExpensesSection`, `CashSection`, `ReviewSection`) are translated both ways. The older Phase-6-era report tabs (`dashboard/org/[orgId]/page.tsx`, `station/[stationId]/page.tsx`) are **not** translated yet — deliberately scoped out to keep this pass bounded to the highest-traffic daily workflow the brief's own priority order calls out first; tracked as follow-up under Stage 6. Dynamic backend error messages (`detail` strings from API responses) also stay English-only — translating those would mean either duplicating every backend validation message on the frontend or adding an error-code contract to the API, neither of which this pass attempted.

**Real bug caught by this pass, not just a translation exercise:** four `useLanguage()` additions were going into files whose own loop variable was already named `t` (`tanks.map((t) => ...)` in `ReadingsSection`, `tenders.map((t) => ...)` in `SalesSection`) — the translate function would have been silently shadowed, and the code would have crashed at runtime (`t is not a function`) the moment that branch rendered. Caught by reading each file before editing, not by the type checker (TypeScript didn't catch it either, since both are legitimately callable in different scopes) — fixed by renaming the loop variables (`tank`, `tender`).

## 5. Stage 4 — Dashboard charts (implemented, `recharts@3.10.1`)

Verified `recharts` 3.10.1 declares a real React 19 peer-dependency range before installing it (not assumed). Six charts, each reading data a page had already fetched for its table/cards — no new fetches, no fabricated series:

| Chart | Where | Source |
|---|---|---|
| Fuel stock per tank | Today's Overview | `GET .../tanks` (already fetched) |
| Litres sold by grade (today) | Today's Overview | daily-fuel-sales report (already fetched) |
| Expense breakdown by category | Daily Entry → Expenses | the day's own expense list, grouped client-side |
| Litres sold over time | Station dashboard → Daily fuel sales tab | daily-fuel-sales report across the selected date range |
| Tank variance trend | Station dashboard → Tank variance tab | tank-variance report, framed neutrally (never "theft/fraud" language) |
| Expected vs. collected per shift | Station dashboard → Reconciliation tab | shift-reconciliation report |

**Known, documented gap, not an oversight:** the brief also asks for "revenue breakdown by payment method." No report endpoint aggregates `ShiftTender` by payment method across a date range today (only per-shift tender lists exist), and building that aggregation was out of scope for a chart added opportunistically while wiring the others — flagged here rather than built as a rushed client-side N+1 fetch across every shift in range.

## 6. Stage 5 — Daily Operations guided workflow (implemented)

`daily-entry/page.tsx` gained a `DailyEntryProgress` component: a thin 5-segment progress bar plus "Step N of 5 · <section>" text above the existing tab row, and a one-line contextual help sentence (translated, from `dailyEntry.help.*` keys) under the tabs, matching what each section actually does — e.g. for Cash Closing: *"Check here whether the money that should have come in actually matched what was collected"* / *"Is screen par check karein ke kitna paisa aana chahiye tha aur asal mein kitna mila."* The progress bar reflects **position in the flow**, not a correctness claim — the existing Review & Submit checklist (`ReviewSection.tsx`) remains the one place that asserts a section is actually *done*, since sales/expenses are open-ended (more can always be added before closing) and have no real "complete" signal to display honestly.

## 7. Stage 6 — Forms, tables, charts, reports (partially implemented)

Covered as part of Stages 3/4 above (every Daily Entry form is now translated; 6 charts added to report tabs). Not done: a dedicated reports hub, nozzle-wise/bank-reconciliation report types, and translating the older Phase-6 report tabs — see Stage 3's coverage note.

## 8. Stage 7 — Users & Settings (implemented, new page + one new backend endpoint)

**Real backend gap found while building this, fixed minimally:** `GET /organizations/{id}/users` never returned a user's role assignments, and there was no endpoint to list them at all (only `POST`/`DELETE` existed for creating/revoking one). Added `GET /organizations/{organization_id}/users/{user_id}/roles` (`backend/app/api/users.py`) — read-only, reuses the existing `USER_READ` permission and the existing `_get_org_user_or_404` scoping helper, no new business logic. Two new tests (`backend/tests/test_rbac.py::test_owner_can_list_a_users_role_assignments`, `::test_cannot_list_roles_for_a_user_not_in_this_organization`) — both passing, and the full 182-test backend suite still passes.

New page: `app/dashboard/org/[orgId]/settings/page.tsx`, linked from the sidebar (now actually permission-gated on `user:read`, which it previously was not — a real, if small, access-control gap: every other nav item already checked a permission before rendering its link, this one didn't). Sections:
- **Your account** — language switch (English/Roman Urdu, same mechanism as the sidebar toggle), change password (`PATCH /auth/password`), active session count + "sign out everywhere" (`GET/POST /auth/sessions`, `/auth/logout-all`) — all pre-existing backend endpoints from Phase A, never previously exposed in the UI.
- **Organization users** (gated `user:read`) — table of users, click one to see their role assignments.
- **Add a user** (gated `user:create`) and **Assign/revoke a role** (gated `user:assign_role`) — both call the existing create-user and role-assignment endpoints; the privilege-escalation guard (`actor_can_grant_scope`) that already existed server-side is untouched and still the real enforcement boundary — the frontend gate is a UX convenience, not the security control.

## 9. Stage 8 — Animations, responsiveness, accessibility (implemented, intentionally restrained)

Used lightweight CSS keyframes (`app/globals.css`: `cynvexa-fade-slide-up`, `cynvexa-slide-in-left`), not Framer Motion — avoids a new runtime dependency for an effect this small, and the existing `prefers-reduced-motion` media query (added in the Stage 2 pass) already neutralizes both via `!important`, verified by cascade precedence, not assumed. Applied to: toast entrances, the mobile sidebar drawer, and the Today's Overview summary-card grid. Explicitly did **not** animate any rendered financial figure itself (shortage/excess, revenue, cash) — the brief's own caution against making an amount's value momentarily unclear. No new responsive-layout work beyond what already existed; no dedicated WCAG audit performed (same honest gap already on record in `docs/REMAINING_RISKS.md`).

## 10. Stage 9 — Full regression (run for real, results below)

- Backend: `pytest tests/ -q` → **182 passed** (15m03s), including the 2 new role-listing tests.
- Frontend: `npx tsc --noEmit` → clean. `npm run lint` → clean. `npm run build` → succeeds, `/dashboard/org/[orgId]/settings` is a new compiled route.
- Rebuilt the frontend (and backend, since its source changed too) Docker images and ran the full Playwright suite twice: the first run caught one real regression (below), the second run was **7/7 passed**.

**Real regression caught and fixed by this run, not by inspection:** `daily-entry.spec.ts` failed on `getByLabel("Actual cash counted")` — the Stage 3 translation for that field's label was written as "Actual physical cash counted" (a paraphrase, not the original string), silently breaking the exact-text Playwright selector. Fixed by making the English translation value match the pre-existing copy exactly (`lib/i18n/translations.ts`'s `cash.actualPhysicalCash` key) — a reminder that introducing i18n keys for existing, already-tested English copy must preserve the original wording exactly when English is selected, not just convey the same meaning.

## 11. Implementation order — final status

| Stage | Scope | Status |
|---|---|---|
| 1 | Audit + design system definition | **Done** |
| 2 | Black/blue theme + reusable components | **Done** |
| 3 | Centralized English/Roman Urdu translations | **Done** (core workflow + nav + login; older report tabs not translated) |
| 4 | Main dashboard redesign with real API data + charts | **Done** (6 charts; payment-method breakdown chart deferred — no aggregation endpoint) |
| 5 | Daily Operations guided-workflow redesign | **Done** (progress indicator + contextual help; still no draft/autosave) |
| 6 | All forms, tables, filters, reports | **Partial** (see Stage 3/4 scope notes) |
| 7 | Users & Settings + onboarding | **Done** (Users & Settings; no first-time onboarding tour) |
| 8 | Animations, responsive behavior, accessibility | **Done**, restrained (no new WCAG audit) |
| 9 | Full Playwright regression + production verification | **Done** — 182 backend + 7 e2e tests passing |

See `docs/REMAINING_RISKS.md`'s "UI/UX upgrade pass" section for the consolidated, prioritized list of what's still open.
