# CYNVEXA — Complete Usage Guide (A to Z)

**Date:** 2026-11-15
**Who this is for:** the owner setting this up for the first time, and every staff member who will use it day to day. Written against what the live app actually does today — nothing described here is planned or assumed.

**Live app:** https://cynvexa-frontend-laraib.onrender.com
**Demo account to try it right now:** `demo.owner@cynvexa.app` / `CynvexaDemo2026!` (Owner role — full access). Don't put real business data under this account; create your own organization once you're ready (Section 2).

> Free-tier note: the first page load after a few minutes of inactivity can take 30–60 seconds while the free server wakes up. This is normal — see `docs/PHASE_7_FREE_HOSTING_LIMITATIONS.md`.

---

## 1. Signing in

Open the login page, enter your email and password, tap **Sign in**. Forgot your password? There's no self-service "forgot password" yet — ask whoever has the Owner or Station Manager role to set a new one for you from **Users & Settings**.

**Language.** Every page has an **EN / UR** toggle (top-right of the login card, and in the sidebar once inside). It switches the whole screen between English and Roman Urdu. This is per-device — it doesn't change anything for anyone else.

---

## 2. Setting up your own organization (do this once)

If you're not using the demo account, go to **/register** from the login page and fill in:

- **Company name** — your business name
- **Station name** — your first station (you can rename or add more later)
- **Your full name, email, password** — this becomes your Owner account
- **Plan** — defaults to "Starter" if you don't pick one (see Section 15 for what the plans mean)

One submit creates your organization, its first station, you as Owner, and a 14-day trial subscription — and signs you straight in. There is no multi-step setup wizard after this; the steps below (Section 3) are what you do manually instead.

---

## 3. First-time station setup

Before anyone can record a day's work, a few things need to exist. Go to **Station Config** in the sidebar (Owner or Station Manager only):

1. **Station Profile** — address, contact info, receipt settings.
2. **Fuel Grades** — add each fuel type you sell (e.g. Petrol, Diesel, Hi-Octane) with its code and name.
3. **Tanks** — add each underground tank: which fuel grade it holds, its capacity, and safe-fill limit.
4. **Dispensers** — add each physical pump/dispenser unit.
5. **Nozzles** — add each nozzle, linking it to one dispenser and the one tank it draws from.
6. **Shift Templates** — define your station's shift timings (e.g. Morning 6 AM–2 PM).
7. **Tolerances & Thresholds** — set the acceptable variance percentage for fuel receipts and the acceptable cash discrepancy amount before extra authorization is required.

Then at the **organization** level, go to **Users & Settings** (Owner only):

8. **Payment Methods** — add how customers pay (Cash, Card, Digital/Easypaisa/JazzCash, Credit) — these show up as options when staff record sales.
9. **Expense Categories** — add categories for station expenses (Electricity, Repairs, Staff meals, etc.).

**Suppliers — one honest gap:** there is currently no page to *add* a supplier from the UI. Suppliers can be read and picked from a dropdown on the Purchases page, but creating a new one today requires a direct API call or a database insert by whoever manages the deployment. This is a real, acknowledged limitation, not an oversight you missed — flag it if it blocks you and it can be prioritized.

---

## 4. Adding your team and assigning roles

Still in **Users & Settings** → **Org Users**:

1. **Add a user** — name, email, a temporary password. Tell them to sign in and you can change their password later if needed.
2. **Assign a role** — pick the person, pick a role, and optionally pick one specific station (otherwise the role applies across every station in your organization).

### The 7 roles and what each one can actually do

| Role | Can do | Cannot do |
|---|---|---|
| **Owner** | Everything — every permission in the system. | — |
| **Station Manager** | Manage station config, approve fuel deliveries/shifts/expenses/reading corrections, record reconciliation, manage inventory, view reports, manage attendance/payroll. | Manage billing/subscriptions, platform admin. |
| **Shift Supervisor** | Open/close/approve shifts, record and approve reading corrections, record reconciliation, manage fuel deliveries, record inventory movements. | Station config changes, approvals outside shift operations, reports. |
| **Cashier / Operator** | Open/close a shift, record readings (read-only view of tanks/nozzles to do so), record inventory movements. | Approve anything, edit station config, view reports/audit history. |
| **Accountant** | Approve reconciliation and reading corrections, manage expenses/supplier ledger/credit collections, view reports/audit/subscription info, manage attendance & payroll. | Station config, shift operations, platform admin. |
| **Storekeeper / Technician** | Manage tanks/dispensers/nozzles, record fuel deliveries, manage inventory items and movements. | Shift operations, approvals, financial records. |
| **Auditor / Viewer** | Read-only access to almost everything — stations, deliveries, shifts, credit, expenses, inventory, reports, audit history. | Create, edit, approve, or delete anything. |

A role only grants what's listed — e.g. Cashier can see tanks/nozzles to record a reading, but cannot create or edit one. If someone tries an action their role doesn't cover, the app shows "Access restricted" — this isn't a bug, it's the permission system working correctly.

---

## 5. Your daily routine — Daily Entry (Aaj ka Kaam)

*Roles: Cashier/Operator, Station Manager, Shift Supervisor*

Open **Daily Entry**. If today hasn't been started, tap **Start today's entry** — yesterday's closing stock carries forward automatically.

1. **Pump Readings** — for each tank, record the opening/closing dip; for each nozzle, record the opening/closing meter reading.
2. **Sales & Collections** — log every payment received (cash, card, digital, credit) with amount and method, as many times through the day as needed.
3. **Expenses** — log anything paid out of station cash today (category, description, amount).
4. **Cash Closing** — physically count the cash on hand and enter it; the app shows the difference against what sales/expenses say should be there.
5. **Review & Submit** — a checklist confirms everything required is done, then **Approve today's entry** finalizes the day. Once approved, it feeds every report and **cannot be un-approved** — only corrected (Section 8).

---

## 6. Reading the dashboard — Today's Overview

*Roles: Owner, Station Manager*

- **Sales value** = revenue, not profit (no cost-of-fuel/wages deduction yet).
- **Expected vs. actual cash** — always shown separately; the system never silently adjusts one to match the other.
- **Cash shortage/excess** — a flagged difference, not an automatic accusation.
- **Fuel stock remaining** — calculated from deliveries in minus sales out (book stock), not a live tank sensor.

---

## 7. Fuel Stock & Reconciliation (historical reports)

*Roles: Station Manager, Accountant*

- **Fuel Stock** (its own nav item) — book stock vs. physical reading per approved day, variance %, tolerance flag, trend chart.
- **Reconciliation** — the cash equivalent: expected revenue vs. total collected per shift, over a date range, with a comparison chart. (Today's live version is on the Dashboard; this is the historical record.)

A variance here is a number to investigate, never an automatic label of theft or error.

---

## 8. Reading corrections (the 24-hour rule)

If a mistake is found in an already-approved reading, it's corrected through a **reading correction request**, not by editing the original record directly (approved data never changes in place — it's an audit requirement). Go to **Reading Corrections**, submit the correction with a reason, and whoever has approval authority (Station Manager, Shift Supervisor, or Accountant) reviews it.

**Hard rule, never bypassed by any role including Owner:** a correction can only be requested within **24 hours** of the original reading. After 24 hours, it locks permanently — there is no override, by design, to protect the integrity of closed financial records.

---

## 9. Fuel deliveries — Purchases

*Role: Station Manager, Shift Supervisor, Storekeeper*

When fuel arrives: open **Purchases**, record the delivery against a supplier (see Section 3's note on adding suppliers) with the invoiced quantity, then record the tank reading after it's unloaded. A manager/supervisor approves it afterward — approving locks the record, so check the numbers first.

---

## 10. Credit customers

*Roles: Accountant, Owner, Station Manager*

**Credit Sales** shows every credit customer's running balance — credit sales minus repayments. When a customer pays something back, record it here as a collection against their balance.

---

## 11. Attendance & Payroll

*Roles: Station Manager, Accountant*

**Attendance** — mark staff present/absent per shift; this feeds payroll calculations.

**Payroll — one honest gap:** the payroll engine (rules, salary generation, listing, finalization) is fully built on the backend, but there is **no frontend page for it yet** — it can't be used through the app's UI today. This is a known, documented gap (see `docs/PHASE_7_INITIAL_AUDIT.md`), not something broken; it's next on the feature list.

---

## 12. Approvals & Alerts

*Roles: Owner, Station Manager, Accountant*

One screen listing everything waiting on someone: deliveries, shifts, cash movements, discrepancies needing authorization, expenses, supplier payments, low inventory. Tap through to act on each from its own section.

---

## 13. Reports

*Roles: Owner, Accountant*

**Daily fuel sales and litres** — litres sold and expected revenue by fuel grade, per day, over any date range, with a trend chart. Everything comes from approved shifts' real records — nothing estimated. **Export CSV** downloads the same data for Excel or an accountant.

---

## 14. Audit history

*Roles: Owner, Accountant*

A permanent, uneditable log of every approval, rejection, reversal, and change — who, when, what. Scoped to your own station(s) unless your role covers the whole organization.

---

## 15. Billing & subscription

*Role: Owner*

Under **Users & Settings → Billing & subscription**: see your current plan (Starter / Business / Enterprise) and its limits (max stations, max users). **No payment gateway is wired in** — every real payment is recorded and verified manually by a platform admin, by design. Plan limits are also not yet technically enforced (documented in `docs/SAAS_GAP_ANALYSIS.md`) — this is intentional scoping, not a bug.

---

## 16. Platform Admin (superuser only — not a normal role)

A separate, cross-organization screen at **/dashboard/platform**, visible only to a platform superuser account (not any of the 7 organization roles above). From here: manage the global list of plans, and view/manage every organization's subscription across the whole platform. Ordinary Owners never see this page — it's for whoever operates CYNVEXA itself across multiple client organizations.

---

## 17. What's genuinely not available yet (so you don't go looking for it)

- Self-service "forgot password" — a manager must reset it for you.
- A guided onboarding wizard after registration — Section 3's steps are manual.
- A UI to add new suppliers — API/backend-only for now.
- A payroll frontend — backend-complete, no pages yet.
- Any payment gateway integration for subscription billing.
- Enforcement of plan limits (max stations/users) — tracked but not blocking yet.

None of these are silently broken — they're scoped-out, tracked gaps, listed here so you know exactly where the line is today.

---

## 18. If something looks wrong

- **"I can't close today's readings"** — every tank needs opening + closing dip, every nozzle needs opening + closing meter; the app names exactly what's missing.
- **"My login stopped working"** — session expired, or your password changed elsewhere; sign in again, or ask your Owner/Station Manager to check your account.
- **"A dashboard number looks wrong"** — nothing on the dashboard is typed by hand; it's all computed from readings/sales/expenses already recorded. Check the entry, not the dashboard.
- **"The page is stuck loading for 30-60 seconds"** — normal free-tier cold start after inactivity; wait, don't refresh repeatedly.

---

## 19. Where to go next

- Day-to-day staff workflow in more plain language, with a glossary: `docs/STAFF_GUIDE.md`
- How to deploy, redeploy, or troubleshoot the live infrastructure itself: `docs/PRODUCTION_RUNBOOK.md`
- Free-tier limitations in full: `docs/PHASE_7_FREE_HOSTING_LIMITATIONS.md`
- What changes once a real client is confirmed and paid hosting is approved: `docs/PHASE_7_PAID_PRODUCTION_PLAN.md`
