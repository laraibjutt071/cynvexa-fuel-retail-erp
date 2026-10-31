import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers, login

pytestmark = pytest.mark.asyncio


async def test_create_organization_requires_name(client: AsyncClient, superuser):
    token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    resp = await client.post("/organizations", json={"name": ""}, headers=auth_headers(token))
    assert resp.status_code == 422


async def test_update_organization_partial_fields(client: AsyncClient, owner_user, org):
    token = await login(client, "owner@acmefuel-dev.com")
    resp = await client.patch(
        f"/organizations/{org.id}", json={"is_active": False}, headers=auth_headers(token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_active"] is False
    assert body["name"] == "Acme Fuel Co"  # untouched field preserved


async def test_get_nonexistent_organization_is_404_not_500(client: AsyncClient, superuser):
    token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    import uuid

    resp = await client.get(f"/organizations/{uuid.uuid4()}", headers=auth_headers(token))
    assert resp.status_code == 404
    assert "traceback" not in resp.text.lower()


async def test_station_code_must_be_unique_within_organization(
    client: AsyncClient, owner_user, org
):
    token = await login(client, "owner@acmefuel-dev.com")
    first = await client.post(
        f"/organizations/{org.id}/stations",
        json={"name": "Station A", "code": "DUP"},
        headers=auth_headers(token),
    )
    assert first.status_code == 201

    second = await client.post(
        f"/organizations/{org.id}/stations",
        json={"name": "Station B", "code": "DUP"},
        headers=auth_headers(token),
    )
    assert second.status_code == 409


async def test_station_code_can_repeat_across_different_organizations(
    client: AsyncClient, superuser, owner_user, org
):
    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    create_org_resp = await client.post(
        "/organizations", json={"name": "Second Co"}, headers=auth_headers(admin_token)
    )
    assert create_org_resp.status_code == 201

    owner_token = await login(client, "owner@acmefuel-dev.com")
    resp1 = await client.post(
        f"/organizations/{org.id}/stations",
        json={"name": "Station A", "code": "SAME"},
        headers=auth_headers(owner_token),
    )
    assert resp1.status_code == 201

    # Superuser creating a station directly in the second org (no station role needed: is_superuser bypasses).
    second_org_id = create_org_resp.json()["id"]
    resp2 = await client.post(
        f"/organizations/{second_org_id}/stations",
        json={"name": "Station A", "code": "SAME"},
        headers=auth_headers(admin_token),
    )
    assert resp2.status_code == 201


async def test_station_update_rejects_invalid_timezone_type(client: AsyncClient, owner_user, org, station):
    token = await login(client, "owner@acmefuel-dev.com")
    resp = await client.patch(
        f"/organizations/{org.id}/stations/{station.id}",
        json={"timezone": 12345},
        headers=auth_headers(token),
    )
    assert resp.status_code == 422
