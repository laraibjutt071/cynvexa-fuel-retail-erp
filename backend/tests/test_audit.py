import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers, login

pytestmark = pytest.mark.asyncio


async def test_creating_a_station_writes_an_audit_log_entry(client: AsyncClient, owner_user, org):
    token = await login(client, "owner@acmefuel-dev.com")
    create_resp = await client.post(
        f"/organizations/{org.id}/stations",
        json={"name": "Main Station", "code": "STN-1"},
        headers=auth_headers(token),
    )
    assert create_resp.status_code == 201
    station_id = create_resp.json()["id"]

    audit_resp = await client.get(f"/organizations/{org.id}/audit-log", headers=auth_headers(token))
    assert audit_resp.status_code == 200
    entries = audit_resp.json()
    assert len(entries) == 1
    entry = entries[0]
    assert entry["action"] == "station.create"
    assert entry["entity_type"] == "Station"
    assert entry["entity_id"] == station_id
    assert entry["actor_user_id"] == str(owner_user.id)
    assert entry["after"]["code"] == "STN-1"
    assert entry["before"] is None


async def test_updating_organization_records_before_and_after(client: AsyncClient, owner_user, org):
    token = await login(client, "owner@acmefuel-dev.com")
    await client.patch(
        f"/organizations/{org.id}", json={"name": "Acme Renamed"}, headers=auth_headers(token)
    )

    audit_resp = await client.get(f"/organizations/{org.id}/audit-log", headers=auth_headers(token))
    entry = audit_resp.json()[0]
    assert entry["action"] == "organization.update"
    assert entry["before"]["name"] == "Acme Fuel Co"
    assert entry["after"]["name"] == "Acme Renamed"


async def test_audit_log_requires_audit_read_permission(client: AsyncClient, cashier_user, org):
    token = await login(client, "cashier@acmefuel-dev.com")
    resp = await client.get(f"/organizations/{org.id}/audit-log", headers=auth_headers(token))
    assert resp.status_code == 403


async def test_audit_log_is_isolated_per_organization(
    client: AsyncClient, owner_user, org, other_org, superuser
):
    owner_token = await login(client, "owner@acmefuel-dev.com")
    await client.patch(
        f"/organizations/{org.id}", json={"name": "Acme Renamed"}, headers=auth_headers(owner_token)
    )

    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    other_org_audit = await client.get(
        f"/organizations/{other_org.id}/audit-log", headers=auth_headers(admin_token)
    )
    assert other_org_audit.status_code == 200
    assert other_org_audit.json() == []
