# Operational Checklist

A working checklist for running CYNVEXA day to day, not a one-time launch gate (that's `docs/DEPLOYMENT.md`). Each item says whether it's already true of the running system, or something an operator still has to set up.

## Before every deploy

- [ ] `pytest tests/` passes (backend). As of Phase 7: 176 passed, 0 failed.
- [ ] `npm run build` and `npm run lint` pass (frontend).
- [ ] `npx playwright test` passes (end-to-end, against the built containers). As of Phase 7: 6 passed, 0 failed.
- [ ] If the deploy includes a migration and you run more than one backend replica: run `alembic upgrade head` as a separate one-off step before updating replicas — see `docs/DEPLOYMENT.md`'s migrations section. (Not needed for a single-replica deploy; the entrypoint handles it.)
- [ ] If `NEXT_PUBLIC_API_BASE_URL` changed: rebuild the frontend image (restarting it is not enough — the value is baked into the JS bundle at build time).
- [ ] Review `git diff` for anything that looks like a committed secret before pushing — `backend/.dockerignore`/`frontend/.dockerignore` keep `.env*` out of images, but that doesn't stop a secret from landing in git history if someone edits the wrong file.

## Daily / routine

- [ ] Confirm the backup job actually ran (once a schedule exists — see `docs/DEPLOYMENT.md`'s backup section; no schedule exists yet, this is a setup task, not a currently-running check).
- [ ] Watch `/ready` failures in whatever monitors it — a sustained `/ready` failure with `/health` still OK means the app is up but the database is unreachable, which is actionable (check the DB, not the app).
- [ ] Skim structured logs for `"level": "ERROR"` — every unhandled exception logs the full traceback server-side only (`app/main.py`'s exception handlers), by design, so this is the only place to see what actually broke when a client got a generic 500.

## Weekly / periodic

- [ ] Run a backup **restore** drill, not just confirm the backup file exists — a backup nobody has restored is unverified. See `docs/DEPLOYMENT.md`'s tested procedure.
- [ ] Re-run `pip-audit -r backend/requirements.txt` and `npm audit` (frontend) — dependency vulnerability data changes over time; what was clean at Phase 7 (see `docs/IMPLEMENTATION_PLAN.md`'s Phase G record for the exact findings and fixes applied then) will not stay clean indefinitely.
- [ ] Check login-rate-limiter behavior if you've since added a second backend replica — if you have, the current single-instance limiter (`app/core/rate_limit.py`) is no longer providing the protection its own docstring claims; see `docs/ASSUMPTIONS.md` #30.

## Incident response quick reference

| Symptom | Likely cause | Where to look |
|---|---|---|
| `/health` OK, `/ready` failing | Database unreachable (network, credentials, or the DB itself is down) | `DATABASE_URL`, the Postgres instance's own status, connection pool exhaustion (`app/database.py`'s `pool_size`/`max_overflow` vs. the DB's `max_connections`) |
| Login returns 429 for a real user | They tripped `login_limiter` (10 failed attempts / 5 min per email+IP) - or, behind a shared NAT/proxy, many users share one IP and collectively tripped it | `app/core/rate_limit.py`; the limiter resets per-key on the next successful login for that key, or naturally after the 5-minute window |
| A deploy with a migration crash-loops on 2+ replicas | Concurrent `alembic upgrade head` race (see `docs/ASSUMPTIONS.md` #32) | Run the migration as a separate step before scaling up, per `docs/DEPLOYMENT.md` |
| An uploaded receipt attachment "disappears" | More than one backend replica, each with its own local disk (see `docs/ASSUMPTIONS.md` #31) | Not a bug in the usual sense - this is the known local-disk-storage limitation; the fix is object storage, not a restart |
| A report or dashboard figure looks wrong | Reports are *derived*, never hardcoded (`app/api/reports.py`) - a wrong figure means either the underlying records are wrong/missing, or a genuine bug | Check the audit log for the entity in question first (`/organizations/{id}/audit-log?entity_type=...&entity_id=...`) before assuming the report math is wrong |
| 500 with no detail to the client | By design in production (`app/main.py`'s unhandled-exception handler never leaks a traceback to the client) | The full traceback is in the server's structured logs, not the HTTP response - check there |

## What "done" looks like for an item on this list

An unchecked box above is either a one-time setup task (backup schedule, restore drill cadence, monitoring wiring) that hasn't been done in *this* environment, or a recurring task that needs to actually recur, not something broken in the code. Don't read an unchecked box as a bug report.
