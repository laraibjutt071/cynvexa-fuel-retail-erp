# CYNVEXA — Phase 7 Initial Audit

**Date:** 2026-11-15
**Method:** Read-only review of all Phase 1–6 reports plus direct inspection of the current repository and running stack. No code changed while producing this document.

---

## 1. Repository state — a finding that changes this phase's plan

**93 files are modified or new and have never been committed to git**, across all of Phases 1–6 (permission fixes, the entire frontend security/design-system/Daily Entry/onboarding work, every new test file, every `docs/PHASE_*` report). The GitHub remote (`github.com/laraibjutt071/cynvexa-fuel-retail-erp`, **public**, default branch `main`) still only has the 5 commits from before this engagement began.

**This directly affects Section 8 (deployment).** Every mainstream free-hosting provider (Render, Vercel, Railway, Netlify, Fly.io) deploys by connecting to a GitHub repository and building whatever is on a chosen branch — deploying "from GitHub" right now would deploy the **old, pre-Phase-1 code**, none of this engagement's work. Nothing can be meaningfully deployed before this gap is resolved. **No commit or push has been made without asking first** (git history is treated as an append-only record the owner should confirm, same as every prior phase) — this is flagged here as a blocking question for the owner before Section 8 proceeds.

Checked before flagging this as safe to resolve: `.gitignore` already correctly excludes `.env`/`*.env` (only `.env.example` placeholder files are tracked); no real secret, password, or API key was found in any of the 93 uncommitted files (the only hardcoded credentials anywhere are e2e/test-fixture passwords for ephemeral, locally-seeded accounts — the same pattern already committed in the original `backend/tests/conftest.py` since the initial commit).

## 2. Remaining features / incomplete modules (carried forward from Phase 6, re-confirmed)

| Item | Status |
|---|---|
| Guided onboarding wizard | **Missing.** Self-service registration exists; nothing after it. |
| Payroll frontend | **Missing.** Backend API (`payroll_router`: rules, salary generation/listing/finalization) is materially complete; zero frontend pages consume it. |
| Design-system adoption (`DataTable`/`Skeleton`) | Partial (Phase 4). |
| Accountant's `shift_reconcile:record` scope | Flagged as possibly wider than intended (Phase 5), not changed — needs its own approval. |

## 3. Security (re-verified against Phase 2/6's own evidence, not re-litigated from scratch)

- JWT secret: required field, production additionally rejects a weak/placeholder one (Phase 2). Unchanged.
- Argon2id password hashing, real refresh-token rotation **with reuse detection**, correct access-token expiry (15 min) — unchanged, confirmed by the still-passing Phase 2 test suite.
- Backend RBAC + frontend permission gating: now aligned for every role except the two open items in Section 2 above (Phase 3/5/6).
- Cross-station/cross-organization isolation: proven by dedicated tests across Phases 2, 3, and 6 (most recently the Phase 6 Cashier tank/nozzle tests) — all still passing.
- CORS: config-driven allowlist, no wildcard (Phase 2). **Currently set to `http://localhost:3000` only** — a real production deployment needs this updated to whatever origin the frontend is actually served from (Section 7/8).
- Starlette/FastAPI CVE set: resolved in Phase 2 (`fastapi==0.133.1`, `starlette==1.3.1`), re-scanned clean then — not re-scanned again this phase yet (done in Section 6 below).
- Security headers: `X-Content-Type-Options`, `Referrer-Policy` set at the app layer (Phase 2); HSTS/CSP deliberately deferred to a reverse-proxy/edge layer that doesn't exist yet — directly relevant to Section 7's provider choice, since some free platforms supply HTTPS/HSTS automatically at the edge and some don't.
- Rate limiting: in-process, single-instance only (documented limitation since Phase 2) — relevant to Section 9, since some free backend tiers run exactly one instance (which happens to match this limiter's actual scope) while others may auto-scale.

## 4. Existing tests (exact baseline before this phase touches anything)

- Backend: 259 passing (Phase 6).
- Frontend: `tsc --noEmit` clean, production build clean, 16/16 routes.
- Playwright: 32/32 passing (Phase 6 fixed the last 2 long-standing failures).

Re-run in full as part of Section 10, not assumed still true without re-checking.

## 5. Free-hosting compatibility — what the stack actually needs

- **Backend:** FastAPI + Uvicorn, a long-running process (not a short-lived serverless function — it holds an in-process rate-limiter and a SQLAlchemy connection pool, both of which assume one persistent instance; Phase 2's own documented limitation). Needs: Python 3.12 runtime or a Docker-based deploy (a `Dockerfile` already exists and works), outbound access to Postgres, and the ability to run `alembic upgrade head` on boot (already automated via `docker-entrypoint.sh`).
- **Frontend:** Next.js 16, already configured for a standalone Docker build; also deployable directly to a Next.js-native platform (Vercel) without Docker at all, which is usually the simpler free path for this specific framework.
- **Database:** PostgreSQL 16 specifically (the app uses Postgres-specific features — confirmed throughout Phases 1–6's test runs against real Postgres, never SQLite). Needs a free Postgres host with enough storage for a pilot's worth of data and a connection string reachable from wherever the backend is deployed.
- **File storage:** `app/core/storage.py` writes uploaded evidence (tanker-receipt attachments) to local disk — already documented since Phase B/Phase 2 as **not durable across a container restart or redeploy**. This is the single biggest free-hosting risk: most free container platforms have an **ephemeral filesystem** (wiped on every redeploy, sometimes on every restart). This must be addressed honestly in Section 9, not papered over.
- **Background/scheduled tasks:** none exist in the app today (no Celery, no cron job, no queue) — Section 7's comparison does not need to weigh this capability.

## 6. Deployment blockers, ranked

1. **93 uncommitted files / stale GitHub remote** (Section 1) — blocks any GitHub-integrated deploy until resolved with the owner's go-ahead.
2. **No hosting provider account yet selected or confirmed** — Section 7 researches options; Section 8 cannot create an account or complete an OAuth/email-verification signup on the owner's behalf without the owner actually present for that step (this session has no browser-automation tool to click through a provider's signup UI).
3. **Ephemeral storage risk for uploaded evidence files** (Section 5) — needs a named mitigation (e.g., disable evidence upload for the free pilot, or point it at a free object-storage tier) before calling any deployment "safe" for real client data.
4. **Production CORS origin, JWT secret, and DB credentials** are all still dev values — must be set to real, freshly-generated production values as part of Section 8, never reused from `backend/.env`.

None of these block Sections 1, 7, 9, 13, or 14 (audit, research, limitations, the paid-future plan, and documentation), which proceed regardless.
