"""
Phase 2 security hardening tests - CYNVEXA security report.

These are additive to the existing auth/rate-limit/cross-tenant test
files (test_auth.py, test_security.py, test_rate_limit.py,
test_cross_tenant_isolation.py, test_rbac.py), which already cover login
success/failure, expired/tampered tokens, refresh rotation + reuse
detection, inactive-user rejection, rate limiting, and cross-org read
denial. This file adds what Phase 2's audit found was NOT yet covered:

- Production refuses a missing/weak/placeholder JWT secret (app/config.py)
- CORS rejects an origin that isn't on the configured allowlist
- Cross-org UPDATE, DELETE and report-export are rejected, not just reads
- /auth/refresh with no refresh-token cookie at all is rejected
- The two new unconditional security response headers are present
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from tests.conftest import auth_headers, login


# ---------------------------------------------------------------------------
# JWT algorithm confusion: decode_access_token must only ever accept the
# one configured algorithm, never whatever the token itself claims.
# ---------------------------------------------------------------------------


def test_unsigned_alg_none_token_is_rejected():
    from app.config import get_settings
    from app.core.security import decode_access_token

    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(uuid.uuid4()),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }
    # pyjwt refuses to encode with alg="none" unless explicitly told the
    # key may be empty - this crafts the classic "alg: none" bypass token
    # by hand to prove decode_access_token (which pins
    # algorithms=[settings.jwt_algorithm], never trusting the token's own
    # header) rejects it outright.
    forged = jwt.encode(payload, key=None, algorithm="none")
    with pytest.raises(jwt.PyJWTError):
        decode_access_token(forged)
    assert settings.jwt_algorithm != "none"


def test_token_signed_with_a_different_algorithm_is_rejected():
    from app.config import get_settings
    from app.core.security import decode_access_token

    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(uuid.uuid4()),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=15),
    }
    # Same secret, same claims, wrong algorithm header (HS512 instead of
    # the configured HS256) - decode_access_token must reject this rather
    # than auto-detecting the algorithm from the token.
    other_alg = "HS512" if settings.jwt_algorithm != "HS512" else "HS384"
    forged = jwt.encode(payload, settings.jwt_secret_key, algorithm=other_alg)
    with pytest.raises(jwt.PyJWTError):
        decode_access_token(forged)


# ---------------------------------------------------------------------------
# Production config: weak/missing/placeholder JWT secret must be rejected
# ---------------------------------------------------------------------------


def _build_settings(**overrides):
    """Constructs a fresh Settings() with the given env vars applied just
    for this call, bypassing the process-wide os.environ that conftest.py
    already set (JWT_SECRET_KEY, ENV=test) and the get_settings() lru_cache
    singleton - this test exercises the validator directly, not the
    cached app-wide settings object."""
    from app.config import Settings

    env_backup = {k: os.environ.get(k) for k in overrides}
    os.environ.update({k: str(v) for k, v in overrides.items()})
    try:
        return Settings()
    finally:
        for k, v in env_backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_production_rejects_known_placeholder_jwt_secret():
    with pytest.raises(ValidationError, match="placeholder"):
        _build_settings(
            ENV="production",
            JWT_SECRET_KEY="replace-with-a-generated-secret-never-commit-this",
        )


def test_production_rejects_short_jwt_secret():
    with pytest.raises(ValidationError, match="at least 32 characters"):
        _build_settings(ENV="production", JWT_SECRET_KEY="too-short")


def test_production_accepts_a_real_strong_secret():
    settings = _build_settings(
        ENV="production",
        JWT_SECRET_KEY="a-genuinely-long-randomly-generated-secret-value-1234567890",
    )
    assert settings.env == "production"


def test_development_tolerates_a_short_secret():
    """The weak-secret check is production-only by design - a short secret
    in a local dev .env must not block `uvicorn --reload` from starting."""
    settings = _build_settings(ENV="development", JWT_SECRET_KEY="dev-only")
    assert settings.jwt_secret_key == "dev-only"


def test_missing_jwt_secret_key_is_rejected_in_any_environment():
    """jwt_secret_key has no default - Settings() must fail to construct
    at all if it's absent, in every environment, not just production."""
    from app.config import Settings

    backup = os.environ.pop("JWT_SECRET_KEY", None)
    try:
        with pytest.raises(ValidationError):
            Settings(_env_file=None)
    finally:
        if backup is not None:
            os.environ["JWT_SECRET_KEY"] = backup


# ---------------------------------------------------------------------------
# CORS: only the configured origin is reflected back
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cors_reflects_the_configured_allowed_origin():
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.options(
            "/auth/login",
            headers={
                "Origin": "http://localhost:3000",  # matches settings.cors_allowed_origins default
                "Access-Control-Request-Method": "POST",
            },
        )
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"


@pytest.mark.asyncio
async def test_cors_does_not_reflect_an_unapproved_origin():
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.options(
            "/auth/login",
            headers={
                "Origin": "https://evil-attacker.example",
                "Access-Control-Request-Method": "POST",
            },
        )
    # Starlette's CORSMiddleware does not add CORS headers for a
    # disallowed origin - the request isn't blocked at the HTTP level (no
    # mechanism can stop a non-browser client from sending it), but a real
    # browser enforcing CORS will refuse to expose the response to
    # attacker-controlled JS without this header.
    assert "access-control-allow-origin" not in {k.lower() for k in resp.headers}


# ---------------------------------------------------------------------------
# Unconditional security response headers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_security_headers_present_on_every_response(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    assert "x-request-id" in {k.lower() for k in resp.headers}


# ---------------------------------------------------------------------------
# /auth/refresh and /auth/logout with no cookie at all
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_with_no_cookie_is_rejected(client: AsyncClient):
    resp = await client.post("/auth/refresh")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_logout_with_no_cookie_does_not_error(client: AsyncClient):
    """Logging out with no active session is a no-op, not an error - a
    double-logout (e.g. two tabs) must not surface a 401/500 to the user."""
    resp = await client.post("/auth/logout")
    assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Cross-tenant: UPDATE, DELETE and report-export must be rejected,
# not just list/detail reads (those are already covered by
# test_cross_tenant_isolation.py).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_org_update_is_rejected(client, owner_user, other_org, fuel_grade):
    """owner_user's role is in `org`; `fuel_grade` also belongs to `org`.
    Using owner_user's token but *other_org*'s id in the URL must be
    denied before the fuel grade is ever looked up - organization_id in
    the path is the only tenant signal `require_permission` trusts."""
    token = await login(client, owner_user.email)
    resp = await client.patch(
        f"/organizations/{other_org.id}/fuel-grades/{fuel_grade.id}",
        json={"name": "Hacked Name"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_cross_org_fuel_grade_lookup_is_rejected_even_with_correct_org_in_body(
    client, owner_user, org, other_org, db
):
    """A second organization's fuel grade must not be reachable even when
    the *path* correctly says `org` - i.e. a fuel_grade_id belonging to
    `other_org` cannot be edited by addressing it through `org`'s URL.
    This is the IDOR check: an ID alone, without matching organization_id,
    must never resolve to another tenant's row."""
    from app.models.fuel_grade import FuelGrade

    other_grade = FuelGrade(organization_id=other_org.id, name="Diesel (Other Org)", code="D1")
    db.add(other_grade)
    await db.commit()
    await db.refresh(other_grade)

    token = await login(client, owner_user.email)
    resp = await client.patch(
        f"/organizations/{org.id}/fuel-grades/{other_grade.id}",
        json={"name": "Hacked Name"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 404  # scoped query finds nothing - not a leak, not a silent edit


@pytest.mark.asyncio
async def test_cross_org_role_assignment_delete_is_rejected(
    client, owner_user, other_org, station_manager_user, db, seeded_roles
):
    """DELETE .../users/{user_id}/roles/{assignment_id} must be denied
    when called with the wrong organization in the URL, same as every
    other mutating endpoint."""
    from sqlalchemy import select

    from app.models.user_station_role import UserStationRole

    assignment = (
        await db.execute(
            select(UserStationRole).where(UserStationRole.user_id == station_manager_user.id)
        )
    ).scalar_one()

    token = await login(client, owner_user.email)
    resp = await client.delete(
        f"/organizations/{other_org.id}/users/{station_manager_user.id}/roles/{assignment.id}",
        headers=auth_headers(token),
    )
    assert resp.status_code == 403


async def _create_user_with_role(db, org, role, email: str):
    from app.core.security import hash_password
    from app.models.user import User
    from app.models.user_station_role import UserStationRole

    user = User(email=email, full_name="Test User", hashed_password=hash_password("a-strong-password-123"))
    db.add(user)
    await db.flush()
    db.add(UserStationRole(user_id=user.id, organization_id=org.id, station_id=None, role_id=role.id))
    await db.commit()
    return user


@pytest.mark.asyncio
async def test_auditor_cannot_approve_an_expense(client, db, org, seeded_roles):
    """Auditor / Viewer is read-only by seed definition - it must not be
    able to approve (or create) an expense, a financial mutation."""
    from app.models.expense import Expense

    import datetime as _dt

    auditor = await _create_user_with_role(db, org, seeded_roles["Auditor / Viewer"], "auditor@acmefuel-dev.com")
    expense = Expense(
        organization_id=org.id,
        category="Fuel pump repair",
        description="test",
        amount="100.00",
        expense_date=_dt.date.today(),
        created_by_user_id=auditor.id,
    )
    db.add(expense)
    await db.commit()
    await db.refresh(expense)

    token = await login(client, auditor.email)
    resp = await client.patch(
        f"/organizations/{org.id}/expenses/{expense.id}/approve", headers=auth_headers(token)
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_storekeeper_cannot_approve_an_expense(client, db, org, seeded_roles):
    """Storekeeper/Technician holds physical-equipment and inventory
    permissions, not financial approval authority - approving an expense
    is an Owner/Station Manager/Accountant action it must not reach."""
    from app.models.expense import Expense

    import datetime as _dt

    storekeeper = await _create_user_with_role(
        db, org, seeded_roles["Storekeeper / Technician"], "storekeeper@acmefuel-dev.com"
    )
    expense = Expense(
        organization_id=org.id,
        category="Fuel pump repair",
        description="test",
        amount="100.00",
        expense_date=_dt.date.today(),
        created_by_user_id=storekeeper.id,
    )
    db.add(expense)
    await db.commit()
    await db.refresh(expense)

    token = await login(client, storekeeper.email)
    resp = await client.patch(
        f"/organizations/{org.id}/expenses/{expense.id}/approve", headers=auth_headers(token)
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_cross_org_report_export_is_rejected(client, owner_user, other_org, station):
    """A report export endpoint must enforce the same organization+station
    scoping as every other endpoint - exports are not a lower-security
    side door."""
    token = await login(client, owner_user.email)
    resp = await client.get(
        f"/organizations/{other_org.id}/stations/{station.id}/reports/daily-fuel-sales/export",
        params={"date_from": "2026-01-01", "date_to": "2026-01-31"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 403
