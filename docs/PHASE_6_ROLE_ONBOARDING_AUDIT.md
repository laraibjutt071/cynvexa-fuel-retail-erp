# CYNVEXA — Phase 6 Role, Permission & Onboarding Audit (Step 1 + Step 3)

**Date:** 2026-11-15
**Scope:** Read-only audit. All Phase 1–5 reports were re-read before writing this. No application code was changed while producing this document.

---

## 1. The Cashier/Operator finding, re-confirmed before touching anything

Phase 5 found, by actually testing as a real Cashier account, that `tank:read` and `nozzle:read` are missing from the seeded `Cashier / Operator` role (`app/core/permission_codes.py::SEED_ROLES`), while `shift:open`/`shift:close` (which gate *recording* a reading) are present. Re-confirmed here by reading the current file before any edit:

```
"Cashier / Operator": [
    STATION_READ, SHIFT_READ, SHIFT_OPEN, SHIFT_CLOSE, PAYMENT_METHOD_READ,
    SHIFT_RECONCILE_RECORD, INVENTORY_ITEM_READ, INVENTORY_MOVEMENT_READ,
    INVENTORY_MOVEMENT_RECORD,
]
```

`TANK_READ` and `NOZZLE_READ` are genuinely absent — not a misreading. `app/api/tanks.py`'s list/detail endpoints and `app/api/nozzle_overview.py`'s list endpoint both `require_permission(TANK_READ)` / `require_permission(NOZZLE_READ)` respectively, confirmed again this phase. The repository has **no separate "Operator" role** — only one combined `"Cashier / Operator"` role exists in `SEED_ROLES`, so the owner-approved fix applies to that single role, not two.

## 2. Role/permission architecture (how a fix here actually reaches a real client)

- `Permission` and `Role` are **global catalog tables**, not per-organization — confirmed by re-reading `app/seed.py` and `app/models/role.py`. An organization doesn't get its own copy of "Cashier / Operator"; every organization's users reference the same `Role` row via `UserStationRole`.
- `app/seed.py::seed_permissions_and_roles()` is explicitly idempotent and **additive only**: for each seed role it adds any permission code listed in `SEED_ROLES` that the role's current permission set doesn't already have (`if code not in current_codes: role.permissions.append(...)`). It **never removes** a permission a role already has.
- This means: adding `TANK_READ`/`NOZZLE_READ` to `SEED_ROLES["Cashier / Operator"]` in code, then re-running `python -m app.seed permissions-roles` against a real database, safely **adds** the two permissions to the existing, already-deployed `Cashier / Operator` Role row — every client organization's existing Cashier/Operator users gain the new access immediately, with zero risk of silently removing anything an owner may have customized on that role (the seed script physically cannot remove a permission, only add a missing one).
- **No schema migration is needed.** `tank:read` and `nozzle:read` already exist as `Permission` rows today (Storekeeper/Technician, Auditor/Viewer, Station Manager, Shift Supervisor, and Owner already reference them) — this is a data change (one new `role_permissions` association row), not a new table or column. Step 8's migration-safety requirements are addressed by re-running the existing, already-idempotent seed command, not by writing a new Alembic revision.
- **Station/organization scoping is untouched by this change.** `tank:read`/`nozzle:read` are checked by `require_permission()`, which (per Phase 2/3's own verified findings) resolves `organization_id`/`station_id` from the URL path only, exactly the same way for every permission code — granting a Cashier this permission does not and cannot widen which station's data they can see; it only lets them see *their own* authorized station's tanks/nozzles, same as every other permission this role already holds.

## 3. Role-based workflow matrix (Step 3) — from the real permission catalog, not assumed

| Capability | Cashier/Operator | Shift Supervisor | Station Manager | Accountant | Storekeeper/Technician | Auditor/Viewer | Owner | Platform Admin |
|---|---|---|---|---|---|---|---|---|
| View station profile | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | n/a (superuser bypass) |
| Edit station profile | — | — | ✅ | — | — | — | ✅ | — |
| View tanks/nozzles | ❌ **(the bug)** → ✅ after fix | ✅ | ✅ | — | ✅ | ✅ | ✅ | bypass |
| Create/edit tanks/nozzles | — | — | — | — | ✅ | — | ✅ | bypass |
| Open/close a shift | ✅ | ✅ | ✅ | — | — | — | ✅ | bypass |
| Approve a shift (final Daily Entry approval) | — | ✅ | ✅ | — | — | — | ✅ | bypass |
| Record a reading correction request | — | ✅ | ✅ | — | — | — | ✅ | bypass |
| Approve a reading correction | — | ✅ | ✅ | ✅ | — | — | ✅ | bypass |
| Record a tender/collection | ✅ | ✅ | ✅ | ✅ | — | — | ✅ | bypass |
| Reverse a tender | — | ✅ | ✅ | ✅ | — | — | ✅ | bypass |
| Record an expense | — | — | — | ✅ | — | — | ✅ | bypass |
| Approve/reject an expense | — | — | ✅ | ✅ | — | — | ✅ | bypass |
| Record cash movements/closing | ✅ | ✅ | ✅ | ✅ | — | — | ✅ | bypass |
| Approve a decreasing cash movement / authorize a discrepancy | — | — | — | ✅ | — | — | ✅ | bypass |
| Receive a tanker delivery | — | — | ✅ | — | ✅ | — | ✅ | bypass |
| Approve a tanker delivery | — | ✅ | ✅ | — | — | — | ✅ | bypass |
| Manage fuel grades | — | — | — | — | — | — | ✅ | bypass |
| Manage dispensers/nozzles (create/edit) | — | — | — | — | ✅ | — | ✅ | bypass |
| Manage payment methods | — | — | — | — | — | — | ✅ | bypass |
| View attendance | — | — | ✅ | ✅ | — | — | ✅ | bypass |
| Record attendance | — | — | ✅ | — | — | — | ✅ | bypass |
| Manage payroll rules | — | — | — | ✅ | — | — | ✅ | bypass |
| View audit log | — | — | ✅ | ✅ | — | ✅ | ✅ | bypass |
| Manage users/roles | — | — | — | — | — | — | ✅ | bypass |
| Manage subscriptions/plans (platform-wide) | — | — | — | — | — | — | — | ✅ only |
| Suspend/activate any organization | — | — | — | — | — | — | — | ✅ only |

**Frontend/backend agreement, confirmed by code (not assumed):** every row above that the frontend gates (Phase 3/5 work) uses the literal permission code shown — e.g. the "Approve a shift" row is `shift:approve` in both `app/api/shifts.py`'s endpoint dependency and `ReviewSection.tsx`'s `can("shift:approve")` check. Where the frontend does **not** yet gate a capability (e.g. attendance recording's UI gating was fixed in Phase 3; cash-movement approval and discrepancy authorization gating were fixed in Phase 5), the backend already enforced it correctly throughout — confirmed by the passing Phase 2/3 test suites, not a new claim.

## 4. Existing onboarding and registration (re-confirmed)

- Self-service registration (`POST /auth/register`, `app/register/page.tsx`) exists and works: one form creates the organization, a first station (defaulting to "Main Station"), the caller as that org's Owner, and a 14-day trial subscription, then signs them straight into `/dashboard`.
- **No guided setup checklist exists after that.** A brand-new owner lands on a dashboard that (per the existing single-station auto-redirect) sends them to `/today`, which will show empty states for fuel grades, tanks, dispensers, nozzles, and payment methods — all of which must be configured through Station Settings / Org Settings before Daily Entry can be used at all. Nothing currently tells the new owner this is the required order, or links them directly to it.
- This matches Phase 1's `SAAS_GAP_ANALYSIS.md` finding ("guided onboarding wizard: Not built") and Phase 3's audit — re-confirmed, not a new discovery.

## 5. What this audit does not re-litigate

The 24-hour reading-correction policy, append-only stock ledger, Decimal-precision discipline, and tenant/station isolation mechanics were all independently verified in Phases 2–5 and are not re-tested from scratch here — this audit focuses on what Phase 6 was actually asked to inspect (the Cashier permission gap, the role matrix, and onboarding), and defers to the existing, already-passing test suites for everything else, re-running them in full as part of Step 7 rather than re-reading their logic line by line again.
