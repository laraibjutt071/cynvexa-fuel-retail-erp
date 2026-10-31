import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers, login

pytestmark = pytest.mark.asyncio


async def test_wrong_current_password_is_rejected(client: AsyncClient, owner_user):
    token = await login(client, "owner@acmefuel-dev.com")
    resp = await client.patch(
        "/auth/password",
        json={"current_password": "totally-wrong", "new_password": "a-new-strong-password-1"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 401


async def test_password_change_revokes_other_sessions_and_new_password_works(
    client: AsyncClient, owner_user
):
    token = await login(client, "owner@acmefuel-dev.com")

    # A second, independent login - simulates a second device/browser.
    second_login = await client.post(
        "/auth/login",
        json={"email": "owner@acmefuel-dev.com", "password": "a-strong-password-123"},
    )
    assert second_login.status_code == 200
    other_session_refresh_cookie = second_login.cookies["refresh_token"]

    change_resp = await client.patch(
        "/auth/password",
        json={
            "current_password": "a-strong-password-123",
            "new_password": "a-new-strong-password-1",
        },
        headers=auth_headers(token),
    )
    assert change_resp.status_code == 204

    # The old password no longer works.
    old_login = await client.post(
        "/auth/login",
        json={"email": "owner@acmefuel-dev.com", "password": "a-strong-password-123"},
    )
    assert old_login.status_code == 401

    # The new password works.
    new_login = await client.post(
        "/auth/login",
        json={"email": "owner@acmefuel-dev.com", "password": "a-new-strong-password-1"},
    )
    assert new_login.status_code == 200

    # The OTHER session's refresh token (the "second device"), issued before
    # the password change, must now be revoked.
    client.cookies.set("refresh_token", other_session_refresh_cookie)
    other_refresh_resp = await client.post("/auth/refresh")
    assert other_refresh_resp.status_code == 401


async def test_list_sessions_and_logout_all(client: AsyncClient, owner_user):
    token = await login(client, "owner@acmefuel-dev.com")
    second_login = await client.post(
        "/auth/login",
        json={"email": "owner@acmefuel-dev.com", "password": "a-strong-password-123"},
    )
    other_session_refresh_cookie = second_login.cookies["refresh_token"]

    sessions_resp = await client.get("/auth/sessions", headers=auth_headers(token))
    assert sessions_resp.status_code == 200
    assert len(sessions_resp.json()) == 2
    for session in sessions_resp.json():
        assert "token_hash" not in session and "token" not in session

    logout_all_resp = await client.post("/auth/logout-all", headers=auth_headers(token))
    assert logout_all_resp.status_code == 204

    client.cookies.set("refresh_token", other_session_refresh_cookie)
    refresh_resp = await client.post("/auth/refresh")
    assert refresh_resp.status_code == 401


async def test_sessions_endpoint_requires_authentication(client: AsyncClient):
    resp = await client.get("/auth/sessions")
    assert resp.status_code == 401
