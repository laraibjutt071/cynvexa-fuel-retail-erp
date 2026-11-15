# CYNVEXA — Future Paid Production Deployment Plan

**Date:** 2026-11-15
**Status: DOCUMENTATION ONLY.** No payment has been made, no VPS reserved, no domain registered, nothing has been activated. This plan is not executed until the owner confirms a real client and explicitly approves the spending.

This document builds directly on `docs/CLOUD_DEPLOYMENT_PLAN.md` (already produced in an earlier phase, with real provider pricing researched then) and adds what's specific to *migrating* from the free-tier demonstration deployment (`docs/PHASE_7_FREE_HOSTING_COMPARISON.md`) to paid infrastructure, rather than re-deriving everything from scratch.

---

## 1. When this plan activates

Only after: (a) a real client has reviewed the free-tier demonstration deployment and confirmed they want to proceed, and (b) the owner has explicitly approved the monthly cost below. Neither condition is met at the time this document was written.

## 2. VPS selection (unchanged from the existing plan, re-cited not re-researched this phase)

Per `docs/CLOUD_DEPLOYMENT_PLAN.md` Section 1: Hetzner CX22 (€4.35/mo, ~PKR 1,400) or DigitalOcean Basic ($6/mo, ~PKR 1,700) were the two recommended options within the owner's PKR 4,000/month target, leaving room for a domain and DNS. **These prices should be re-verified at the point this plan is actually activated** — this document does not claim they are still current months or years later, only that they were real, checked prices when that plan was written.

## 3. Custom domain

Not yet selected. `docs/CLOUD_DEPLOYMENT_PLAN.md` Section 4 already lays out the DNS record structure (`app.` / `api.` subdomains or a single-domain + path-routing alternative) — a specific domain name is an owner decision, not a technical one, and remains open.

## 4. PostgreSQL production database

Two real options, to be decided at migration time:
- **Self-hosted on the VPS itself** (what `docs/CLOUD_DEPLOYMENT_PLAN.md` already specs: PostgreSQL 16 in Docker Compose, bound to `127.0.0.1` only, never exposed publicly) — full control, included in the VPS cost, no extra monthly fee.
- **Keep using Neon, upgraded to its paid tier**, if the free-tier pilot's data should carry forward without a migration step at all. This trades a small recurring Neon fee for zero data-migration risk, worth weighing once real usage patterns from the pilot are known.

## 5. Persistent file storage (the item free hosting could not safely provide)

This is the one capability the free-tier stage explicitly could not deliver (`docs/PHASE_7_FREE_HOSTING_LIMITATIONS.md` Section 5). For paid production: either (a) a Docker named volume on the VPS (simplest, already partially modeled in the existing `docker-compose.yml`'s `cynvexa_uploads` volume, but still single-instance-only, consistent with the VPS's own single-replica design), or (b) a real S3-compatible object storage service once the schema's own `Attachment.storage_backend` field (already designed for this swap, per `docs/ASSUMPTIONS.md`) is wired up. Decision deferred to the owner at migration time, not assumed here.

## 6. HTTPS, firewall, and the rest of the hardening checklist

Already fully specified in `docs/CLOUD_DEPLOYMENT_PLAN.md` Sections 5–6 (Caddy for automatic HTTPS, UFW firewall rules, fail2ban, SSH key-only auth, non-root containers — the last of which is already true today, verified in Phase 2). Not re-written here; that document remains the source of truth for the *technical* hardening steps.

## 7. Automated backups and restore testing

Already specified in `docs/CLOUD_DEPLOYMENT_PLAN.md` (daily `pg_dump -Fc`, 7-day rotation). **This plan adds one requirement the earlier draft didn't emphasize strongly enough:** before this migration is considered complete, a real backup must be restored to a separate scratch database and verified to contain real organization/station/financial/audit data — the same standard `docs/PHASE_7_BACKUP_RESTORE_REPORT.md` already holds the free-tier pilot to. A successful `pg_dump` alone is not proof of recoverability, on the free tier or the paid one.

## 8. Monitoring

Not yet specified in detail. At minimum: the existing `/health` (liveness) and `/ready` (DB-connectivity) endpoints (already built, Phase 1) should be polled by an external uptime check — a free tier of a dedicated monitoring service (e.g., UptimeRobot's free plan) is a reasonable zero-cost addition at this stage, to be confirmed against its own current free-tier terms the same way Section 7 verified hosting providers, not assumed from memory.

## 9. Deployment process

Standard `docker compose -f docker-compose.prod.yml up -d --build` against the real VPS, with migrations run as a separate, explicit step before scaling (already the documented pattern in `docs/DEPLOYMENT.md`'s production section, re-confirmed in Phase 2's own review) — not on every container boot, which is fine for a single-instance free-tier pilot but was already flagged as a multi-replica race risk for anything bigger (`docs/REMAINING_RISKS.md` item 2).

## 10. Data migration from free hosting

1. Full `pg_dump -Fc` export from Neon (or wherever the pilot's data actually lives at that point).
2. Restore into the new production Postgres (self-hosted or Neon paid tier) on a scratch instance first — verified per Section 7 above — before pointing the real app at it.
3. Re-point `DATABASE_URL`, `JWT_SECRET_KEY` (a **new**, freshly generated one — never reuse a free-tier secret in production), `CORS_ALLOWED_ORIGINS`, and `NEXT_PUBLIC_API_BASE_URL` to the new domain.
4. Keep the free-tier deployment running, untouched, until the new one is confirmed working end to end — a real rollback path, not a leap of faith.

## 11. Rollback

If the paid deployment has a problem after cutover: DNS and environment variables point back at the free-tier deployment (kept alive, not torn down, until the paid one is proven stable for a real operating day), and the paid VPS is debugged separately without the client-facing system being down in the meantime.

## 12. Estimated monthly cost (PKR, re-stated from the existing researched figures — not re-verified this phase)

| Item | Estimate |
|---|---|
| VPS (Hetzner CX22 or DigitalOcean Basic) | PKR 1,400 – 1,700 |
| Domain (amortized monthly) | PKR 25 – 40 |
| Backup storage (if off-VPS) | To be decided — not costed yet |
| **Total** | **Roughly PKR 1,500 – 1,800/month**, comfortably inside the owner's PKR 4,000 target, leaving headroom for a monitoring service or off-site backup storage if one is added |

**This is an estimate carried forward from an earlier phase's real research, not a new quote obtained this phase** — it must be re-checked against current pricing at the moment the owner actually approves spending, not treated as still-valid indefinitely.
