# CYNVEXA — Phase 2 Security Hardening & Verification Report

**Date:** 2026-11-15
**Scope:** Security baseline, dependency remediation, authentication/authorization verification, CORS/CSRF/header review, input/upload review, logging/audit review, Docker/production-config review, and targeted new tests. No business logic, financial calculations, the 24-hour reading-correction policy, database schema, or role permission grants were changed.

---

## A. Executive summary

The headline finding from Phase 1 — "Starlette 0.47.2 has 12 advisories" — is independently re-verified here and **corrected**: those 12 entries map to **6 distinct CVEs** (each one reported twice because `pip-audit` queries two overlapping advisory databases that both carry it). All 6 are now fixed by upgrading to `fastapi==0.133.1` / `starlette==1.3.1`, the smallest version combination that resolves them (not a jump to the latest `fastapi` 0.163.x). Re-scanning the upgraded image returns **0 known vulnerabilities**, and the full regression suite (230 pre-existing + 18 new security tests = **248 passed, 0 failed**) confirms no breakage. The OpenAPI contract is **byte-for-byte identical** before and after (126 paths / 169 operations, same operation set) — this was a dependency patch, not an API change.

Independent code review (not assumed from documentation) found the existing authentication/authorization implementation to already be substantially sound: real refresh-token rotation **with reuse detection** (a theft signal, not just rotation), constant-shape login responses to prevent account enumeration, password-change session revocation, strict path-param-only tenant resolution (immune to body/query-string tenant spoofing), and JWT algorithm pinning (no algorithm-confusion surface). Two real, low-risk gaps were found and fixed: production had no rejection of a *weak or placeholder* JWT secret (only a *missing* one), and two safe response headers were absent. Both are fixed below. Several items the brief asked about are honestly **not applicable** rather than "fixed" — there is no CSRF token system because the API is bearer-token authenticated (not cookie-authenticated) for every mutating endpoint except `/auth/refresh` and `/auth/logout`, which are protected by `SameSite=Lax` instead.

**No cloud deployment, DNS, or paid service was touched, per the explicit instruction.**

---

## B. Security baseline (before any change)

| Item | Value |
|---|---|
| FastAPI | 0.128.0 |
| Starlette | 0.47.2 |
| Pydantic | 2.10.3 |
| SQLAlchemy | 2.0.36 |
| Python | 3.12.10 |
| Node.js (frontend container) | 22-slim |
| Backend test status | 230 passed, 0 failed (Phase 1, re-verified) |
| Frontend TypeScript | 0 errors |
| Frontend production build | Clean, 16 routes |
| `npm audit` (frontend) | 0 vulnerabilities |
| `pip-audit` (backend) | 12 advisory entries, 1 package (Starlette) — see Section C for the distinct-CVE correction |
| CORS | Config-driven allowlist (`CORS_ALLOWED_ORIGINS`), no wildcard, `allow_credentials=True` |
| Auth architecture | Argon2id password hashing + short-lived (15 min) JWT access token (Bearer header) + rotating refresh token (httpOnly cookie, SHA-256 hash stored, not the raw token) |
| Docs/OpenAPI exposure | Disabled when `ENV=production` (`docs_url`/`redoc_url`/`openapi_url` all `None`) |
| Rate limiting | In-process sliding-window limiter on `/auth/login` (10/5min, keyed by email+IP) and `/auth/register` (5/hour, keyed by IP) — single-instance only, already documented as such |
| Security response headers | `X-Request-ID` only; no `X-Content-Type-Options`, `Referrer-Policy`, CSP, or HSTS |

---

## C. Dependency advisory findings — independently verified, not assumed

Ran `pip-audit -r requirements.txt` (JSON output) against the actual installed environment, not a cached report.

**Correction to the Phase 1 headline number:** "12 advisories" is the raw count of advisory *records* `pip-audit` returned. Deduplicating by CVE, there are **6 distinct vulnerabilities**, every one of them in `starlette==0.47.2` and nowhere else (`fastapi`, `sqlalchemy`, `asyncpg`, `alembic`, `pydantic`, `argon2-cffi`, `pyjwt`, and every other direct/transitive dependency returned zero advisories).

| CVE | Advisory ID | Severity (per advisory) | Affected | Fixed in | Reachable in this app? |
|---|---|---|---|---|---|
| CVE-2025-62727 | PYSEC-2026-1942 | High (CPU-exhaustion DoS via `FileResponse` Range header) | <0.49.1 | 0.49.1 | **No** — this app never uses `StaticFiles` or `FileResponse` (confirmed by repo-wide search); nothing serves files through Starlette's response types |
| CVE-2026-48710 | PYSEC-2026-161 | Medium (Host-header path-confusion, can enable authz bypass in apps that trust `request.url.path`) | <1.0.1 | 1.0.1 | **Logging only** — `request.url.path` is read in exactly 3 places (`app/main.py`'s access-log middleware and the unhandled-exception logger), never for an authorization decision. Every real permission check (`require_permission` in `app/api/deps.py`) uses `request.path_params`, which is resolved by routing against the real path, not reconstructed from the `Host` header |
| CVE-2026-48818 | PYSEC-2026-2281 | High (Windows-only SSRF/NTLM credential leak via `StaticFiles`) | ≤1.0.1 | 1.1.0 | **No** — no `StaticFiles` usage, and the production target is a Linux VPS (`docs/CLOUD_DEPLOYMENT_PLAN.md`), not Windows |
| CVE-2026-48817 | PYSEC-2026-2280 | Medium (arbitrary-method dispatch on unguarded `HTTPEndpoint` routes) | ≤1.0.1 | 1.1.0 | **No** — this app registers every route via FastAPI's function-based `@router.get/post/patch/delete` decorators, never Starlette's class-based `HTTPEndpoint` |
| CVE-2026-54282 | PYSEC-2026-248 | Medium (request-path authority injection, e.g. `@google.com`, can mislead code reading `request.url.hostname`) | <1.3.0 | 1.3.0 | Same as CVE-2026-48710 above — logging only, no authz decision reads `request.url.hostname` |
| CVE-2026-54283 | PYSEC-2026-249 | Medium (urlencoded-form DoS — `max_fields`/`max_part_size` silently unenforced) | <1.3.1 | 1.3.1 | **No** — no endpoint calls `request.form()` on urlencoded bodies (checked by repo-wide search); all input is JSON via Pydantic models or `multipart/form-data` file uploads, which were already unaffected |

**Honest conclusion:** none of the 6 was practically exploitable against this specific application's actual code paths today — but "not currently reachable" is not the same as "safe to leave unpatched," since a future change (adding a file-download endpoint, for example) could make #1 or #3 reachable without anyone remembering this analysis. The upgrade was done regardless, because it was low-risk and free.

**Remediation applied:** `fastapi==0.133.1`, `starlette==1.3.1` (`backend/requirements.txt`). This is the *smallest* FastAPI version that removes its own `starlette<1.0.0` pin (verified directly against PyPI metadata for FastAPI 0.130–0.140 — the pin lifts starting at 0.133.0, not at the latest 0.163.x), so this is a minor dependency bump, not a framework migration. `requirements-dev.txt` only does `-r requirements.txt`, so it stayed automatically consistent — no separate pin to update.

**Post-upgrade re-scan:** `pip-audit` → **"No known vulnerabilities found."**

---

## D. FastAPI/Starlette upgrade — compatibility verification

| Check | Result |
|---|---|
| Pydantic compatibility | `fastapi==0.133.1` requires `pydantic>=2.7.0`; installed `pydantic==2.10.3` already satisfies it. No change needed. |
| SQLAlchemy/middleware compatibility | Unaffected — SQLAlchemy has no dependency relationship with Starlette/FastAPI versions. |
| Python version compatibility | Both versions support Python 3.12 (installed: 3.12.10). No change needed. |
| App import | `Application startup complete` in container logs, no import errors. |
| App startup | Confirmed via container logs: migrations ran, Uvicorn started cleanly. |
| OpenAPI generation | `GET /openapi.json` → HTTP 200, identical path/operation set to before (Section F). |
| Middleware (CORS, request-ID, exception handlers) | Exercised by the full test suite (login/CORS/error-handling tests) — all pass. |
| Authentication | `test_auth.py` (9 tests) + `test_security.py` (6 tests) + 4 new JWT/algorithm tests — all pass. |
| CORS | 2 new explicit tests (allowed origin reflected, disallowed origin not reflected) — pass. |
| Cookies/CSRF | See Section I. |
| Rate limiting | `test_rate_limit.py` (5 tests) — pass, unchanged behavior. |
| Full backend test suite | 248/248 pass (Section G). |

No breaking API changes were required or made. No major-version framework migration was needed — the brief's stop-and-document-a-blocker clause does not apply here.

---

## E. Authentication security — findings (mostly already correct; two real fixes applied)

### Password security
- Argon2id confirmed (`argon2.PasswordHasher()` default profile) — `app/core/security.py`.
- Passwords are hashed before storage; `verify_password` never logs the plaintext or the hash on failure.
- Password-change (`PATCH /auth/password`) requires the current password, then revokes every other active session (`_revoke_all_sessions`) — a leaked-credential replacement can't leave an old session usable.
- No insecure default password exists anywhere in application code (the only "default" credentials anywhere are developer-created via `app/seed.py`, which requires an explicit `--password` argument of at least 10 characters and is never exposed over HTTP).
- **Existing policy, not newly invented:** no minimum-length/complexity rule is enforced on login (login always accepts whatever was set at registration); `app/seed.py`'s CLI enforces ≥10 characters for superuser bootstrap only. **Recommendation (not implemented — would change registration behavior, out of this phase's "no business-workflow changes" scope):** add a minimum password length check to `RegisterRequest`/`ChangePasswordRequest` schemas in a future pass.

### JWT security
- Algorithm is explicitly configured (`settings.jwt_algorithm`, default `HS256`) and **pinned** on decode: `jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])` — the token's own header can never select a different algorithm. Verified with two new tests: an `alg: none` forged token and an HS512-signed token are both rejected.
- Signature is verified (pyjwt's default behavior; never bypassed).
- Expiration is enforced (`exp` claim checked by pyjwt automatically; `test_expired_access_token_is_rejected` confirms).
- No issuer/audience claims exist in the architecture (none configured, so none validated — matches "when configured by the architecture").
- Invalid, expired, and malformed tokens are all rejected (`decode_access_token` catches `jwt.PyJWTError`, `get_current_user` translates it to a 401).
- **Fixed this phase:** `jwt_secret_key` already had no insecure *default* (`str` with no default value — Pydantic Settings refuses to construct at all without it, in any environment). It did **not**, until this phase, reject a *present but weak* secret. Added a `model_validator` (`app/config.py`) that, **in production only**, rejects a secret shorter than 32 characters or matching a list of known placeholder strings (including the literal text shipped in `.env.example`). Development is deliberately exempt so a short local `.env` value still works for `uvicorn --reload`. 5 new tests cover: placeholder rejected, short secret rejected, strong secret accepted, dev tolerates a short secret, and missing secret rejected in any environment.
- JWT secret and full tokens are never logged (`app/main.py`'s access-log middleware logs only method/path/status/duration/client_ip — never headers, never the request body).

### Refresh-token security
- **Rotation:** every `/auth/refresh` call issues a new token and revokes the old one (`stored.revoked_at = ...`, `stored.replaced_by_id = new_token.id`).
- **Reuse detection — actually implemented, not just claimed:** if a refresh token that is already `revoked_at is not None` is presented again, `_revoke_all_sessions` is called for that user and **every** active session is killed, then a 401 is returned. This is real theft-response behavior, confirmed by reading `app/api/auth.py::refresh` and by the existing `test_refresh_rotates_token_and_old_one_cannot_be_reused` test.
- **Logout** revokes the specific refresh token tied to the cookie presented; a logout with no cookie at all is a no-op 204, not an error (new test added).
- **Session invalidation:** `/auth/logout-all` revokes every active session for the account; `/auth/sessions` lists active (non-revoked, non-expired) sessions without ever exposing a token value.
- **Concurrent refresh:** not separately load-tested this phase; the row-level state transition (`revoked_at`, `replaced_by_id`) relies on normal transactional consistency, same pattern already proven under concurrent load for shift state transitions elsewhere in the codebase (`docs/REMAINING_RISKS.md`). Flagged as **not separately verified** for refresh specifically — a real gap to close with a concurrency test in a future pass, not claimed as done here.
- **Storage:** only a SHA-256 hash of the refresh token is stored (`RefreshToken.token_hash`); the raw 48-byte random token is never persisted. A database compromise alone does not yield usable refresh tokens.

### Cookie security
- `httponly=True` always; `secure=settings.is_production` (true only in production, so local HTTP dev still works); `samesite="lax"`; explicit `max_age` and `path=/auth`. Development and production behavior are already correctly separated by the existing `is_production` flag — no change needed.

### Session security — acceptance tests
| Test | Result |
|---|---|
| Valid login succeeds | ✅ pre-existing (`test_login_success_returns_access_token_and_sets_refresh_cookie`) |
| Incorrect password fails | ✅ pre-existing, constant-shape response |
| Expired JWT fails | ✅ pre-existing (`test_me_rejects_expired_token`, `test_expired_access_token_is_rejected`) |
| Invalid signature fails | ✅ pre-existing (`test_tampered_access_token_is_rejected`) |
| Revoked session (reused refresh token) fails | ✅ pre-existing (`test_refresh_rotates_token_and_old_one_cannot_be_reused`) |
| Disabled user fails | ✅ pre-existing (`test_inactive_user_cannot_login`), and re-checked live on every request via `get_current_user` (not just at login) |
| Logout invalidates session | ✅ pre-existing (`test_logout_revokes_refresh_token`) + new no-cookie-logout test |
| Refresh rotation works | ✅ pre-existing |
| Invalid/missing refresh token fails | ✅ new test added (`test_refresh_with_no_cookie_is_rejected`) |
| Production startup rejects missing JWT secret | ✅ new test added |
| Production startup rejects weak/placeholder JWT secret | ✅ new tests added (this phase's fix) |

---

## F. RBAC and multi-tenant security

Existing architecture (unchanged, verified by re-reading `app/api/deps.py::require_permission`): organization/station identity is resolved **only** from the URL's path parameters, via FastAPI's own routing (never the request body, never a query string). A superuser bypasses checks explicitly (`current_user.is_superuser or ...`); everyone else goes through `user_has_permission` scoped to the exact `organization_id`/`station_id` the URL names.

**New tests added this phase** (the existing `test_cross_tenant_isolation.py` already covered list/detail reads and unauthenticated rejection; these add the mutation and export paths the brief specifically asked for):

| Test | What it proves |
|---|---|
| `test_cross_org_update_is_rejected` | A PATCH with the *wrong* organization_id in the URL is denied (403) before the target row is ever queried |
| `test_cross_org_fuel_grade_lookup_is_rejected_even_with_correct_org_in_body` | The classic IDOR check: a row belonging to Org B cannot be edited by addressing it through Org A's URL, even with the correct org_id — the scoped query simply finds nothing (404), it does not leak or silently edit |
| `test_cross_org_role_assignment_delete_is_rejected` | DELETE (role-assignment revocation) is denied across orgs, same as any other mutation |
| `test_cross_org_report_export_is_rejected` | A CSV export endpoint enforces the same org+station scoping as every other endpoint — exports are not a lower-security side door |
| `test_auditor_cannot_approve_an_expense` | The read-only Auditor/Viewer role cannot perform a financial mutation |
| `test_storekeeper_cannot_approve_an_expense` | Storekeeper/Technician (physical-equipment permissions) cannot reach a financial-approval action outside its scope |

Pre-existing tests already covering the brief's other literal acceptance criteria (not duplicated): cashier cannot create a station (`test_cashier_cannot_create_station`), a user with no role in an org is denied (`test_user_with_no_role_in_org_is_denied`), a revoked role assignment loses access immediately (`test_revoked_role_assignment_loses_access_immediately`), organization creation is superuser-only (`test_superuser_only_can_create_organization`).

**No permission grants were changed.** The seven roles (Owner, Station Manager, Shift Supervisor, Cashier/Operator, Accountant, Storekeeper/Technician, Auditor/Viewer) and their permission sets in `app/core/permission_codes.py::SEED_ROLES` are exactly as Phase 1 documented them.

**Background tasks:** this application has none (no Celery/RQ/cron worker) — "background tasks do not bypass tenant scope" is **not applicable**, not silently skipped.

---

## G. Full regression test results (exact)

### Backend — pytest against real PostgreSQL 16, after the dependency upgrade and config/header changes

```
248 passed, 0 failed, 0 skipped, 0 errors
3 warnings (pre-existing, non-fatal Pydantic decimal-serialization warnings in
test_attendance.py — unrelated to this phase, not introduced by it)
Exit code: 0
Duration: 691.36s (11 min 31 sec)
```
230 pre-existing + 18 new (Section E/F/H above). This is the **second** full run against real Postgres this engagement (the first was Phase 1's baseline, also 230/230) — the dependency upgrade introduced zero regressions.

### Frontend — TypeScript and production build (re-verified after backend changes, to confirm no cross-cutting breakage)
```
npx tsc --noEmit  → 0 errors
npm run build     → Compiled successfully, 16/16 routes generated, exit code 0
npm audit --omit=dev → 0 vulnerabilities (unchanged — frontend wasn't touched this phase)
```

### Playwright e2e (existing suite, run against the live docker-compose stack)
```
10 passed, 2 failed (chromium, 18.9s)
```
Both failures are **pre-existing frontend test fragility, unrelated to any Phase 2 change**:
1. `day2-pages.spec.ts` "Tank management page": expects a "No tanks configured" empty-state string that isn't currently shown — the page's actual empty-state copy has likely changed since this test was written, or the seeded e2e data now has tanks. Not a security issue.
2. `day2-pages.spec.ts` "Credit customers page": a Playwright **strict-mode violation** — `getByText("Credit customers")` now matches *two* elements (an `<h1>` and an `<h2>` both containing that text), not zero. A page-structure change made the selector ambiguous, not broken.

Neither failure touches authentication, authorization, CORS, rate limiting, or anything else in this phase's scope. **Flagged as a pre-existing frontend test-maintenance item for a future pass, not fixed here** (fixing frontend test selectors is not a security change and is out of this phase's stated scope).

### OpenAPI contract comparison
```
Before: 126 paths, 169 operations
After:  126 paths, 169 operations
Structural diff of the full (method, path) operation set: IDENTICAL — zero added, zero removed
```

### Business invariants — explicitly re-confirmed intact
- 24-hour reading-correction policy: code unchanged (`app/api/reading_corrections.py` not touched this phase); its existing tests are part of the 248 passing.
- Append-only stock ledger: unchanged.
- Tenant/station isolation: unchanged, and now has 4 additional mutation/export tests proving it (Section F).
- Decimal-based financial calculations: unchanged — no financial code was touched.
- Approval workflows and audit trail: unchanged; `app/core/audit.py` confirmed (by direct code read) to never reference `password`, `token`, or `secret` in any field it writes.
- Historical record protection: unchanged.

---

## H. CORS, CSRF and HTTP security

### CORS
- `allow_origins=settings.cors_origins` — a config-driven list (`CORS_ALLOWED_ORIGINS` env var, comma-separated), never a wildcard. `allow_credentials=True` combined with a wildcard is also structurally impossible here (Starlette/FastAPI reject that combination at the framework level, and this app never sets a wildcard regardless).
- **New tests added:** an allowed origin (`http://localhost:3000`, the configured default) is reflected in `Access-Control-Allow-Origin`; a disallowed origin (`https://evil-attacker.example`) gets no such header at all — both pass.
- Preflight (`OPTIONS`) requests are handled correctly by `CORSMiddleware` automatically; `allow_methods`/`allow_headers` are explicit lists (`GET, POST, PATCH, DELETE` / `Authorization, Content-Type`), not wildcards.
- Development origins do not automatically become production origins — `CORS_ALLOWED_ORIGINS` is a plain environment variable with a dev-only default (`http://localhost:3000`); a real production deployment must set it explicitly (already documented in `docs/CLOUD_DEPLOYMENT_PLAN.md`'s environment-variable table). **Status: requires production infrastructure** to set the real value — not something this local-dev audit can set for a domain that doesn't exist yet.

### CSRF
**Honest characterization, not an overclaim:** this API has no classic CSRF-token (double-submit) mechanism, and **does not need one for most of its surface** — every mutating business endpoint (shifts, tenders, expenses, fuel grades, etc.) authenticates via a `Bearer` token in the `Authorization` header, which a browser never attaches automatically to a cross-site request the way it does a cookie. Classic CSRF requires an *ambient* credential; there isn't one here except for two endpoints:
- `/auth/refresh` and `/auth/logout`, which read the httpOnly refresh cookie. These are protected by `SameSite=Lax`: a cross-site `POST` (the only method these endpoints accept) does not carry a `Lax` cookie at all — only a top-level `GET` navigation does. This is a real, standard, modern mitigation, not a workaround.
- **Tested this phase:** missing-cookie behavior on both endpoints (401 and no-op-204 respectively). **Not separately tested:** a live cross-origin browser request (would require a second origin/browser-automation harness beyond this phase's tooling) — the `SameSite=Lax` mechanism itself is standard browser behavior, not application code, so it is not something this test suite can exercise end-to-end without a real second-origin page. **Status: mitigated by design (SameSite), not independently verified with a live cross-origin request.**

### Security headers
| Header | Status | Where |
|---|---|---|
| `X-Content-Type-Options: nosniff` | **Fixed and verified** (new) | App layer, unconditional, all responses — new test confirms presence |
| `Referrer-Policy: strict-origin-when-cross-origin` | **Fixed and verified** (new) | App layer, unconditional, all responses — new test confirms presence |
| `Strict-Transport-Security` | **Requires production infrastructure** | Deliberately NOT added at the app layer — setting HSTS on a server that might still be reached over plain HTTP (true today; no HTTPS reverse proxy exists yet) would be actively wrong, not just incomplete. Belongs on the Caddy reverse proxy once deployed, per `docs/CLOUD_DEPLOYMENT_PLAN.md`. |
| `Content-Security-Policy` / `frame-ancestors` | **Requires production infrastructure** | Not added — a strict CSP risks breaking Next.js's own inline scripts/styles without real testing against the live frontend build, which this phase did not attempt (out of scope: no frontend changes this phase). Belongs at the reverse-proxy layer, tuned against the actual deployed frontend, not guessed here. |
| `Permissions-Policy` | **Requires production infrastructure** | Same reasoning — not guessed without a concrete feature list to restrict. |

---

## I. Rate limiting and abuse protection

Re-read `app/core/rate_limit.py` directly (not assumed from its own docstring, though the docstring turned out to be accurate):
- In-process `SlidingWindowLimiter`, thread-safe (a `Lock`), keyed by `email:client_ip` for login (10 attempts/5 min) and `client_ip` for registration (5/hour).
- **Honest, unchanged limitation:** this is single-instance only. With more than one backend replica behind a load balancer, each replica has its own independent counter, so an attacker spread across replicas is only partially throttled — this was already correctly documented in `docs/REMAINING_RISKS.md` and `docs/ASSUMPTIONS.md` #30, and remains true. **Not fixed this phase, per explicit instruction not to add Redis or another paid/external service.** Documented here again as a **deployment prerequisite**: before running more than one backend container, this limiter must be replaced with a shared store (Redis `INCR`+TTL is the standard pattern) — not optional, not deferred indefinitely, just correctly out of scope for a PKR 4,000/month single-VPS pilot.
- Login failure responses are constant-shape regardless of whether the email exists (`AuthenticationError("Incorrect email or password.")` in both cases) — does not leak account existence.
- Rate-limit responses are a generic `429` with a generic message (`RateLimitedError`'s default: "Too many attempts. Please wait before trying again.") — no secrets, no internal detail.
- Expensive report endpoints and other sensitive operations have **no additional rate limiting beyond the standard per-request authentication/authorization check** — not flagged as broken (nothing in the existing threat model calls for it), but explicitly **not claimed as protected** either.

---

## J. Input validation, file uploads, and database safety

- Every request body is a Pydantic model (FastAPI's standard behavior) — unexpected fields are ignored by default (Pydantic v2's default `extra="ignore"` unless a schema overrides it), not silently trusted into a dangerous field.
- All SQLAlchemy queries use the ORM's parameterized query builder (`select(...)`, `.where(...)`) — no raw SQL string interpolation was found anywhere in the reviewed code (`app/api/deps.py`, `app/api/auth.py`, `app/api/fuel_grades.py`, `app/api/reports.py`, `app/core/*`). No SQL injection path identified.
- File uploads (`app/core/storage.py`, re-read this phase): real magic-byte content verification (not just the client's `Content-Type` header), chunked reads with an early size-limit abort (never buffers an oversized body into memory first), filename sanitization that strips directory components and unsafe characters (path traversal rejected), and a random UUID-prefixed, organization-scoped storage path (one org cannot overwrite another's files by filename collision).
- **New finding this phase:** `resolve_storage_path()` (the function that would read an uploaded evidence file back) is defined but **called by nothing** — there is currently no API endpoint that serves an uploaded attachment back to any client. This means there is currently **no unauthorized-access attack surface for evidence files** (nothing exposes them), but it is also a real product gap (evidence cannot be viewed through the API at all today) — noted for the product backlog, not a security defect to fix in this pass.
- Error responses never reveal internal paths or stack traces: the global `Exception` handler in `app/main.py` logs the full traceback server-side only and returns a fixed generic message (`"An unexpected error occurred."`) to the client, confirmed unchanged by this phase.
- Financial/inventory safety: no financial or inventory code was touched this phase. Decimal/Numeric usage, append-only stock ledger behavior, existing database constraints, and the 24-hour reading-correction rule are all unchanged (verified by the unchanged line counts/diffs in `app/api/reading_corrections.py`, `app/core/revenue.py`, and related files — none appear in this phase's changed-files list in Section M).

---

## K. Logging, audit, and error handling

- Passwords: never logged anywhere (confirmed by grep across `app/`; the only places a password touches code are `hash_password`/`verify_password`, neither of which logs).
- JWTs/refresh tokens: never logged. The access-log middleware (`app/main.py`) logs only `method`, `path`, `status_code`, `duration_ms`, `client_ip` — it does not log headers at all, so the `Authorization` header and the refresh cookie are never captured by the logging layer in the first place. This is a stronger guarantee than "redaction," since there is nothing to redact.
- Database credentials: never logged (connection string is read once into `Settings`, never passed to a log call).
- Sensitive request headers: not logged at all (see above) — no redaction layer needed because nothing sensitive is captured.
- Error messages in production: generic, no stack traces, no internal paths (Section J).
- Request IDs: every response carries `X-Request-ID` (unchanged, pre-existing), enabling troubleshooting without needing to log anything sensitive.
- Security-relevant events already audited (via `write_audit_log`, confirmed unchanged): failed/successful login is **not** separately audit-logged today (only rate-limiting counts failures; the access log's status code is the only record of a failed login) — **this is a real, honest gap**, not claimed as covered. Already audited: logout-all (`user.logout_all_sessions`), password change (`user.change_password`), self-registration (`organization.self_register`), and every other business mutation across the app (expense approval, fuel-grade changes, etc.) via the existing shared `write_audit_log` pattern. **No duplicate audit records were added** — Phase 2 did not touch `app/core/audit.py` or any of its call sites.

---

## L. Production configuration and Docker

- Both containers already run as non-root (`appuser` backend uid 1000, `node` frontend) — unchanged, re-confirmed by reading both Dockerfiles.
- Secrets (`JWT_SECRET_KEY`, `DATABASE_URL`) are supplied via environment configuration (`.env` file, `env_file:` in compose) — never embedded in either image.
- The **development** `docker-compose.yml` exposes PostgreSQL on `5432:5432` to the host — correct and expected for local development, **not a production configuration** (the separate, not-yet-built `docker-compose.prod.yml` that `docs/CLOUD_DEPLOYMENT_PLAN.md` specifies binds Postgres to `127.0.0.1:5432` only, never `0.0.0.0`). This audit did not create that production compose file — doing so is Phase 11 work, gated on the owner's hosting decision, per the brief's own non-negotiable rule 11.
- Swagger/OpenAPI docs: already disabled when `ENV=production` (`docs_url`/`redoc_url`/`openapi_url` all `None`) — unchanged, re-confirmed.
- Debug mode: FastAPI's own debug flag is never set (defaults off); no `--reload` flag is used in the production `CMD`.
- CORS production origins: config-driven, not hardcoded (Section H) — the actual production domain value is not yet known (no domain purchased), so it cannot be set to a real value yet; this is accurately a **deployment prerequisite**, not something fixable today.
- JWT secret: now mandatory **and** validated for strength/placeholder-rejection in production (Section E — this phase's fix).
- Health/readiness endpoints (`/health`, `/ready`): re-confirmed unchanged — `/health` touches nothing (pure liveness), `/ready` touches only the database connection, neither reveals configuration, secrets, or internal detail in its response body.

**No deployment, DNS change, or public exposure was made or attempted.**

---

## M. Files changed this phase

| File | Change |
|---|---|
| `backend/requirements.txt` | `fastapi==0.128.0` → `0.133.1`; `starlette==0.47.2` → `1.3.1`. No other version changed. |
| `backend/app/config.py` | Added `_reject_weak_production_jwt_secret` model validator: rejects a JWT secret under 32 characters or matching a known placeholder string, **in production only**. No field removed, no default changed, no behavior change in development/test. |
| `backend/app/main.py` | Added two unconditional response headers (`X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`) inside the existing request-logging middleware. No route, middleware ordering, or exception-handling behavior changed. |
| `backend/tests/test_phase2_security.py` | **New file**, 18 tests (Sections E, F, H). Purely additive — no existing test file was modified or deleted. |

**Database migrations: none.** No model, column, or schema change was made this phase — `alembic upgrade head` ran the same pre-existing migration set both before and after (confirmed: the startup log shows "Running database migrations..." completing without creating or modifying anything new).

**Permissions: unchanged.** `SEED_ROLES` and `ALL_PERMISSIONS` in `app/core/permission_codes.py` were read for verification only, never edited.

---

## N. Open issues requiring owner approval or production infrastructure

| Issue | Status |
|---|---|
| Strict-Transport-Security, CSP, `frame-ancestors`, Permissions-Policy headers | **Requires production infrastructure** — belongs on the HTTPS reverse proxy (Caddy), not guessable before that proxy exists and can be tested against |
| Production `CORS_ALLOWED_ORIGINS` set to the real domain | **Requires owner approval** — no domain has been purchased yet (per Phase 1's deployment-blockers list, still true) |
| Distributed (multi-replica) rate limiting | **Still open, by design** — explicitly not built this phase per instruction; a hard prerequisite before running more than one backend container, documented, not silently deferred |
| Local-disk evidence storage durability | **Still open** — unchanged from Phase 1/`docs/REMAINING_RISKS.md`; not security-relevant today only because nothing serves the files back (Section J), but still a real durability gap for a future multi-replica or evidence-viewing feature |
| Migration-on-boot race with >1 replica | **Still open** — unchanged, already documented in `docs/DEPLOYMENT.md`'s production section |
| No idempotency key on pure-create endpoints | **Still open** — unchanged from Phase 1, not touched this phase (would be a business-logic change, out of scope) |
| Minimum password-complexity policy at registration/change | **Requires owner approval** — not implemented; would be a user-facing behavior change to `RegisterRequest`/`ChangePasswordRequest`, deliberately not made without sign-off |
| No audit-log entry for individual failed/successful login attempts | **Still open** — a real, honest gap identified this phase (Section K); not fixed, since adding it is a small but real behavior change better scoped and reviewed on its own rather than folded silently into a dependency-upgrade phase |
| 2 pre-existing Playwright test failures (`day2-pages.spec.ts`) | **Still open, unrelated to this phase** — frontend test-selector/empty-state-text maintenance, not a security issue, not fixed here |
| Concurrent-refresh-request behavior under real load | **Not independently verified** this phase — relies on existing transactional consistency, not separately stress-tested |

---

## O. Final response (per the brief's required format)

### A. Baseline
- FastAPI 0.128.0 / Starlette 0.47.2; 230 backend tests passing (Phase 1); frontend clean; 12 raw advisory entries (6 distinct CVEs) all in Starlette.

### B. Changes
- Files changed: `backend/requirements.txt`, `backend/app/config.py`, `backend/app/main.py`, `backend/tests/test_phase2_security.py` (new).
- Dependencies updated: `fastapi` 0.128.0→0.133.1, `starlette` 0.47.2→1.3.1.
- Security controls improved: production rejects a weak/placeholder JWT secret (previously only rejected a *missing* one); two new unconditional security response headers.
- Database migrations: **none.**

### C. Test results
- Backend: **248 passed, 0 failed, 0 skipped, 0 errors**, exit code 0, duration 691.36s (11m31s).
- Frontend TypeScript: **0 errors.**
- Frontend production build: **success**, 16/16 routes.
- Playwright: **10 passed, 2 failed** (both pre-existing, unrelated to this phase — Section G).
- OpenAPI before/after: **126 paths / 169 operations, identical operation set, zero changes.**

### D. Security status
- **Fixed and verified:** Starlette/FastAPI CVE set (6 distinct, all resolved, re-scanned clean); weak/placeholder JWT secret rejection in production; two security response headers.
- **Mitigated:** CSRF on the two cookie-authenticated endpoints, via `SameSite=Lax` (not a token system, by design — the rest of the API doesn't need one).
- **Not applicable:** background-task tenant scoping (no background tasks exist); algorithm-confusion JWT attacks (already pinned, now also test-covered).
- **Still open:** distributed rate limiting, local-disk evidence storage, migration-on-boot race, missing idempotency keys, no per-login-attempt audit log, 2 unrelated Playwright failures — all explicitly listed in Section N, none hidden.
- **Requires production infrastructure:** HSTS/CSP/frame-ancestors/Permissions-Policy headers, real production CORS origin.
- **Requires owner approval:** password-complexity policy, real domain for CORS.

### E. Business regression
**Confirmed intact.** 24-hour reading-correction policy, append-only stock ledger, Decimal-based financial math, approval workflows, audit trail, and tenant/station isolation are all unchanged in code and all pass their existing tests, plus 4 new tests specifically proving tenant isolation holds for UPDATE/DELETE/export operations (not just reads, which were the only thing previously tested).

### F. Phase 2 verdict

**READY WITH DOCUMENTED LIMITATIONS.**

The critical security-review items this phase targeted (dependency CVEs, JWT/session integrity, cross-tenant mutation/export authorization, CORS allowlist behavior, production secret strength) are fixed and test-verified with real evidence, not assumed. The items still open (Section N) are each honestly categorized — several explicitly require production infrastructure that does not exist yet (no VPS, no domain, no HTTPS proxy) or explicit owner sign-off (password policy, distributed rate limiting's Redis dependency) — not hidden or claimed as done. Nothing in this phase is marked complete without the test run or code read that backs it.
