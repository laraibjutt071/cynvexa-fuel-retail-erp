import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from httpx import AsyncClient

from app.config import get_settings
from tests.conftest import auth_headers, login

settings = get_settings()

pytestmark = pytest.mark.asyncio


async def test_login_success_returns_access_token_and_sets_refresh_cookie(
    client: AsyncClient, owner_user
):
    resp = await client.post(
        "/auth/login", json={"email": "owner@acmefuel-dev.com", "password": "a-strong-password-123"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) > 20
    assert "refresh_token" in resp.cookies


async def test_login_wrong_password_rejected_with_safe_error(client: AsyncClient, owner_user):
    resp = await client.post(
        "/auth/login", json={"email": "owner@acmefuel-dev.com", "password": "wrong-password"}
    )
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Incorrect email or password."}


async def test_login_unknown_email_gives_same_error_as_wrong_password(client: AsyncClient):
    resp = await client.post(
        "/auth/login", json={"email": "nobody@acmefuel-dev.com", "password": "whatever-123"}
    )
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Incorrect email or password."}


async def test_me_requires_authentication(client: AsyncClient):
    resp = await client.get("/auth/me")
    assert resp.status_code == 401


async def test_me_rejects_expired_token(client: AsyncClient, owner_user):
    now = datetime.now(timezone.utc)
    expired = jwt.encode(
        {
            "sub": str(owner_user.id),
            "type": "access",
            "iat": now - timedelta(minutes=30),
            "exp": now - timedelta(minutes=1),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    resp = await client.get("/auth/me", headers=auth_headers(expired))
    assert resp.status_code == 401
    assert "traceback" not in resp.text.lower()


async def test_me_returns_station_roles(client: AsyncClient, owner_user, org):
    token = await login(client, "owner@acmefuel-dev.com")
    resp = await client.get("/auth/me", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "owner@acmefuel-dev.com"
    assert len(body["station_roles"]) == 1
    assert body["station_roles"][0]["role_name"] == "Owner"
    assert str(org.id) == body["station_roles"][0]["organization_id"]


async def test_refresh_rotates_token_and_old_one_cannot_be_reused(client: AsyncClient, owner_user):
    login_resp = await client.post(
        "/auth/login", json={"email": "owner@acmefuel-dev.com", "password": "a-strong-password-123"}
    )
    old_refresh_cookie = login_resp.cookies["refresh_token"]

    refresh_resp = await client.post("/auth/refresh")
    assert refresh_resp.status_code == 200
    assert "access_token" in refresh_resp.json()

    # Force the OLD (now-rotated) refresh cookie back and try to reuse it.
    client.cookies.set("refresh_token", old_refresh_cookie)
    reuse_resp = await client.post("/auth/refresh")
    assert reuse_resp.status_code == 401


async def test_logout_revokes_refresh_token(client: AsyncClient, owner_user):
    await client.post(
        "/auth/login", json={"email": "owner@acmefuel-dev.com", "password": "a-strong-password-123"}
    )
    logout_resp = await client.post("/auth/logout")
    assert logout_resp.status_code == 204

    refresh_resp = await client.post("/auth/refresh")
    assert refresh_resp.status_code == 401


async def test_inactive_user_cannot_login(client: AsyncClient, owner_user, db):
    owner_user.is_active = False
    db.add(owner_user)
    await db.commit()

    resp = await client.post(
        "/auth/login", json={"email": "owner@acmefuel-dev.com", "password": "a-strong-password-123"}
    )
    assert resp.status_code == 401
