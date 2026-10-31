# CYNVEXA Staff Guide

A plain-language guide to using the CYNVEXA app day to day — written for everyone at the station, not just managers: owner, station manager, cashier/operator, and accountant. This mirrors the published guide (ask whoever ran the last upgrade pass for the shareable link) and is kept here so it stays versioned with the app itself.

## 1. Getting started

**Signing in.** Open the app in your browser and enter the email and password your manager gave you. If you forget your password, ask your manager or accountant to reset it from Users & Settings — do not share your password with anyone.

**English or Roman Urdu.** In the sidebar, near the bottom, there is a **Language** button showing **EN** or **UR**. Tap it to switch the whole screen between English and Roman Urdu (Urdu written in English letters, e.g. *"Aaj ka Kaam"* for "Daily Entry"). This only changes your own screen on your own device — switching it does not affect anyone else, and it never clears anything you were typing.

**The sidebar.** You only see the sections you are allowed to use — a cashier will not see Users & Settings, for example. This is not a mistake: it matches exactly what your account is permitted to do.

## 2. Your daily routine — *Daily Entry (Aaj ka Kaam)*

*Roles: Cashier/Operator, Station Manager*

Open **Daily Entry** in the sidebar. If today's work hasn't been started yet, you'll see a **"Start today's entry"** button. Yesterday's closing stock carries forward on its own — you never re-type it.

1. **Pump Readings (Meter Reading).** For each tank, write down the dip reading (the physical measurement) at the start and end of the day. For each nozzle, write down the meter number at the start and end of the day. The opening number is usually already filled in from yesterday's closing number.
   *Har tank ki shuru aur aakhri dip, aur har nozzle ka meter number darj karein.*

2. **Sales & Collections.** Every time money comes in — cash, card, digital/bank, or a credit sale to a known customer — add it here with the amount and method. You can add as many entries as you need through the day; nothing is locked until step 5.
   *Jab bhi paisa aaye — cash, card, digital ya udhar — yahan darj karein.*

3. **Expenses.** Anything paid out of the station's own cash today — electricity, a small repair, tea for staff — gets its own entry here: category, a short description, and the amount.
   *Aaj station ke cash se jo kharcha hua, usay yahan darj karein.*

4. **Cash Closing.** At the end of the day, physically count the cash in hand and type that number in. The app compares it to what the sales and expenses say should be there, and shows you the difference. See §4 for what to do if the numbers don't match.
   *Din ke aakhir mein asal cash ginein aur darj karein.*

5. **Review & Submit.** A checklist shows everything that must be done before today can be finalized. Once every item is checked, tap **Approve today's entry**. After that, today's figures are final and feed into every report — so only approve once you're sure.
   *Sab theek hone par "Aaj ka Kaam Manzoor Karein" dabayein.*

> **One entry per day.** Daily Entry can only be started for *today*. If a past day was missed entirely, that is a correction, not a new entry — ask a manager; it isn't something a cashier can create after the fact.

## 3. Reading the dashboard — *Today's Overview*

*Roles: Owner, Station Manager*

- **Sales value** is **revenue** — the money fuel sold for. It is *not profit*. Profit would also need to subtract what the fuel cost to buy, running costs, and wages — this dashboard does not calculate that yet.
- **Expected vs. actual cash** — expected cash is calculated purely from sales and cash movements; actual cash is what was physically counted. These are always shown separately — the system never adjusts one to match the other.
- **Cash shortage / excess** is the honest difference between the two above. A difference is *not* automatically treated as theft or a mistake by anyone — it's simply flagged so a manager or accountant can look into it.
- **Fuel stock remaining** is how much fuel the books say should be in each tank right now, based on deliveries in and sales out — not a live sensor reading.

## 4. Cash & discrepancies

*Roles: Accountant, Station Manager*

- **Small differences** — every station has a small allowed tolerance. A difference inside that range is recorded but doesn't block anything.
- **Larger differences need authorization** — if the gap is bigger than the station's tolerance, the Cash Closing screen will ask for a written explanation, and the entry cannot be fully approved until an accountant or the owner authorizes it. This is not an accusation — it's the control that catches real counting errors or missed entries before the day is closed for good.

## 5. Fuel deliveries — *Purchases*

*Role: Station Manager*

When fuel arrives, open **Purchases**, record the delivery with the supplier's own document quantity, then record the tank reading after it's unloaded. A manager (or whoever holds that permission) approves the delivery afterward — approving locks the record, so check the numbers first.

## 6. Fuel stock & reconciliation

*Roles: Station Manager, Accountant*

- **Fuel Stock** shows, for a date range, each approved day's **book stock** (what the records say should be in each tank) next to the **physical reading** taken that day, with the variance as a percentage and whether it's within the station's allowed tolerance, plus a trend chart.
- **Reconciliation** is the same idea for cash: expected revenue and total collected, side by side for every shift in the range, with a chart comparing the two. This is the historical view — the live version for *today* is on the Dashboard.

> A variance is not an accusation. A gap between book and physical stock, or between expected and collected cash, is shown plainly as a number to look into — the system never labels it as theft, fraud, or anyone's mistake.

## 7. Reports

*Roles: Owner, Accountant*

**Daily fuel sales and litres** — for any date range, see litres sold and expected revenue broken down by fuel grade, per day, with a chart of litres sold over time. Every figure comes from approved shifts' own stock and revenue records — nothing is estimated. Use **Export CSV** to download the same data for Excel or to send to an accountant.

## 8. Approvals & alerts

*Roles: Owner, Station Manager, Accountant*

**Pending & exceptions** is a single screen listing real counts: deliveries awaiting approval, shifts awaiting approval, cash movements awaiting approval, cash/revenue discrepancies needing authorization, expenses awaiting approval, supplier payments awaiting approval, and inventory items running low. Tap through to actually deal with each one from its own section.

## 9. Credit sales

*Roles: Accountant, Owner*

**Credit customer balances** shows every credit customer's current balance — their credit sales so far, minus whatever they've already paid back. When a customer pays something back, record it here as a collection against their balance.

## 10. Audit history

*Roles: Owner, Accountant*

Every approval, rejection, reversal and change anywhere in the system writes a permanent entry here — who did it, when, and what changed. You can only see events for your own station(s) unless your role covers the whole organization. Nothing here can be edited or deleted.

## 11. Users & settings

*Roles: Owner, Station Manager*

- **Adding a new staff member** — use "Add a user" with their name, email and a temporary password. Tell them to change it after their first sign-in.
- **Giving someone a role** — select the person from the list, then "Assign a role." Choose a role (e.g. Cashier/Operator) and, if it should only apply at one station, pick that station — otherwise leave it as organization-wide.
- **Changing your password** — enter your current password and a new one under "Your account." This signs you out of every other device automatically, as a safety measure.
- **Your language choice** — the same English/Roman Urdu switch from the sidebar is also here.

## 12. If something looks wrong

- **"I can't close today's readings"** — every tank needs both an opening and closing dip, and every nozzle needs both an opening and closing meter reading. The app will tell you exactly which one is missing.
- **"My login stopped working"** — your session may have expired, or your password was changed on another device. Sign in again; if that fails, ask whoever manages Users & Settings to check your account is still active.
- **"A number on the dashboard looks wrong"** — nothing on the dashboard is typed in by hand; every figure comes directly from the readings, sales and expenses already recorded. If a number looks wrong, the most likely cause is an entry earlier in the day, not the dashboard itself.

## Glossary

| English | Roman Urdu |
|---|---|
| Daily Entry | Aaj ka Kaam |
| Opening stock | Shuru ka Stock |
| Closing stock | Aakhri Stock |
| Fuel received | Mila Hua Petrol |
| Fuel sold | Bika Hua Petrol |
| Cash shortage | Cash Kam Nikla |
| Pending approval | Manzoori Baqi Hai |
| Save changes | Tabdeeli Save Karein |
