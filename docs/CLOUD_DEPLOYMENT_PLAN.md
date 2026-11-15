# CYNVEXA — Cloud Deployment Plan

**Date:** 2026-11-15
**Budget constraint:** PKR 4,000/month (~USD 14/month)
**Deployment model:** Single VPS, Docker Compose, single backend replica
**Status:** PLAN ONLY — no infrastructure purchased, no changes made

---

## 1. Hosting Decision

### Why a Single VPS

At PKR 4,000/month (~USD 14), managed services (AWS ECS, Cloud Run, RDS) are not feasible — a single managed PostgreSQL instance alone costs more than the entire budget on most cloud providers. A single Linux VPS with Docker Compose is the only architecture that fits.

### Recommended Providers (owner approval required before purchase)

| Provider | Plan | vCPU | RAM | Disk | Monthly Cost | Notes |
|---|---|---|---|---|---|---|
| **Hetzner Cloud CX22** | Shared | 2 | 4 GB | 40 GB NVMe | €4.35 (~PKR 1,400) | EU/US datacenters, excellent price/performance |
| **DigitalOcean Basic** | Shared | 1 | 2 GB | 50 GB SSD | $6 (~PKR 1,700) | SGP1 datacenter available (closer to Pakistan) |
| **Contabo Cloud VPS S** | Shared | 4 | 8 GB | 200 GB SSD | €6.99 (~PKR 2,250) | Generous specs for the price |

**Recommended:** Hetzner CX22 or DigitalOcean Basic — both leave room in the PKR 4,000 budget for a domain (~PKR 300-500/year amortized) and DNS.

### What the Budget Does NOT Cover
- Managed database (RDS, Cloud SQL)
- Load balancer
- Object storage (S3) — use local disk for pilot; migrate later
- Separate staging environment
- CDN
- Email service (SendGrid, SES)
- Monitoring SaaS (Datadog, New Relic)

---

## 2. Architecture (Single VPS)

```
Internet
    │
    ▼
┌──────────────────────────────────────┐
│  VPS (Ubuntu 22.04 LTS)             │
│                                      │
│  ┌─────────────┐                     │
│  │  Caddy 2    │ ← TLS termination   │
│  │  (reverse   │   (automatic HTTPS) │
│  │   proxy)    │                     │
│  └──┬────┬─────┘                     │
│     │    │                           │
│     ▼    ▼                           │
│  ┌─────┐ ┌──────────┐               │
│  │front│ │ backend  │               │
│  │end  │ │ (FastAPI)│               │
│  │:3000│ │ :8000    │               │
│  └─────┘ └────┬─────┘               │
│               │                      │
│               ▼                      │
│         ┌──────────┐                 │
│         │PostgreSQL│                 │
│         │  16      │                 │
│         │ :5432    │                 │
│         └──────────┘                 │
│         (localhost only)             │
│                                      │
│  ┌──────────────────────┐            │
│  │ /backups/            │            │
│  │ Daily pg_dump -Fc    │            │
│  │ 7-day rotation       │            │
│  └──────────────────────┘            │
└──────────────────────────────────────┘
```

### Why Caddy Instead of Nginx

- **Automatic HTTPS** via Let's Encrypt — zero manual certificate management
- Single-file config (`Caddyfile`) vs. nginx's multi-file setup
- Automatic HTTP→HTTPS redirect
- Built-in reverse proxy with WebSocket support
- Significantly less configuration to get wrong

### Port Exposure

| Port | Exposed to Internet | Service |
|---|---|---|
| 80 | Yes | Caddy (redirects to 443) |
| 443 | Yes | Caddy (TLS-terminated proxy) |
| 3000 | **No** (localhost only) | Next.js frontend |
| 8000 | **No** (localhost only) | FastAPI backend |
| 5432 | **No** (localhost only) | PostgreSQL |

**PostgreSQL is NEVER exposed publicly.** Docker Compose will bind it to `127.0.0.1:5432` only.

---

## 3. Docker Compose (Production)

A production `docker-compose.prod.yml` will be created separately from the development `docker-compose.yml`. Key differences:

| Concern | Dev (`docker-compose.yml`) | Prod (`docker-compose.prod.yml`) |
|---|---|---|
| Database password | `cynvexa` (hardcoded) | Strong random, from `.env` |
| JWT secret | Dev key | Strong random, from `.env` |
| CORS origins | `http://localhost:3000` | `https://app.cynvexa.com` (actual domain) |
| ENV | `development` | `production` |
| API base URL | `http://localhost:8000` | `https://api.cynvexa.com` (actual domain) |
| DB port binding | `5432:5432` | `127.0.0.1:5432:5432` |
| Restart policy | None | `restart: unless-stopped` |
| Logging | Default | JSON with rotation limits |
| Health checks | pg_isready only | All three services |

### Environment Variables (production)

All injected via `.env` file on the VPS (never committed to Git):

```
ENV=production
DATABASE_URL=postgresql+asyncpg://cynvexa:<STRONG_PASSWORD>@db:5432/cynvexa
JWT_SECRET_KEY=<GENERATED_64_CHAR_SECRET>
CORS_ALLOWED_ORIGINS=https://<DOMAIN>
POSTGRES_PASSWORD=<STRONG_PASSWORD>
NEXT_PUBLIC_API_BASE_URL=https://api.<DOMAIN>
```

### Secret Generation Commands (to run at deploy time)
```bash
# JWT secret
python3 -c "import secrets; print(secrets.token_urlsafe(48))"

# Database password
openssl rand -base64 24
```

---

## 4. Domain & DNS

**Owner decision required:** Choose a domain name. Options:
- `cynvexa.com` (or `.pk`) — brand domain
- A subdomain of an existing domain the owner controls

### DNS Records (once domain is chosen)

| Record | Name | Value | Purpose |
|---|---|---|---|
| A | `@` or `app` | VPS IP | Frontend |
| A | `api` | VPS IP | Backend API |

### Subdomain Strategy

| URL | Service | Notes |
|---|---|---|
| `https://app.cynvexa.com` | Next.js frontend | Or just `cynvexa.com` |
| `https://api.cynvexa.com` | FastAPI backend | Required to be different from frontend for CORS |

**Alternative (single domain):** Caddy can route `/api/*` to the backend and everything else to the frontend on a single domain. This simplifies CORS (same-origin) but the frontend build must be updated to use `/api` prefix instead of a separate domain.

---

## 5. TLS / HTTPS

- Caddy handles all TLS via Let's Encrypt automatically
- Certificates auto-renew (Caddy's built-in ACME client)
- HTTP/2 enabled by default
- No manual certificate management needed
- `ENV=production` in backend enables `secure` cookie flag — this REQUIRES HTTPS to be working first

### Caddyfile (template)

```
app.cynvexa.com {
    reverse_proxy frontend:3000
}

api.cynvexa.com {
    reverse_proxy backend:8000
}
```

---

## 6. Security Hardening (VPS Level)

### Immediate (before first deploy)

1. **SSH key-only authentication** — disable password login
2. **UFW firewall** — allow only 22 (SSH), 80, 443
3. **Fail2ban** — protect SSH from brute-force
4. **Unattended upgrades** — automatic security patches
5. **Non-root deploy user** — never run Docker as root login user

### Docker-Specific

1. Both containers already run as non-root users (`appuser` backend, `node` frontend)
2. PostgreSQL bound to localhost only (never `0.0.0.0`)
3. Docker daemon socket not exposed to containers
4. No `--privileged` flag on any container
5. Log rotation via Docker daemon config:
   ```json
   {
     "log-driver": "json-file",
     "log-opts": { "max-size": "10m", "max-file": "3" }
   }
   ```

### Application-Level (already implemented)

- Rate limiter on login (10 attempts / 5 min per email+IP)
- Rate limiter on registration
- Magic-byte file upload validation
- Content-Type verification for uploads
- Chunked upload size checking
- `.dockerignore` preventing `.env` bake-in
- No Swagger/ReDoc in production (`ENV=production`)
- Secure cookie flag in production
- CORS restricted to exact frontend origin

---

## 7. Backup & Disaster Recovery

### Automated Daily Backup

A cron job on the VPS runs `pg_dump` daily:

```bash
#!/bin/bash
# /opt/cynvexa/backup.sh
set -euo pipefail

BACKUP_DIR=/opt/cynvexa/backups
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

docker exec cynvexa-db pg_dump -U cynvexa -d cynvexa -Fc \
  -f /tmp/cynvexa_${TIMESTAMP}.dump

docker cp cynvexa-db:/tmp/cynvexa_${TIMESTAMP}.dump \
  ${BACKUP_DIR}/cynvexa_${TIMESTAMP}.dump

docker exec cynvexa-db rm /tmp/cynvexa_${TIMESTAMP}.dump

# 7-day retention
find ${BACKUP_DIR} -name "cynvexa_*.dump" -mtime +7 -delete

echo "[$(date)] Backup completed: cynvexa_${TIMESTAMP}.dump"
```

**Crontab:** `0 2 * * * /opt/cynvexa/backup.sh >> /var/log/cynvexa-backup.log 2>&1`

### Off-Site Backup (within budget)

| Option | Cost | Method |
|---|---|---|
| **rclone to free cloud storage** | Free | Sync to Google Drive (15GB free) or Backblaze B2 (10GB free) |
| **SCP to a second VPS** | Over budget | Not recommended for pilot |

**Recommended:** `rclone` sync the backup directory to a free-tier cloud storage account nightly, after the dump completes. This gives geographic redundancy at zero cost.

### Restore Procedure (tested locally — see `docs/DEPLOYMENT.md`)

```bash
# Create a test database to verify the backup
docker exec cynvexa-db createdb -U cynvexa cynvexa_restore_check
docker exec cynvexa-db pg_restore -U cynvexa -d cynvexa_restore_check /path/to/dump
# Verify row counts, spot-check data, check Alembic version
# If verified, restore to production (requires downtime):
docker compose -f docker-compose.prod.yml down
docker exec cynvexa-db dropdb -U cynvexa cynvexa
docker exec cynvexa-db createdb -U cynvexa cynvexa
docker exec cynvexa-db pg_restore -U cynvexa -d cynvexa cynvexa_TIMESTAMP.dump
docker compose -f docker-compose.prod.yml up -d
```

### Upload/Evidence Files

Currently stored on local disk (`/app/uploads` Docker volume). The backup script should also tar this directory:

```bash
tar czf ${BACKUP_DIR}/uploads_${TIMESTAMP}.tar.gz -C /opt/cynvexa/data uploads/
```

**Future:** Migrate to object storage (S3-compatible) when scaling beyond single instance or if evidence durability becomes critical.

---

## 8. Monitoring (Zero-Cost)

### Health Checks

| Endpoint | Type | Check |
|---|---|---|
| `/health` | Liveness | Process is up (no DB touch) |
| `/ready` | Readiness | Process + DB connection |

### Monitoring Strategy

| Layer | Tool | Cost |
|---|---|---|
| Uptime monitoring | **UptimeRobot** (free plan) | Free — 5-minute checks, 50 monitors |
| Container health | Docker Compose `healthcheck` directives | Free |
| Disk/CPU/RAM | `node_exporter` + alerting script or `htop` manual | Free |
| Log review | `docker logs --since 1h backend` | Free |
| Backup verification | Cron job that checks backup file exists and is > 0 bytes | Free |

### Alerting

UptimeRobot's free plan sends email/SMS alerts when `https://api.<domain>/ready` goes down. This is the minimum viable monitoring for a single-VPS pilot.

---

## 9. Deployment Procedure (Step by Step)

### Prerequisites (owner approval required for each)
- [ ] VPS purchased from chosen provider
- [ ] Domain registered or subdomain delegated
- [ ] DNS A records pointing to VPS IP
- [ ] SSH key configured for deploy user

### First Deploy

```bash
# 1. Initial VPS setup
ssh root@<VPS_IP>
adduser deploy
usermod -aG sudo deploy
# Configure SSH key auth, disable password login
# Install Docker, Docker Compose, UFW, Fail2ban, unattended-upgrades

# 2. Clone and configure (as deploy user)
ssh deploy@<VPS_IP>
mkdir -p /opt/cynvexa/{backups,data}
cd /opt/cynvexa
git clone <REPO_URL> app
cd app

# 3. Create production .env (NEVER committed)
cat > .env.prod << 'EOF'
ENV=production
DATABASE_URL=postgresql+asyncpg://cynvexa:<GENERATED_DB_PASSWORD>@db:5432/cynvexa
JWT_SECRET_KEY=<GENERATED_JWT_SECRET>
CORS_ALLOWED_ORIGINS=https://app.<DOMAIN>
POSTGRES_PASSWORD=<GENERATED_DB_PASSWORD>
EOF

# 4. Build and start
docker compose -f docker-compose.prod.yml build \
  --build-arg NEXT_PUBLIC_API_BASE_URL=https://api.<DOMAIN>
docker compose -f docker-compose.prod.yml up -d

# 5. Wait for DB health check, then seed
docker compose -f docker-compose.prod.yml exec backend \
  python -m app.seed permissions-roles
docker compose -f docker-compose.prod.yml exec backend \
  python -m app.seed plans
docker compose -f docker-compose.prod.yml exec backend \
  python -m app.seed superuser --email <ADMIN_EMAIL> --password <ADMIN_PASSWORD>

# 6. Install and configure Caddy
sudo apt install caddy
# Write Caddyfile (see Section 5)
sudo systemctl restart caddy

# 7. Verify
curl https://api.<DOMAIN>/health   # {"status":"ok"}
curl https://api.<DOMAIN>/ready    # {"status":"ready"}
# Open https://app.<DOMAIN> in browser, login with seeded admin

# 8. Set up backups
chmod +x /opt/cynvexa/backup.sh
crontab -e  # Add the backup cron line
```

### Subsequent Deploys (code updates)

```bash
ssh deploy@<VPS_IP>
cd /opt/cynvexa/app
git pull origin main
docker compose -f docker-compose.prod.yml build \
  --build-arg NEXT_PUBLIC_API_BASE_URL=https://api.<DOMAIN>
docker compose -f docker-compose.prod.yml up -d
# Backend entrypoint runs alembic upgrade head automatically
# Verify /health and /ready
```

---

## 10. What This Plan Does NOT Do

These are explicitly out of scope for the PKR 4,000/month budget and single-VPS architecture:

| Item | Why Not | When to Add |
|---|---|---|
| Multi-replica backend | Single VPS, known limitations (see `docs/REMAINING_RISKS.md`) | When scaling past ~50 concurrent users |
| Managed PostgreSQL | Over budget | When budget allows or data durability is critical |
| Object storage (S3) | Over budget, local disk sufficient for pilot | Before multi-replica or if evidence files exceed disk |
| CDN | Over budget | When frontend load warrants it |
| Staging environment | Over budget (needs second VPS) | Before production launch with real financial data |
| Point-in-time recovery (WAL) | Requires managed Postgres or complex manual setup | When RPO < 24h matters |
| CI/CD pipeline | No CI service budgeted | When team grows past 1-2 developers |
| Email notifications | No email service budgeted | When operational alerts are needed |
| DDoS protection | Cloudflare free tier is an option but adds DNS complexity | If attacked |

---

## 11. Risk Assessment

### Risks Accepted for Pilot

| Risk | Impact | Mitigation |
|---|---|---|
| Single point of failure (one VPS) | Total downtime if VPS fails | Daily backups, restore procedure tested, VPS provider's built-in snapshots |
| No staging environment | Bugs reach production without isolated testing | Comprehensive test suite (230 backend + 10 e2e), Docker images identical to local dev |
| 24h backup RPO | Up to 24h of data loss | Acceptable for controlled pilot with <5 users; shorten to 6h cron if needed |
| Local file storage | Evidence files not durable across container recreation | Docker named volume persists across restarts; backup script includes uploads |
| No horizontal scaling | Can't handle sudden traffic spike | Pilot is controlled (<10 users); VPS can be upgraded if needed |

### Hard Blockers (must be done before pilot)

1. [ ] VPS purchased and SSH access confirmed
2. [ ] Domain registered and DNS propagated
3. [ ] TLS working (Caddy + Let's Encrypt)
4. [ ] Production `.env` created with strong secrets
5. [ ] Seed commands run (permissions, roles, plans, first admin user)
6. [ ] Backup cron running and first backup verified
7. [ ] UptimeRobot monitoring configured
8. [ ] Owner has logged in and verified basic flow

---

## 12. Monthly Cost Breakdown (Estimated)

| Item | Monthly Cost (PKR) |
|---|---|
| VPS (Hetzner CX22 or equivalent) | ~1,400 - 2,250 |
| Domain (amortized annually) | ~30 - 50 |
| Monitoring (UptimeRobot free) | 0 |
| Backup storage (Google Drive free) | 0 |
| TLS certificates (Let's Encrypt) | 0 |
| **Total** | **~1,430 - 2,300** |

Well under the PKR 4,000 budget, leaving room for a domain upgrade or VPS size increase if needed.
