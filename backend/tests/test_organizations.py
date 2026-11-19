import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import auth_headers, login

pytestmark = pytest.mark.asyncio


async def test_create_organization_requires_name(client: AsyncClient, superuser):
    token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    resp = await client.post("/organizations", json={"name": ""}, headers=auth_headers(token))
    assert resp.status_code == 422


async def test_update_organization_partial_fields(client: AsyncClient, owner_user, org):
    token = await login(client, "owner@acmefuel-dev.com")
    resp = await client.patch(
        f"/organizations/{org.id}", json={"legal_name": "Acme Fuel Co Pvt Ltd"}, headers=auth_headers(token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["legal_name"] == "Acme Fuel Co Pvt Ltd"
    assert body["name"] == "Acme Fuel Co"  # untouched field preserved


async def test_owner_cannot_suspend_their_own_organization(client: AsyncClient, owner_user, org):
    """Suspending/reactivating a tenant is a platform-admin action - an
    Owner holds organization:update for their own profile fields, but
    is_active specifically is reserved for require_superuser."""
    token = await login(client, "owner@acmefuel-dev.com")
    resp = await client.patch(
        f"/organizations/{org.id}", json={"is_active": False}, headers=auth_headers(token)
    )
    assert resp.status_code == 403


async def test_superuser_can_suspend_and_reactivate_organization(client: AsyncClient, superuser, org):
    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    suspend = await client.patch(
        f"/organizations/{org.id}", json={"is_active": False}, headers=auth_headers(admin_token)
    )
    assert suspend.status_code == 200
    assert suspend.json()["is_active"] is False

    reactivate = await client.patch(
        f"/organizations/{org.id}", json={"is_active": True}, headers=auth_headers(admin_token)
    )
    assert reactivate.status_code == 200
    assert reactivate.json()["is_active"] is True


async def test_suspended_organization_blocks_member_access(client: AsyncClient, superuser, owner_user, org, station):
    """The suspension must actually block access, not just sit unread in
    the database - a real tenant-level kill switch, not a decorative flag."""
    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    suspend = await client.patch(
        f"/organizations/{org.id}", json={"is_active": False}, headers=auth_headers(admin_token)
    )
    assert suspend.status_code == 200

    owner_token = await login(client, "owner@acmefuel-dev.com")
    blocked = await client.get(
        f"/organizations/{org.id}/stations/{station.id}", headers=auth_headers(owner_token)
    )
    assert blocked.status_code == 403

    # A superuser is exempt, so the org can still be inspected/reactivated while suspended.
    still_visible = await client.get(f"/organizations/{org.id}", headers=auth_headers(admin_token))
    assert still_visible.status_code == 200

    reactivate = await client.patch(
        f"/organizations/{org.id}", json={"is_active": True}, headers=auth_headers(admin_token)
    )
    assert reactivate.status_code == 200

    unblocked = await client.get(
        f"/organizations/{org.id}/stations/{station.id}", headers=auth_headers(owner_token)
    )
    assert unblocked.status_code == 200


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
    client: AsyncClient, db: AsyncSession, superuser, owner_user, org, seeded_roles
):
    """Phase 5b: a bare superuser with no tenant role can no longer create
    a station directly (require_permission's is_superuser bypass is gone
    for tenant business-data writes) - so the second organization is
    onboarded with its own real owner via the platform onboarding flow,
    and that owner creates the station, same as any other tenant."""
    from app.models.plan import Plan

    db.add(
        Plan(
            code="starter", name="Starter", price_monthly="15000.00", price_annual="150000.00",
            max_stations=1, max_users=5,
        )
    )
    await db.commit()

    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    create_org_resp = await client.post(
        "/platform/organizations",
        json={
            "company_name": "Second Co",
            "owner_full_name": "Second Owner",
            "owner_email": "secondowner@secondco-dev.com",
            "owner_password": "a-strong-password-123",
        },
        headers=auth_headers(admin_token),
    )
    assert create_org_resp.status_code == 201

    owner_token = await login(client, "owner@acmefuel-dev.com")
    resp1 = await client.post(
        f"/organizations/{org.id}/stations",
        json={"name": "Station A", "code": "SAME"},
        headers=auth_headers(owner_token),
    )
    assert resp1.status_code == 201

    second_owner_token = await login(client, "secondowner@secondco-dev.com")
    second_org_id = create_org_resp.json()["organization_id"]
    resp2 = await client.post(
        f"/organizations/{second_org_id}/stations",
        json={"name": "Station A", "code": "SAME"},
        headers=auth_headers(second_owner_token),
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
