# CYNVEXA — Phase 7 Free Hosting Comparison

**Date:** 2026-11-15
**Method:** Live web search performed this session (not recalled from training data, per the explicit instruction not to trust an old tutorial) for current 2026 free-tier terms of each candidate. Each provider's section states how confident the finding is and names the source. Where sources conflicted, the conflict is shown rather than silently picking one number.

---

## 1. Disqualified immediately (owner's explicit rule: no credit card, no auto-converting trial)

### Fly.io — disqualified
Fly.io's own blog (updated September 2026) states the old free-Postgres allowance is gone; new accounts get a time-boxed trial only (reports conflict on exact size: "2 VM-hours or 7 days, whichever comes first" vs. "$5 trial credit"), and a credit card is required to keep anything running once the trial ends. This is exactly the "free trial that automatically converts" risk the owner ruled out. **Not used.**

## 2. Backend hosting (FastAPI + Uvicorn, needs a persistent process)

### Render — selected
- **Free web service**, no credit card required to deploy one, confirmed by Render's own article (`render.com/articles/platforms-with-a-real-free-tier-for-developers-in-2026`).
- **Sleep behavior:** spins down after 15 minutes of no traffic (reduced from a previous 30-minute threshold per one source); cold start back up takes roughly 30–60 seconds. This is an honest limitation, documented again in `docs/PHASE_7_FREE_HOSTING_LIMITATIONS.md` — acceptable for a demo/review deployment, not for a live client's real-time operations.
- **Deploys directly from the existing `backend/Dockerfile`** — no rewrite needed, confirmed against the already-working Dockerfile from Phase 2's own verification.
- Supports setting environment variables (JWT secret, DATABASE_URL, CORS origin) through its dashboard without ever committing them to the repo.
- **Render's own bundled free Postgres is explicitly not used for this app's actual database** (see Section 3) — sources disagree on its exact expiry window (30 days with a 14-day grace period vs. 90 days, per different third-party pages) and agree it's capped at 256 MB either way. That combination (uncertain expiry + very small storage) is not something to build a client-review deployment's actual data on.

## 3. Database (PostgreSQL 16 specifically — the app has never run on anything else)

### Neon — selected
- Neon's own FAQ (`neon.com/faqs/free-plan-limits-and-quotas`, last updated 2026-10-01): Free plan = 100 projects, 10 branches per project, 100 CU-hours per project, **1 GB storage per project** (a September/October 2026 changelog entry confirms this was recently doubled from 0.5 GB — older blog posts still quoting 0.5 GB are out of date).
- No credit card requirement is repeated across multiple third-party sources, but **not found stated on Neon's own official page in this search** — to be confirmed at the actual signup step, not assumed.
- No stated expiration on the Free plan itself (unlike Render's bundled Postgres) — if this changes, it will be caught at signup, not assumed safe in advance.
- **This session already has a Neon MCP integration configured** (listed among this session's available connectors) that is not yet authorized — directly relevant to Section 8, flagged for the owner rather than acted on unilaterally.
- 1 GB is more than sufficient for a pilot/demo organization's worth of shifts, readings, and tenders (orders of magnitude smaller than what this app's own Phase 1 index-benchmark used — 200k rows at realistic size).

## 4. Frontend hosting (Next.js 16)

### Vercel Hobby — viable, with a real caveat to flag, not hide
- Vercel's own Hobby plan page states the plan is for **personal, non-commercial use** — confirmed directly from Vercel's docs. A free, zero-card signup, no 14-day clock, no silent auto-conversion to paid (per multiple independent sources).
- **This is a genuine gray area for CYNVEXA's purpose**, not a clean fit: the brief's own goal is a "demonstration/client-review deployment" (arguably still non-commercial — no money changes hands over the deployment itself), but if a real prospective client starts actually operating a station through it, that crosses into commercial use that Hobby's own terms don't cover. **Flagged for the owner's decision, not assumed acceptable.**
- Deploys the existing Next.js app natively (no Docker needed on Vercel specifically - it builds directly from `frontend/`), which is the simplest possible path for this exact framework.

### Render (second free web service) — the safer alternative, recommended instead
- Using Render for both frontend and backend (two separate free web services, both from the existing Dockerfiles) avoids Vercel's non-commercial restriction entirely, since Render's free-tier terms found in this search carry no equivalent commercial-use exclusion.
- Trade-off: both services independently sleep after 15 minutes idle, so a cold frontend visit while the backend is also asleep could mean two separate ~30-60s wake-ups in sequence on a user's first request of the day. Documented honestly in the limitations report, not hidden.

**Recommendation:** Render for both frontend and backend (avoids the Vercel ToS gray area entirely for a client-facing review deployment), Neon for the database. This is a recommendation for the owner to confirm, not an account that has been created.

## 5. Object/file storage (for `app/core/storage.py`'s evidence uploads)

No free object-storage provider was researched or selected this phase. Given the existing, already-documented risk (local-disk evidence storage is not durable across a redeploy even in the current Docker setup, let alone on a platform with an ephemeral filesystem), the honest recommendation for the free pilot stage is **not** to wire up a new storage provider under time pressure, but to flag evidence uploads as a feature to avoid relying on during the free-tier review period — covered in `docs/PHASE_7_FREE_HOSTING_LIMITATIONS.md`.

## 6. What was explicitly NOT verified by creating a real account

Every limit above comes from public documentation and third-party reporting gathered via live web search this session — **none of it was confirmed by actually signing up**, because doing so requires the owner's active participation (email/GitHub OAuth consent in a browser, which this session has no tool to complete on the owner's behalf). Section 8 names exactly what the owner needs to do before an actual deployment can proceed.
