# CYNVEXA Fuel Retail ERP

A cloud-based petrol station management system that reconciles physical fuel movement with financial movement while keeping responsibility, approvals and exceptions visible.

Start here:
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — technology choices, repository layout, database entity plan, critical business rules.
- [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) — phase-by-phase scope, acceptance criteria, and the completion record for each finished phase.
- [`docs/ASSUMPTIONS.md`](docs/ASSUMPTIONS.md) — every business rule the source blueprint left unresolved, the safe default implemented for each, and who needs to confirm it (owner or accountant).
- [`docs/blueprint/`](docs/blueprint/) — the original discovery document.
- [`docs/UX_UPGRADE_PLAN.md`](docs/UX_UPGRADE_PLAN.md) — the premium UI/UX, multilingual, dashboard and daily-ops upgrade: audit, what changed, and real test results.
- [`docs/STAFF_GUIDE.md`](docs/STAFF_GUIDE.md) — plain-language guide to using the app day to day (owner, station manager, cashier/operator, accountant). Also published as a shareable page for staff who won't be reading this repo.

Deploying or operating this app (not just developing it):
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — staging and production deployment, documented separately; what's been verified vs. not.
- [`docs/OPERATIONS_CHECKLIST.md`](docs/OPERATIONS_CHECKLIST.md) — recurring operational tasks and an incident-response quick reference.
- [`docs/REMAINING_RISKS.md`](docs/REMAINING_RISKS.md) — the prioritized, honest list of what's fixed, what's documented-but-not-fixed, and what hasn't been tested at all (e.g. real cloud deployment, TLS end-to-end).

**Status:** Phases A through G (production readiness) complete for a single-backend-replica deployment. See `docs/REMAINING_RISKS.md` before scaling to more than one backend replica — three specific things need to change first.

## Running locally

### Everything via Docker

```bash
cp backend/.env.example backend/.env   # fill in JWT_SECRET_KEY (see the comment in the file)
docker compose up -d --build
```

- Backend: http://localhost:8000 (`/health`, `/ready`, `/docs` in non-production)
- Frontend: http://localhost:3000

The backend container runs `alembic upgrade head` automatically before starting; migrations are never applied by hand in a deployed environment.

Seed the permission/role catalog and a first platform administrator (run once per environment):

```bash
docker compose exec backend python -m app.seed permissions-roles
docker compose exec backend python -m app.seed superuser --email you@example.com --password "a-strong-password" --full-name "Your Name"
```

### Backend only, without Docker

```bash
cd backend
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements-dev.txt   # Windows
# source .venv/bin/activate && pip install -r requirements-dev.txt   # macOS/Linux
cp .env.example .env   # fill in JWT_SECRET_KEY and point DATABASE_URL at a running Postgres
alembic upgrade head
python -m app.seed permissions-roles
pytest tests/ -v
uvicorn app.main:app --reload
```

### Frontend only, without Docker

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

## Security notes for anyone extending this

- Never commit `.env` files — only `.env.example`.
- All authorization checks go through `app/core/permissions.py::user_has_permission`, reached via `app/api/deps.py::require_permission`. Do not add an endpoint that infers permission from the frontend.
- Approved/financial records are never hard-edited — see the "Approved records are immutable" rule in `ARCHITECTURE.md` before adding any update endpoint on a post-Phase-A model.
- Money and litre columns are `NUMERIC`, never `FLOAT`.
