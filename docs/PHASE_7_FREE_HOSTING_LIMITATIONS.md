# CYNVEXA — Free Hosting Limitations (Honest Disclosure)

**Date:** 2026-11-15
**Applies to:** the free-tier demonstration/client-review deployment only (Render + Neon, per `docs/PHASE_7_FREE_HOSTING_COMPARISON.md`). **None of this applies once, and if, the owner approves paid production hosting** (`docs/PHASE_7_PAID_PRODUCTION_PLAN.md`).

This deployment is a **demonstration and client-review environment, not production infrastructure.** It must never be described to a client as enterprise-grade, guaranteed-uptime, or suitable for storing a real station's permanent financial records.

---

## 1. Cold starts and sleep

Render's free web services (both frontend and backend, per the selected architecture) spin down after **15 minutes with no incoming traffic**. The first request after that takes roughly **30–60 seconds** to wake the service back up. If both services happen to be asleep at once, a user's very first click of the day could see two sequential wake-ups. **The application must show an honest loading/retry state during this**, not a silent hang or a generic error that looks like the app is broken.

## 2. Resource restrictions

Free web services run on shared, limited CPU/RAM. Under this engagement's existing, already-documented constraint that the in-process rate limiter and JWT/session logic assume a **single instance** (Phase 2), a free single-instance deployment actually matches that assumption correctly — this is not a new limitation introduced by free hosting, it is the one scenario the existing security design was already built for.

## 3. Database expiration / inactivity policy

Neon (selected for the database specifically to avoid this) does not have a reported expiration window in this session's research, unlike Render's own bundled free Postgres (reports conflict on 30 vs. 90 days, both time-boxed). **This was not confirmed by creating a real account** — it must be re-checked at the actual signup step before anyone treats the pilot's data as safe for more than a short review window.

## 4. Storage restrictions

Neon's free plan: 1 GB per project (per Neon's own FAQ, current as of this search). Sufficient for a pilot organization's shift/reading/tender history, not for years of multi-station production data.

## 5. File/evidence storage — the most serious limitation, not downplayed

`app/core/storage.py` writes uploaded tanker-receipt evidence to local disk inside the backend container. On Render's free tier (and most free container platforms), **the filesystem is ephemeral** — any file written to it can be lost on the next deploy, restart, or sleep/wake cycle. **This was already a documented risk before any free-hosting work began** (Phase B/Phase 2); free hosting makes it materially worse, not newly discovered.

**Decision for this pilot stage:** evidence upload should be treated as **not reliable** during the free-tier review period. Do not rely on it for anything the owner or a reviewing client needs to keep. This is not fixed by switching providers within the free tier — it needs real object storage (a future, approved addition), not improvised here.

## 6. Backup limitations

No automated, scheduled, free backup service was found or set up this phase (see `docs/PHASE_7_BACKUP_RESTORE_REPORT.md` for exactly what manual process exists instead). **No claim of automated backups is made anywhere in this engagement's documentation** — only what was actually verified: a manual `pg_dump`/export, tested by restoring it to a separate scratch database.

## 7. Performance and availability

No SLA exists on any free tier used here. A slow or temporarily unavailable free service is expected behavior, not an incident. The application should distinguish this honestly in its own error messaging (e.g., "The server is waking up, please wait a moment" vs. a generic failure) rather than implying something is broken when it's simply asleep.

## 8. Free-tier usage quotas

Render and Neon's free allowances (web-service hours, Neon's 100 CU-hours/project) are generous enough for a low-traffic pilot review but are not unlimited. Sustained real operational use by an actual station would exceed what either free tier is designed for — exactly why Section 13's paid plan exists as the next step once a client confirms.

## 9. Data retention risk — the summary that matters most

**Do not store a real client's actual day-to-day financial records in this free-tier deployment.** It exists to let an owner or prospective client see and try the real product, not to be the system of record for anyone's actual fuel-station operations. The owner retains full control of the code, the database export, and every deployment credential (Section 15 of the brief) specifically so this environment can be torn down and replaced with the approved paid production deployment the moment a real client is confirmed.
