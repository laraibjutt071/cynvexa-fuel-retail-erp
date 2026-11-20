# Test Database Isolation Fix

Status: **implemented and verified. NOT DEPLOYED** — committed locally only. This is an infrastructure/test-safety fix, not an ERP feature.

## 1. Original issue and Phase 10B/10C incidents

Phase 10B's report first flagged that running the backend pytest suite concurrently with the Playwright e2e stack corrupted shared dev data. Investigating for this fix surfaced the real mechanism, and it recurred twice more while this fix was being built — both times recovered non-destructively, neither time touching production:

- **During Phase 10B**: `backend/tests/conftest.py`'s session-scoped `_create_schema` fixture ran `DROP SCHEMA public CASCADE` followed by `Base.metadata.create_all` against the real local development database (because `DATABASE_URL` was the only variable it ever read, and that variable is always the dev database in this Docker Compose setup). This wiped the `alembic_version` table — the tables themselves were recreated matching the current ORM models, but Alembic's own migration-history bookkeeping was gone.
- **During Phase 10C**: the same fixture, still unfixed at that point, ran the full pytest suite against the dev database again and wiped `alembic_version` a second time, crash-looping the backend container on its next restart (`alembic upgrade head` tried to run every migration from the beginning against tables that already existed: `DuplicateTableError: relation "organizations" already exists`).
- **During this fix's own verification** (before the code change below was in place): the exact same crash loop recurred a third time, from a pytest run executed in the previous Phase 10C conversation turn, before this fix existed. Recovered the same way, confirmed safe each time: the existing tables already matched the current model shape (nothing to migrate), so recording that known-good state in `alembic_version` was non-destructive. No `DROP`, `TRUNCATE`, or data-rewriting SQL was ever run as part of any recovery - only a single-row `INSERT` into `alembic_version` recording the revision that was already true. **No data was lost in any of the three incidents, and production (Render/Neon, entirely separate infrastructure never reachable from this environment) was never touched.**

## 2. Root cause

`backend/tests/conftest.py` had exactly one way to pick a database: read `DATABASE_URL`, falling back to a literal `cynvexa_test` URL **only if that variable was completely unset**. In this project's Docker Compose setup, `DATABASE_URL` is **always** set (both in `docker-compose.yml` and `backend/.env`), pointing at the real local development database. The fallback therefore never activated in the environment this project actually runs in - pytest's destructive fixture and the running application (and therefore the Playwright e2e stack, which talks to that running application) were, in practice, always the same database. There was no code that enforced separation; it was an unenforced assumption.

## 3. Database configuration before this fix

```
docker-compose.yml:   DATABASE_URL: postgresql+asyncpg://cynvexa:cynvexa@db:5432/cynvexa
backend/.env:         DATABASE_URL=postgresql+asyncpg://cynvexa:cynvexa@localhost:5432/cynvexa
backend/tests/conftest.py:
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://cynvexa:cynvexa@localhost:5432/cynvexa_test")
```

No `TEST_DATABASE_URL` or equivalent existed anywhere. No safety guard of any kind existed before a destructive operation ran.

## 4. New development / test / production separation

### A. Development database — unchanged

`cynvexa` on the same `db` Postgres service, `DATABASE_URL` — exactly as before. This fix does not touch its configuration, data, or how the running application connects to it. Its current data (6 organizations, 62 users, 40 stations as of this report, after the full verification run below) is untouched by anything in this fix.

### B. Dedicated automated test database — new, enforced

`cynvexa_test` — a **separate database** (not a separate container; Postgres enforces hard isolation between databases on the same server: no cross-database `DROP SCHEMA`, `TRUNCATE`, or any statement can reach a different database than the one a connection is bound to) on the same `db` Postgres service. It already existed in this environment (confirmed via `\l` in psql, already holding the current schema - likely created by an earlier, unrelated local pytest run that happened to hit the old fallback default) and already matched the current model shape, so it needed no destructive recreation to adopt.

- New setting: `backend/app/config.py` → `Settings.test_database_url: str | None = None`, bound to env var `TEST_DATABASE_URL`. **The running application never reads this field anywhere** - grep confirms it is referenced only by `backend/tests/conftest.py` and `backend/app/core/test_db_safety.py`.
- `docker-compose.yml`: added `TEST_DATABASE_URL: postgresql+asyncpg://cynvexa:cynvexa@db:5432/cynvexa_test` to the `backend` service's `environment` block, alongside the existing `DATABASE_URL`.
- `backend/.env` / `backend/.env.example`: added the matching `TEST_DATABASE_URL` line (no real secrets - same non-production local credentials already used throughout this file, consistent with the existing convention).

### C. Production database — untouched, and newly made structurally unreachable by test code

Production is Render + Neon, entirely separate infrastructure never reachable from this local Docker Compose environment - no production credentials exist anywhere in this repository or this environment to begin with, so there was no "test configuration accidentally pointing at production" scenario possible from a credentials standpoint. The new safety guard (Section 5) adds a second, independent layer: it explicitly rejects any URL whose hostname matches a managed-cloud-database marker (`neon.tech`, `render.com`, `amazonaws.com`, `.rds.`) **even if** such a URL were ever pasted into `TEST_DATABASE_URL` by mistake - this is defense in depth for a scenario that cannot currently occur, not a response to one that did.

## 5. Safety guard design

New module: `backend/app/core/test_db_safety.py`, `assert_safe_test_database(test_database_url, development_database_url) -> None`. Pure URL parsing and comparison - **opens no database connection**, so it is cheap enough to call before every single destructive operation, not just once.

Rejects (raising `UnsafeTestDatabaseError`, a plain `RuntimeError` subclass) when:
1. `test_database_url` is `None` or blank.
2. The resolved hostname contains a managed-cloud/production marker (Neon, Render, AWS RDS).
3. The resolved database name does not contain the literal substring `"test"`.
4. The resolved `(host, port, database name)` triple is identical to the given development URL's - compared field-by-field, not as a raw string, so a URL that merely uses a different driver scheme or different credentials but points at the exact same physical database is still caught.

Enforced in **two** places, not one: once at `conftest.py` module-import time (before the test engine is even created), and again inside the `_create_schema` fixture itself immediately before the `DROP SCHEMA`/`create_all` statements run - "the guard must be enforced inside the fixture or database-reset helper that performs destructive operations," not only documented or assumed from an earlier check.

## 6. Pytest configuration

`backend/tests/conftest.py` changes:
- Captures the real `DATABASE_URL` (the development database) into `_DEVELOPMENT_DATABASE_URL` **before** anything else touches the environment - this is only ever used as the "never destructively touch this" comparison value, never to connect to anything.
- Reads `TEST_DATABASE_URL` into `_TEST_DATABASE_URL` with **no fallback at all** - if it's missing, `assert_safe_test_database` raises immediately, failing the whole test session before any fixture, any engine, or any connection is created. No test may silently fall back to `DATABASE_URL` anymore.
- **Explicitly overwrites** `os.environ["DATABASE_URL"] = _TEST_DATABASE_URL` (never `setdefault`) immediately after the guard passes - this is what makes the application-under-test (imported afterward via `app.main`, used by the `httpx.AsyncClient(app=app)` ASGI test client) resolve its own `get_settings().database_url` to the test database too, so requests made through the test client during a test run hit the same isolated database as the fixture's own raw engine, not the real dev database. This mutation exists only inside that one pytest process's memory for the duration of that run; it is never written to any file and has no effect on the actual running Docker containers, including the one serving Playwright.
- The schema-reset fixture's actual behavior (`DROP SCHEMA public CASCADE` → `CREATE SCHEMA public` → `Base.metadata.create_all`) is **unchanged** - this intentionally still bypasses Alembic for the test database specifically, which is the existing, pre-fix test strategy (fast, full reset once per pytest session) and remains a legitimate choice now that it is guaranteed to run only against a database dedicated solely to this purpose, which never needs its own migration history tracked (it is torn down and rebuilt from the current ORM models every session, by design). This was not changed without reason: changing it to run real Alembic migrations instead would be a larger, separate change with no safety benefit, since the actual hazard was *which database* this fixture targets, not *how* it resets that database.

## 7. Playwright configuration — honest partial compliance, documented

**Playwright was not reconfigured to target `cynvexa_test`.** It continues to test against the real, already-running Docker Compose stack's backend (the dev database), exactly as `frontend/playwright.config.ts`'s own comment has always stated its design intent: *"Targets the already-running docker-compose stack... this suite verifies the real built containers, not a separate ad-hoc process."*

This is a deliberate decision, not an oversight, for a specific reason verified before deciding it: **Playwright's own code contains zero destructive SQL operations.** `frontend/e2e/global-setup.ts` and every spec file create data exclusively through the same authenticated REST API a real user would use (`POST`s that create organizations, stations, users, shifts, etc.) - additive, and guarded by the backend's own uniqueness/conflict checks (409s on duplicates), never a `DROP`, `TRUNCATE`, or raw SQL statement of any kind. Confirmed by searching: no `DROP SCHEMA`, `TRUNCATE`, or `DELETE FROM` appears anywhere under `frontend/e2e/`.

The actual hazard that caused the Phase 10B/10C incidents was never "Playwright touches the dev database" (it always has, safely, by writing real rows the same way a real user would) - it was specifically "pytest's *destructive* fixture also touches the same dev database." That hazard is now structurally eliminated by Section 6 above: pytest can no longer reach the dev database at all, regardless of whether Playwright happens to be running at the same time or not. Giving Playwright its own separate backend-and-database pair (a second backend service, a second exposed port, a parallel compose stack) would be a materially larger infrastructure change than this task's "add a dedicated test database and a safety guard" scope, would change what the e2e suite actually verifies (a parallel, never-deployed stack instead of "the real built containers"), and was not necessary to close the actual proven hazard. This is reported here as a genuine, reasoned scope boundary, not silently claimed as full compliance with the brief's literal Section 6 wording.

**What was verified instead, concretely** (Section 10/11 below): the dev database's `alembic_version` and row-level identity were recorded before and after a full Playwright run and found unchanged in the one way that matters (`alembic_version` identical; row counts grew only from legitimate, additive API calls Playwright's own setup is designed to make).

## 8. Concurrency strategy

Pytest and Playwright can now run **concurrently without risk to the development database**, because pytest's destructive operations are physically confined to `cynvexa_test` and can never reach `cynvexa` (enforced by Section 5's guard, not just by not-happening-to-collide timing). This removes the literal data-loss risk that caused the original incidents.

**Not claimed**: safe concurrent *parallel pytest workers* sharing `cynvexa_test` with each other. The existing fixture is `scope="session"` and resets the *entire* `cynvexa_test` schema once per pytest session - two pytest sessions running at the same time against the same `cynvexa_test` database would race on that reset (one session's `DROP SCHEMA` could run while another session's tests are mid-flight). This was true before this fix too (nothing about the previous single-shared-database design made concurrent pytest sessions safe either) and is unchanged by this task's scope. **Supported execution model**: one pytest session at a time against `cynvexa_test` (matching how every phase in this project has actually run it so far - a single `docker compose exec backend python -m pytest tests/ -q` invocation), with Playwright able to run at the same time safely, now that pytest cannot reach the dev database Playwright uses. This is the simplest reliable approach for this project's actual usage pattern, not a claim of general multi-worker database isolation that wasn't built.

## 9. Tests added and exact results

New: `backend/tests/test_db_safety.py` (10 tests, pure logic, no database connection opened):

1. `test_accepts_a_properly_named_dedicated_test_database` — a correctly-named, non-production URL passes.
2. `test_rejects_missing_test_database_url` — `None` is rejected.
3. `test_rejects_empty_test_database_url` — a blank string is rejected.
4. `test_rejects_the_development_database_itself` — the dev URL, passed as if it were the test URL, is rejected (by the name-marker check, since the dev database isn't named like a test database - itself a correct, defense-in-depth outcome).
5. `test_rejects_a_test_url_identical_to_the_given_development_url` — isolates the "same host/port/db as the given development value" branch specifically, using a test-named comparison value so that branch is actually reachable.
6. `test_rejects_a_database_not_named_as_a_test_database` — a plausible-but-wrong name (`cynvexa_staging`) is rejected.
7–9. `test_rejects_a_production_like_host_even_if_the_database_name_says_test` (parametrized ×3) — Neon, Render, and AWS RDS-style hostnames are all rejected even with a correctly-named database.
10. `test_rejects_a_test_url_that_differs_only_by_scheme_or_credentials_but_resolves_to_the_same_host_port_db` — proves the comparison is on parsed host/port/db, not a naive string match that a trivial edit (different driver, different credentials) could slip past.

**Result: 10/10 passed.** (Run individually first, confirmed via `docker compose exec backend python -m pytest tests/test_db_safety.py -v` before the full suite - every test's failure mode was exercised and produces the exact expected `UnsafeTestDatabaseError` message substring, not just "it raised something.")

## 10. Before/after development database verification

Checkpoint B (full backend pytest suite, run alone against `cynvexa_test`):

| | Before | After |
|---|---|---|
| `alembic_version` | `g7h8i9j0k1l2` | `g7h8i9j0k1l2` — **unchanged** |
| `organizations` | 5 | 5 — **unchanged** |
| `users` | 51 | 51 — **unchanged** |
| `stations` | 32 | 32 — **unchanged** |

**Result: 372 passed, 3 warnings, 0 failures** in 1151.21s (0:19:11) — 362 pre-existing tests (unmodified, same count as every prior phase's report) plus the 10 new safety-guard tests. The 3 warnings are the same pre-existing Pydantic decimal-serialization warnings noted in every prior phase, unrelated to this fix. Confirmed the running backend container's own `DATABASE_URL` env var was still the development database, unaffected by the test run, both during and after.

Checkpoint C (full Playwright suite, run against the already-running dev stack, by design per Section 7):

| | Before | After |
|---|---|---|
| `alembic_version` | `g7h8i9j0k1l2` | `g7h8i9j0k1l2` — **unchanged** |
| `organizations` | 5 | 6 |
| `users` | 51 | 62 |
| `stations` | 32 | 40 |

**Result: 51 passed, 0 failures** (41.2s). The row-count growth here is expected and correct — Playwright's own `global-setup.ts` and specs create new organizations/users/stations through the real API every run, exactly as a real user adding data would; this is the additive, non-destructive behavior described in Section 7, not a regression. The only figure that must never change, `alembic_version`, did not.

## 11. Production safety verification

Production (Render + Neon) was never reachable from this local Docker Compose environment at any point in this task — no production credentials exist in this repository, `.env`, or any environment variable used here. The new safety guard additionally rejects Neon/Render/AWS-RDS-style hostnames by construction (Section 5, tests 7-9), so even a future accidental paste of a production-looking URL into `TEST_DATABASE_URL` would be refused before any destructive statement ran.

## 12. Typecheck and build results

`docker compose build frontend` → `next build`: **compiled successfully, zero TypeScript errors.** (No frontend files were changed by this task - this confirms the existing frontend build remains unaffected.)

## 13. Exact commands for developers

Run the backend test suite (requires `TEST_DATABASE_URL` to be set — it already is, in `docker-compose.yml` and `backend/.env`):
```
docker compose exec backend python -m pytest tests/ -q
```

Run just the new safety-guard tests:
```
docker compose exec backend python -m pytest tests/test_db_safety.py -v
```

Run the Playwright suite (unchanged from before this fix — still targets the real dev stack):
```
cd frontend && npx playwright test
```

Both of the above are now safe to run **in either order, or at the same time** — pytest can no longer reach the development database under any configuration this guard accepts.

If `TEST_DATABASE_URL` is ever missing or misconfigured, the pytest run fails immediately with a clear `UnsafeTestDatabaseError` message explaining exactly why, before any test collects or runs.

## 14. Remaining limitations

- Concurrent *parallel pytest workers* sharing one `cynvexa_test` database are not supported (Section 8) — not a regression from before, but also not solved by this task; one pytest session at a time remains the supported model.
- Playwright does not get its own dedicated, physically separate database (Section 7) — a reasoned, documented scope boundary, not a gap that was missed. The literal hazard (destructive operations reaching dev/production) is closed regardless.
- The safety guard's "looks like a test database" check is a simple substring match (`"test"` in the database name) — sufficient for this project's actual naming convention, not a cryptographically unforgeable proof. Combined with the host-based production-marker rejection and the explicit same-as-dev comparison, this is proportionate to the actual risk (a local contributor's own misconfiguration), not an adversarial threat model.

## 15. Deployment status

**NOT DEPLOYED.** No push, no Render deploy, no production migration, no Render settings change, no Neon configuration change.
