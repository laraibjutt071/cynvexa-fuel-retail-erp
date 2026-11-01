# SaaS Transformation — Audit & Gap Analysis (2026-11-01)

Per the master prompt's own Phase 1/Phase 2 instructions: a grounded audit of what already exists, followed by a prioritized roadmap, before further implementation. This is not a restart — everything below Phase A-7 and the UI/UX upgrade pass (see `docs/IMPLEMENTATION_PLAN.md`, `docs/UX_UPGRADE_PLAN.md`) stays as-is.

## 1. Audit — what's already real (verified by reading the code, not assumed)

**Multi-tenant isolation is already solid.** Every mutating and most read endpoints resolve `organization_id`/`station_id` from the URL path only (never the body) through one shared `require_permission` dependency (`app/api/deps.py`). `backend/tests/test_cross_tenant_isolation.py` already exercises this. This is the hardest part of a multi-tenant SaaS to get right, and it was already built correctly from Phase A onward — nothing to redo here.

**A "platform admin" concept already exists, partially.** `User.is_superuser` bypasses every permission check; `POST /organizations` and `GET /organizations` (returns *every* org for a superuser, only the caller's own orgs otherwise) already work; `Organization.is_active` already exists as a suspend/activate flag, settable via the existing `PATCH /organizations/{id}`. What was missing: any UI for a platform admin to actually use this, and the subscription/billing concept entirely.

**What was completely absent before this pass:** Plan/Subscription/Payment data model (zero rows existed for any of it), a Platform Admin dashboard, self-service company registration (orgs are created by a superuser only, not a public signup flow), a guided onboarding wizard, light/dark mode toggle (the app is dark-only since the UI/UX pass), actual Urdu script + RTL (the app has Roman Urdu/LTR, not Arabic-script Urdu), PDF/Excel export (CSV only), notification infrastructure (email/SMS/WhatsApp), and any landing/pricing/marketing pages (`/` just redirects to `/login` or `/dashboard`).

## 2. Gap analysis — prioritized

| Area | Status | Priority |
|---|---|---|
| Tenant isolation | Done (pre-existing) | — |
| Platform admin: suspend/activate orgs | Backend done (pre-existing), no UI before this pass | High — **done this pass** |
| Subscription/Plan/Payment data model | **Done this pass** | High |
| Platform admin UI (plans, subscriptions, manual payments) | **Done this pass** (minimal) | High |
| Org-facing billing view | **Done this pass** (read-only) | High |
| Self-service company registration / onboarding wizard | Not built | Medium |
| Plan usage-limit enforcement (max_stations/max_users actually blocking) | Not built | Medium |
| Payment gateway integration (JazzCash/Easypaisa/Stripe) | Not built — architecture note only | Medium |
| Subscription expiry access restriction | Not built, deliberately | Medium |
| Light/dark mode toggle | Not built (dark-only) | Low-Medium |
| Real Urdu script + RTL | Not built (Roman Urdu/LTR only) | Low-Medium |
| PDF/Excel export | Not built (CSV only) | Low |
| Notifications (email/SMS/WhatsApp) | Not built | Low |
| Landing/pricing/marketing pages | Not built | Low |

## 3. What was implemented this pass (Phase 3 — core SaaS foundation)

**Backend** (`backend/app/models/plan.py`, `subscription.py`, `subscription_payment.py`, `app/api/platform.py`, `app/api/subscriptions.py`):
- `Plan` — platform-wide catalog (code, name, monthly/annual price, max_stations/max_users as nullable=unlimited, is_active). All fields configurable via `PATCH /platform/plans/{id}` — nothing hardcoded, per the brief's own instruction that these are "initial product packages, not fixed prices."
- `Subscription` — one row per organization (`UniqueConstraint`), status (`trial`/`active`/`past_due`/`canceled`/`expired`), billing cycle, trial/period dates. Managed only by a platform administrator (`require_superuser`, the same dependency `POST /organizations` already used — not a new pattern).
- `SubscriptionPayment` — a manually-recorded, manually-verified payment. No payment gateway exists yet, so every row is entered by a platform admin personally attesting it was received — there is deliberately no separate "unverified/pending" state, to avoid pretending a review workflow exists before one is actually built. Every create/update writes the existing `AuditLog` in the same transaction, same pattern as every other mutation in this codebase.
- New permission `subscription:read` — org-scoped, read-only (Owner and Accountant hold it by default). An organization can see its own plan/status/payment history; it can never change any of it itself.
- Real tests (`backend/tests/test_subscriptions.py`, 6 new, all passing): non-superuser blocked from managing plans, duplicate plan codes rejected, one-subscription-per-org enforced, cross-tenant isolation on the billing view (the exact same discipline as every other resource), and the audit trail on a recorded payment.
- Migration `56260bf7064a` applied to both the local dev database and the live production Neon database.

**Frontend:**
- `/dashboard/platform` — platform-admin-only (redirects away otherwise), outside the org-scoped shell since it has no org in its own URL. Lists/creates plans; lists every organization with its subscription status; can start a trial, change status, and record a verified payment inline.
- A "Platform Admin" sidebar link, visible only to superusers.
- A **Billing & subscription** card on the existing Users & Settings page — plan, status, billing cycle, period end, and payment history, read-only, gated by the new `subscription:read` permission.

**Verified, not claimed:** real migration run against both databases, 6 new backend tests passing plus the full existing suite re-run, frontend typecheck/lint/build clean, full Playwright e2e suite re-run (7/7) after rebuilding the local Docker stack.

## 4. Deliberately not built this pass — triaged, not missed

- **Plan limit enforcement.** `max_stations`/`max_users` exist on `Plan` but nothing checks them against `Station`/`UserStationRole` counts yet — an org on the Starter plan can create unlimited stations today. Real, scoped-out work: the check belongs in `stations.py`'s create endpoint and `users.py`'s role-assignment endpoint, reading the org's current subscription's plan limits.
- **Subscription-expiry access restriction.** An `expired`/`canceled` subscription does not currently block anything — the master prompt explicitly asks for "configurable access restrictions," not a hard cutoff, and building that gate under time pressure without real tests for every affected endpoint risked locking out working accounts (including the live demo). Scoped out deliberately, not forgotten.
- **Payment gateway integration.** The brief asks for "integration-ready architecture," not a live JazzCash/Easypaisa/Stripe integration — `SubscriptionPayment.method` is free text precisely so a real gateway can be wired in later without a schema change; no gateway credentials exist to integrate with yet.
- **Self-service onboarding wizard.** Organizations are still created by a platform admin (via `/dashboard/platform` or the API) — no public "register your company" flow exists. This is a real, sizable UI flow (the brief's own 10-step onboarding list) that deserves its own pass rather than a rushed version.
- **Light/dark mode, real Urdu RTL, PDF/Excel export, notifications, marketing pages** — all real, named gaps from section 2, none started this pass; each is independently sizable.
