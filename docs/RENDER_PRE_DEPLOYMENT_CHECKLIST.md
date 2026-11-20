# Render Pre-Deployment Checklist

Read-only repository audit, cross-referenced against `docs/PRODUCTION_RUNBOOK.md` (the existing, already-deployed configuration record). **No production credentials were accessed, printed, or modified to produce this document.** Several items below genuinely cannot be verified from this repository — they are marked **MANUAL CHECK** and must be confirmed by whoever has Render dashboard access before trusting a new deploy.

## 1. What this repository can confirm

| Item | Finding | Evidence |
|---|---|---|
| Backend start command | `ENTRYPOINT ["./docker-entrypoint.sh"]`, `CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]` | `backend/Dockerfile` |
| Migration-on-boot | `docker-entrypoint.sh` runs `alembic upgrade head` before `exec "$@"` | `backend/docker-entrypoint.sh` |
| Frontend start command | `CMD ["node", "server.js"]` (Next.js standalone build) | `frontend/Dockerfile` |
| Frontend build command | `npm run build`, with `NEXT_PUBLIC_API_BASE_URL` baked in as a **build arg**, not a runtime env var | `frontend/Dockerfile` lines 11-12 |
| Health endpoint | `GET /health` → `{"status":"ok"}`, liveness only, does not touch the database | `backend/app/api/health.py` |
| Readiness endpoint | `GET /ready` → runs `SELECT 1` through the real `DATABASE_URL`-backed engine, confirming DB connectivity | `backend/app/api/health.py` |
| CORS | `allow_origins` comes from `CORS_ALLOWED_ORIGINS` (comma-split), `allow_credentials=True`, methods limited to `GET/POST/PATCH/DELETE` | `backend/app/main.py`, `backend/app/config.py::cors_origins` |
| Cookie security | Refresh cookie's `secure` flag is `settings.is_production` (`ENV == "production"`), not hardcoded true | `backend/app/api/auth.py` line 49 |
| `/docs`, `/redoc`, `/openapi.json` | Disabled when `ENV=production` | `backend/app/main.py` lines 62-64 |
| `TEST_DATABASE_URL` reachability | Confirmed via repo-wide grep: read nowhere in `backend/app/` outside its own `config.py` field declaration and the test-only safety guard (`app/core/test_db_safety.py`). The running application never reads it. | `docs/TEST_DATABASE_ISOLATION_REPORT.md` |
| `docker-compose.yml`'s `TEST_DATABASE_URL` | A local-only convenience for running pytest inside the dev Docker Compose stack. **Render does not use `docker-compose.yml` at all** - each Render service is built directly from its own `Dockerfile`, so this variable has no path into a Render deployment unless someone manually adds it to that service's Environment tab for no reason. | `docker-compose.yml`; Render builds from `Dockerfile`s per `docs/PRODUCTION_RUNBOOK.md` Section 1 |
| No `render.yaml` or render-specific config file | Confirmed - searched the repository, none exists. Render's service configuration lives entirely in its own dashboard. | repo-wide search |
| Alembic migration strategy in production | **Not automatic on deploy** - `docs/PRODUCTION_RUNBOOK.md` Section 5 states migrations against the Neon database are a deliberate, manual step via a one-off `docker compose exec` with the Neon connection string, specifically so a human confirms before altering shared production schema. The container's own `alembic upgrade head` on boot only applies if Render's own start command runs it - confirm this matches intent (see manual checks below). | `docs/PRODUCTION_RUNBOOK.md` Section 5 |

## 2. What this repository cannot confirm — MANUAL CHECK required

Render's actual per-service configuration (env vars, start command overrides, auto-deploy toggle, build cache settings) lives entirely in Render's dashboard, which this audit has no access to. **Do not assume any of the following are correct without opening the dashboard and looking.**

### Backend service (`cynvexa-backend-laraib`)

- [ ] **Correct backend service** — confirm the service building from this repository's `backend/` directory is the one actually serving `https://cynvexa-backend-laraib.onrender.com` (service ID per the runbook: `srv-dbit1kajnfac73bhmi5g`).
- [ ] **`DATABASE_URL`** is the real Neon production connection string (`...?ssl=require`), not a local/test value, not empty.
- [ ] **No `TEST_DATABASE_URL` is set on this service at all.** It would be harmless even if present (the running app never reads it), but its absence is one more layer of proof this environment can't be confused with a test run — confirm it simply isn't there.
- [ ] **`JWT_SECRET_KEY`** is set, is not one of the known placeholder strings this app's own config rejects in production (`backend/app/config.py`'s `_INSECURE_JWT_SECRET_PLACEHOLDERS`), and is at least 32 characters. Do not print its value anywhere during this check.
- [ ] **`ENV=production`** exactly (controls secure-cookie flag, `/docs` exposure, JSON logging per the runbook).
- [ ] **`CORS_ALLOWED_ORIGINS`** exactly matches the live frontend's URL (`https://cynvexa-frontend-laraib.onrender.com`) — a mismatch here silently breaks every authenticated request from the real frontend with no obvious error message.
- [ ] **`JWT_ALGORITHM`**, **`ACCESS_TOKEN_EXPIRE_MINUTES`**, **`REFRESH_TOKEN_EXPIRE_DAYS`**, **`PORT`** are set per `docs/PRODUCTION_RUNBOOK.md` Section 4's table.
- [ ] **Build/start command** on the Render dashboard isn't overriding the Dockerfile's own `ENTRYPOINT`/`CMD` in a way that skips `alembic upgrade head`.
- [ ] **Health check path** configured in Render's dashboard points at `/health` (liveness) — not `/ready`, which would make Render consider the service down during any brief DB hiccup rather than just not-yet-ready.

### Frontend service (`cynvexa-frontend-laraib`)

- [ ] **Correct frontend service** — confirm it's building from this repository's `frontend/` directory (service ID: `srv-dbsv8rd6e07s73b08fd0`).
- [ ] **`NEXT_PUBLIC_API_BASE_URL`** is set to `https://cynvexa-backend-laraib.onrender.com` **as a build-time variable** — if this was only added as a runtime env var and the image was never rebuilt since, the deployed bundle still points at whatever URL was baked in at the last actual build.
- [ ] **`HOSTNAME=0.0.0.0`** is set — its absence causes the exact 502-despite-"live" failure documented in `docs/PRODUCTION_RUNBOOK.md` Section 7.

### Both services

- [ ] **Auto-deploy on push to `main`** is enabled on both services, if that is still the intended deploy process (per `docs/PRODUCTION_RUNBOOK.md` Section 3, it currently is).
- [ ] **No secrets are committed in this repository.** This audit confirmed `.gitignore` covers `.env`/`*.env` and no `.env` file is tracked (`git ls-files` grep for `.env$` returns empty) — but a final human glance at `git log -p` for anything that looks like a real external credential, before pushing, is still worth doing once.

## 3. Migration strategy — read this before running one

This project's own established process (not something introduced by this checklist) is: **migrations against the production Neon database are never automatic.** They are run once, deliberately, from a local machine with the real Neon connection string passed in as an env var override for that single command, specifically so a human confirms the change before it touches shared production schema (`docs/PRODUCTION_RUNBOOK.md` Section 5). If this phase's work (or a future one) ever adds a real migration, that same manual process is how it reaches production — never a redeploy, never this checklist, never an automated CI step. **This checklist does not run, trigger, or recommend running any migration.** (This phase added no migration at all — see `docs/CLIENT_OWNER_DASHBOARD_REPORT.md`.)

## 4. Rollback plan

Not something this audit can test (it would require an actual deploy), but documenting the existing, already-true mechanism so it's written down before it's needed:

- **Code rollback**: Render's **Manual Deploy** → pick an earlier commit from the deploy history → **Deploy**. Both services keep their last several builds available for this.
- **Database rollback**: there is currently no automated migration-down tooling exercised in this project for production (per Section 3, migrations are manual and deliberate) — a schema rollback would mean manually running the corresponding Alembic `downgrade` against the Neon connection string, the same deliberate, human-confirmed way an `upgrade` is run. **No migration is part of this phase's changes, so no rollback of this kind is needed for this deploy.**
- **If a deploy serves a visibly broken frontend/backend**: roll back to the last known-good commit via Manual Deploy on whichever service regressed, rather than attempting a forward-fix under pressure.

## 5. What this phase actually changed (for context, not a repeat of other reports)

This checklist was written alongside three changes in the current uncommitted/local work: a Meter Events navigation link, a cross-tenant data-isolation fix in the pending-approvals report, and an enhancement to the existing Phase 8c Client Owner Dashboard (a new read-only `daily-sales` report endpoint, zero schema change). None of the three require any Render configuration change, any new environment variable in production, or any migration. Full detail in `docs/CLIENT_OWNER_DASHBOARD_REPORT.md` and `docs/REMAINING_RISKS.md`.

## 6. Verdict

**Everything verifiable from this repository is consistent with a safe deploy.** The items under Section 2 are the only gate — they must be manually confirmed on Render's dashboard by someone with access before pushing, not because this audit found a problem, but because this audit structurally cannot see that far. This document does not itself authorize a push or deploy.
