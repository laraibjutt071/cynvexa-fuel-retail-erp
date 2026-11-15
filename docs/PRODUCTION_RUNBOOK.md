# CYNVEXA — Production Runbook

**Date:** 2026-11-15
**Purpose:** The one document you need to run, update, and troubleshoot the live CYNVEXA deployment. Written against what is actually deployed today, not a generic template.

---

## 1. What is live right now

| Component | URL / Location | Notes |
|---|---|---|
| Frontend (Next.js) | https://cynvexa-frontend-laraib.onrender.com | Render free web service. Builds from `frontend/Dockerfile`. |
| Backend (FastAPI) | https://cynvexa-backend-laraib.onrender.com | Render free web service. Builds from `backend/Dockerfile`. |
| Database (PostgreSQL 18) | Neon project (free tier, 1 GB) | Connection string lives only in Render's env vars — never in this repo. |
| Source of truth | https://github.com/laraibjutt071/cynvexa-fuel-retail-erp, branch `main` | Both Render services auto-deploy on every push to `main`. |
| Render account | Owner: `laraibjutt071@gmail.com` ("My Workspace") | Dashboard: https://dashboard.render.com |

**This is a free-tier demonstration/client-review deployment, not production infrastructure.** See `docs/PHASE_7_FREE_HOSTING_LIMITATIONS.md` for exactly what that means (cold starts, no automated backups, ephemeral file storage, no SLA). Do not store a real station's actual day-to-day financial records here — see `docs/PHASE_7_PAID_PRODUCTION_PLAN.md` for what changes once a real client is confirmed and the owner approves paid hosting.

### Demo account (created for review/testing)

- Login: https://cynvexa-frontend-laraib.onrender.com/login
- Email: `demo.owner@cynvexa.app`
- Password: `CynvexaDemo2026!`
- Role: Owner, organization "CYNVEXA Demo Station"

Anyone with this URL and password can sign in — don't put real data in under this account, and rotate the password (via the Users & Settings page, once signed in) before sharing the link outside a trusted review.

---

## 2. Running it locally (for development)

Requirements: Docker Desktop, nothing else (Python/Node are only needed inside the containers).

```bash
cd "petrleum industry"
docker compose up --build
```

This starts three containers:
- `db` — PostgreSQL 16, with a persistent named volume (`cynvexa_db_data`)
- `backend` — FastAPI on port 8000, runs `alembic upgrade head` automatically on boot
- `frontend` — Next.js on port 3000, built as a standalone production bundle

Open http://localhost:3000. The first time, register a new organization via `/register` — there's no seeded login for local dev.

**Local DB credentials** (dev-only, hardcoded in `docker-compose.yml`, never used anywhere else): `cynvexa` / `cynvexa`.

### Running tests locally

```bash
# Backend (259 tests)
docker compose exec backend pytest

# Frontend type-check
docker compose exec frontend npx tsc --noEmit    # only works if build deps are present; otherwise rebuild the image first

# Full Playwright e2e suite (32 tests) — run from the host, not inside a container
cd frontend
npx playwright test
```

---

## 3. Deploying a change to production

Both Render services have **auto-deploy enabled on `main`**. The entire deploy process is:

```bash
git add <files>
git commit -m "..."
git push origin main
```

That's it — Render picks up the new commit on both services within seconds and rebuilds automatically. No manual trigger needed for a normal code change.

### If you need to force a redeploy without a new commit

(e.g. after changing an env var that didn't auto-trigger a rebuild)

Via the Render dashboard: open the service → **Manual Deploy** → **Deploy latest commit**.

Via the API (if you have the Render API key):
```bash
curl -X POST -H "Authorization: Bearer $RENDER_API_KEY" -H "Content-Type: application/json" \
  "https://api.render.com/v1/services/<service-id>/deploys" -d '{"clearCache":"do_not_clear"}'
```

Service IDs:
- Backend: `srv-dbit1kajnfac73bhmi5g`
- Frontend: `srv-dbsv8rd6e07s73b08fd0`

### Important: the frontend must rebuild, not just restart, when the backend URL changes

`NEXT_PUBLIC_API_BASE_URL` is baked into the client JS bundle **at build time**, not read at container start. If the backend's URL ever changes, you must trigger a new frontend **build** (a push, or a Manual Deploy with cache cleared), not just a restart.

---

## 4. Managing environment variables / secrets

All real secrets live in Render's dashboard (Environment tab on each service) — never in this repo, never in `docker-compose.yml`, never in a committed `.env` file.

**Backend (`cynvexa-backend-laraib`) env vars:**

| Key | Purpose |
|---|---|
| `DATABASE_URL` | Neon connection string (`postgresql+asyncpg://...?ssl=require`) |
| `JWT_SECRET_KEY` | Signs access/refresh tokens. Rotating it invalidates every existing session — there is no overlap support. |
| `JWT_ALGORITHM` | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` |
| `ENV` | `production` — controls JSON logging, `/docs` exposure, secure-cookie flags |
| `CORS_ALLOWED_ORIGINS` | Must exactly match the frontend's URL: `https://cynvexa-frontend-laraib.onrender.com` |
| `PORT` | `8000` |

**Frontend (`cynvexa-frontend-laraib`) env vars:**

| Key | Purpose |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | `https://cynvexa-backend-laraib.onrender.com` — baked in at build time (see Section 3) |
| `HOSTNAME` | **Must be `0.0.0.0`.** Without this, Next.js's standalone server binds to the container's internal hostname instead of all interfaces, and Render's proxy can't reach it (shows as a 502 with a "live" deploy status — this exact bug was hit and fixed on 2026-11-15). |

To change a value: Render dashboard → service → Environment → edit → it will usually auto-trigger a redeploy; if it doesn't (observed to sometimes not happen), force one per Section 3.

---

## 5. Database operations (Neon)

The database was migrated and seeded once, directly, by running commands against the Neon connection string from inside the local `backend` container (never from a machine with the string in shell history longer than necessary):

```bash
docker compose exec -T -e DATABASE_URL='<neon-connection-string>' backend alembic upgrade head
docker compose exec -T -e DATABASE_URL='<neon-connection-string>' backend python -m app.seed permissions-roles
docker compose exec -T -e DATABASE_URL='<neon-connection-string>' backend python -m app.seed plans
```

**Running a new migration against production** (after adding one locally and testing it against the dev DB first): repeat the `alembic upgrade head` command above with the current Neon string. There is no automatic migration-on-deploy for this service — Render just restarts the existing container; migrations are a deliberate, manual step here specifically because the free-tier backend runs as a single instance and the team wants a human to confirm before altering the shared Neon schema.

**Current state:** 46 tables, 7 roles, 56 permissions, 3 subscription plans. Zero real organizations except the demo account in Section 1.

### Backup / restore

See `docs/PHASE_7_BACKUP_RESTORE_REPORT.md` for the exact tested procedure. Short version: `pg_dump -Fc` against the Neon connection string, restore to a scratch database to verify, before trusting any backup.

---

## 6. Health checks and logs

```bash
curl https://cynvexa-backend-laraib.onrender.com/health   # {"status":"ok"}
curl https://cynvexa-backend-laraib.onrender.com/ready    # {"status":"ready"} - confirms DB connectivity
curl https://cynvexa-backend-laraib.onrender.com/plans    # public endpoint, confirms real DB reads work
```

Logs: Render dashboard → service → Logs tab (or `GET /v1/logs?ownerId=...&resource=<service-id>` via the API).

---

## 7. Known issues and their fixes (hit during this deployment)

| Symptom | Cause | Fix |
|---|---|---|
| Frontend shows `502 Bad Gateway` even though the Render deploy status says "live" and logs show `✓ Ready` | Next.js standalone server defaults to binding the container's own hostname instead of `0.0.0.0` when the `HOSTNAME` env var isn't set | Set `HOSTNAME=0.0.0.0` on the frontend service, then force a redeploy |
| Env var change doesn't take effect | Render doesn't always auto-redeploy on an env var update via the API | Force a deploy manually (Section 3) |
| Frontend built but shows stale/wrong UI | `NEXT_PUBLIC_API_BASE_URL` or UI code only takes effect on a fresh **build**, not a restart | Trigger a new build, not just a service restart |
| Can't convert an existing Render service's deploy source (e.g. from a static Docker image to a git repo) | Render's API refuses `docker` parameters on a non-`docker` environment service — this isn't editable in place | Delete the service and recreate it with the same name (same URL/subdomain carries over) |

---

## 8. What's explicitly NOT set up yet (don't assume these exist)

- Automated/scheduled backups — only manual, tested-on-demand `pg_dump`.
- Uptime monitoring/alerting.
- A second environment (staging) — there is only this one free-tier deployment.
- Object storage for evidence/attachment uploads — local disk only, **not durable** on Render's free tier (lost on redeploy/restart). See `docs/PHASE_7_FREE_HOSTING_LIMITATIONS.md` Section 5.
- Paid production hosting — see `docs/PHASE_7_PAID_PRODUCTION_PLAN.md` for what that migration looks like when the owner approves it.

---

## 9. Who to contact / where things live

- GitHub repo (source of truth): https://github.com/laraibjutt071/cynvexa-fuel-retail-erp
- Render account: owned by `laraibjutt071@gmail.com`
- Neon project: owned by the same account that supplied the connection string used in Section 5
- All architectural decisions and their reasoning: `docs/PHASE_1_*` through `docs/PHASE_7_*` reports, in order — each phase's report explains what changed and why, not just what.
