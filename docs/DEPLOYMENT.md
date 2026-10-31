# Deployment Guide

This document covers deploying CYNVEXA outside local development. It is split into **staging** and **production** because they have different risk tolerances: staging exists to validate a release candidate against real infrastructure before it reaches production, and can tolerate things production cannot (a shared low-tier database, more permissive CORS for testing, no on-call expectation).

Everything in this guide was written against what the codebase actually does today (verified by reading `docker-compose.yml`, `backend/Dockerfile`, `backend/docker-entrypoint.sh`, `backend/app/config.py`, and `frontend/Dockerfile`), not a generic cloud-deployment template. Where something has NOT been tested against a real cloud provider, that is stated explicitly rather than implied.

## What has and has not been verified

| Item | Status |
|---|---|
| App boots, migrates, and serves traffic in Docker containers | **Verified** — `docker compose up --build`, `/health`, `/ready`, full backend test suite, and the Playwright e2e suite all run successfully against the built images (see `docs/IMPLEMENTATION_PLAN.md`'s Phase G record for exact commands and results). |
| Database backup and restore | **Verified once, locally.** A real `pg_dump -Fc` backup was taken of the dev database, restored into a separate database on the same Postgres server, and its row counts, a sampled row's content, and the Alembic migration version were confirmed to match exactly. This proves the *procedure* works. It does **not** prove point-in-time recovery, restore against a managed cloud Postgres service (RDS/Cloud SQL/etc.), restore under production data volume, or recovery from a corrupted volume — those have not been tested and should be drilled in staging before being relied on. |
| Non-root containers | **Verified** — both images now run as a non-root user (`appuser` backend, `node` frontend); confirmed via `whoami` inside the running containers. |
| Horizontal scaling (more than one backend replica) | **Not verified, and known to need changes first** — see "Before you scale past one backend replica" below. |
| TLS/HTTPS termination | **Not verified** — this app has never been deployed behind a TLS-terminating proxy; see the HTTPS section below for what's expected to work and why it hasn't been tested end-to-end. |
| Cloud provider deployment (any specific provider) | **Not attempted** — no deployment credentials were available in this environment. This guide describes what a deployment needs, not a tested runbook for a specific provider. |

## Required environment variables

All come from `backend/app/config.py` (`Settings`) and `frontend/Dockerfile`'s build arg. Never commit real values — `backend/.env.example` and `frontend/.env.example` are templates only.

| Variable | Where | Notes |
|---|---|---|
| `ENV` | backend | `staging` or `production`. Controls JSON log formatting, `/docs` exposure, and secure-cookie flags (`app/config.py::is_production`). |
| `DATABASE_URL` | backend | `postgresql+asyncpg://user:pass@host:5432/db`. Must point at a real managed Postgres instance in staging/production, never the dev `docker-compose.yml` database. |
| `JWT_SECRET_KEY` | backend | **No default exists in code** — the app will not start without it. Generate with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Rotate by issuing a new value and accepting that all existing access/refresh tokens are invalidated on deploy (there is no key-rotation-with-overlap support). |
| `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS` | backend | Defaults are reasonable; only change deliberately. |
| `CORS_ALLOWED_ORIGINS` | backend | Comma-separated. **Must be the exact HTTPS origin(s) of the deployed frontend** — never `*`, and never an `http://` origin in production. |
| `NEXT_PUBLIC_API_BASE_URL` | frontend (build arg, not env var) | Baked into the client JS bundle at build time (see the Dockerfile's own comment on this). This means **the frontend image must be rebuilt, not just restarted, whenever the backend's public URL changes.** |

### Secret management

- Never put real secrets in `docker-compose.yml`, a Dockerfile, or any file that gets committed. The dev `docker-compose.yml`'s hardcoded `POSTGRES_PASSWORD: cynvexa` is a local-development-only placeholder, not a template to extend into staging/production — that file is not used for either.
- In staging/production, inject secrets through whatever your platform provides for that (a secrets manager, your CI/CD system's encrypted variables, or your orchestrator's secret objects) — never a `.env` file baked into an image. The backend reads `JWT_SECRET_KEY` and `DATABASE_URL` from the process environment at startup (`pydantic_settings.BaseSettings`), so any mechanism that sets environment variables on the container works.
- `backend/.dockerignore` and `frontend/.dockerignore` (added in Phase 7) now exclude `.env*` files from the build context, so a developer's local `.env` can never accidentally get baked into an image layer even if it exists in the directory being built.

## Database

### Connection pooling

Already configured for a reasonable single-instance load in `backend/app/database.py`: `pool_size=10`, `max_overflow=20`, `pool_pre_ping=True`, `pool_recycle=1800`. If you run multiple backend replicas, remember the pool size is **per replica** — N replicas × 10 base connections against your Postgres instance's own `max_connections`, which most managed providers cap well below what you'd expect (e.g. a small RDS instance often defaults to ~100). Size replicas and `max_connections` together; don't scale replica count without checking this.

### Migrations

`backend/docker-entrypoint.sh` runs `alembic upgrade head` automatically on every container boot, then execs into uvicorn. This is convenient and safe **for exactly one running backend instance**, which is how this app has run in every environment so far.

**Before running more than one backend replica**, change the migration step to a separate, explicit deploy action rather than something every replica does on its own boot:

```bash
# As a one-off step BEFORE scaling up new replicas, run migrations once:
docker compose run --rm backend alembic upgrade head
# then start/update the replicas with a normal `docker compose up -d --scale backend=N`
# (or the equivalent Job-then-Deployment pattern in Kubernetes/ECS/etc.)
```

Alembic does not take an advisory lock by default, so N replicas all running `alembic upgrade head` concurrently on the same deploy can race — the realistic failure mode is one or more replicas failing to start (each migration step is its own transaction, so this does not corrupt data), not silent corruption, but it does mean a multi-replica deploy that includes a migration can look like a crash loop until it's retried. See `docs/ASSUMPTIONS.md` #32.

### Indexes

Phase 7 added 29 indexes (migration `eca78cafd252`) covering every organization_id/station_id/shift_id/tank_id-style tenant-isolation filter actually used by a query in this codebase (verified by grepping every `.where(X.*_id ==` in `app/api/` and `app/core/`, not guessed), plus two composite indexes for the hottest queries (`stock_ledger_entries(tank_id, movement_type)` — the book-stock calculation run on every capacity check, shift approval, and variance report; `inventory_movements(inventory_item_id, movement_type)`, its shop-inventory equivalent) and one for the audit log's own `(organization_id, created_at)` filter+sort pattern.

Measured, not estimated: with 200,000 synthetic ledger rows spread across 500 tanks (built, benchmarked, and rolled back in a transaction against the local dev database — nothing persisted), the book-stock query ran in **0.28ms with the index** vs **11.5ms with it disabled** (`SET enable_indexscan/enable_bitmapscan = off`) — roughly 40x, with 220 buffer reads vs 6,030. At the table's current real size the planner correctly prefers a sequential scan (too few rows for an index to help) — the index exists for when the table grows, which is exactly when its absence would otherwise become a real incident.

### Backup and recovery

A tested procedure (see "What has and has not been verified" above):

```bash
# Backup (run against your production Postgres host, not the dev compose db)
pg_dump -h <host> -U <user> -d <database> -Fc -f cynvexa_$(date +%Y%m%d_%H%M%S).dump

# Restore drill (into a NEW database first, never directly over production)
createdb -h <host> -U <user> cynvexa_restore_check
pg_restore -h <host> -U <user> -d cynvexa_restore_check cynvexa_<timestamp>.dump
# then verify row counts / spot-check rows before ever restoring over a real database
```

What you still need to decide and set up before this is a real operational capability, not a procedure that happens to work when run by hand:
- A **schedule** (cron, your cloud provider's managed-backup feature, or a CI job) — none exists yet.
- **Retention** (how many days/weeks of backups to keep, and where — not the same host as the database).
- Whether you need **point-in-time recovery** (continuous WAL archiving), which `pg_dump` alone does not provide — most managed Postgres services offer this natively and it's the simpler path if available.
- A recurring **restore drill** on a schedule, not just once during this review — a backup nobody has restored recently is a backup you don't actually know works.

## File uploads (evidence attachments)

`app/core/storage.py` writes uploaded tanker-receipt evidence to local disk (`UPLOAD_DIR`, default `uploads/`). In `docker-compose.yml` this is a named volume so it survives a container restart — but it is **not safe with more than one backend replica** (each replica has its own disk; a file uploaded to replica A is invisible to replica B) and is not itself backed up by the Postgres backup procedure above. Before any multi-replica deployment, or before relying on uploaded evidence being durable, swap this for object storage (S3 or equivalent) — `Attachment.storage_backend` already exists as a column specifically so this swap doesn't require a schema change, only a different reader/writer in `app/core/storage.py`.

Phase 7 hardened what's validated before a file is accepted (real magic-byte content sniffing against the declared type — not just trusting the client's `Content-Type` header — plus chunked reads that reject an oversized upload before buffering the whole thing into memory), but did not change where files live.

## HTTPS and CORS in production

- **TLS termination**: this app has no built-in HTTPS support (uvicorn serves plain HTTP; `docker-compose.yml` exposes plain HTTP ports). In staging/production, put a TLS-terminating reverse proxy or load balancer (your cloud provider's load balancer, Caddy, nginx, Traefik, etc.) in front of both the backend and frontend containers, and never expose the plain-HTTP container ports directly to the internet. This has not been tested end-to-end in this environment (no such proxy was available to test against) — treat it as a required setup step, not a verified one.
- Set `ENV=production` so `app/config.py::is_production` is true — this flips the refresh-token cookie's `secure` flag on (`app/api/auth.py::_set_refresh_cookie`), which **requires** the connection to actually be HTTPS or browsers will silently refuse to send the cookie back, breaking login. Don't set `ENV=production` until TLS is actually in front of the app.
- Set `CORS_ALLOWED_ORIGINS` to the exact HTTPS origin(s) of the deployed frontend. The CORS middleware (`app/main.py`) already reads this from settings; there is nothing else to configure.
- Rebuild the frontend image with `NEXT_PUBLIC_API_BASE_URL` set to the backend's real HTTPS URL — this is a **build-time** value baked into the JS bundle, not something you can change by restarting the container.

## Staging

Staging's job is to prove a release candidate against infrastructure that behaves like production (a real managed Postgres instance, real TLS, the real container images) before anything reaches production — not to be a second development environment.

1. Provision a small managed Postgres instance (does not need production sizing).
2. Deploy the same container images production will run (`docker compose build` or your CI's image build — never build differently per environment).
3. Set `ENV=staging` (JSON logs, same as production, but `/docs` stays enabled per `app/config.py::is_production` only gating on `production` — deliberately, so staging can still be poked at via Swagger).
4. Run migrations as the one-off step described above, then start the backend.
5. Run the seed commands once (`python -m app.seed permissions-roles`, then `python -m app.seed superuser ...` for a first login).
6. Smoke-test: `/health`, `/ready`, login, one full shift/reconciliation/report cycle through the dashboard — the same cycle the Playwright e2e suite automates, run by hand once against the real staging URL to confirm DNS/TLS/CORS are actually correct end-to-end, which the e2e suite (run against `localhost`) cannot verify.
7. Run a backup+restore drill against the staging database specifically — this is the first time you're validating the procedure against infrastructure that isn't the local dev Docker Postgres.

## Production

Everything from staging, plus:

1. **Do not reuse staging's database, secrets, or JWT key.** Generate fresh values.
2. Decide replica count up front. If more than one backend replica: move migrations to the separate-step pattern above, swap file storage to object storage first, and replace the in-memory login rate limiter with a shared-store (Redis) version — see `docs/ASSUMPTIONS.md` #30/#31/#32 for exactly why each of these breaks silently with more than one replica, and `docs/REMAINING_RISKS.md` for the full list.
3. Put monitoring on `/health` (liveness — intentionally does not touch the database, so it reflects "is the process up," not "is everything healthy") and `/ready` (readiness — does touch the database; wire this into your load balancer's health check and your alerting both). Neither endpoint has been wired into an actual monitoring/alerting system in this environment — that wiring, and its alert thresholds, is a deployment-specific decision this guide cannot make for you.
4. Confirm `ENV=production`, `CORS_ALLOWED_ORIGINS` is the real HTTPS frontend origin, and the frontend image was built with the real `NEXT_PUBLIC_API_BASE_URL`.
5. Schedule backups (see above) and put the restore drill on a recurring calendar, not a one-time checkbox.
6. Read `docs/REMAINING_RISKS.md` in full before calling this launch-ready — several items there are "known gap, not yet fixed," not "theoretical risk."
