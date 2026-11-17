import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user_station_role import UserStationRole
from tests.conftest import auth_headers, login

pytestmark = pytest.mark.asyncio


async def _seed_starter_plan(db: AsyncSession) -> None:
    db.add(
        Plan(
            code="starter",
            name="Starter",
            price_monthly="15000.00",
            price_annual="150000.00",
            max_stations=1,
            max_users=5,
        )
    )
    await db.commit()


async def test_platform_onboarding_creates_full_tenant(client: AsyncClient, db: AsyncSession, superuser, seeded_roles):
    await _seed_starter_plan(db)
    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")

    resp = await client.post(
        "/platform/organizations",
        json={
            "company_name": "Karachi Fuel Hub",
            "owner_full_name": "Bilal Ahmed",
            "owner_email": "bilal@karachifuel-dev.com",
            "owner_password": "a-strong-password-123",
            "phone": "+92-300-1234567",
            "city": "Karachi",
            "country": "Pakistan",
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    org_id = body["organization_id"]

    # The onboarding admin never gets logged in as the new owner.
    assert "access_token" not in body

    # The owner account is real and can sign in independently.
    owner_token = await login(client, "bilal@karachifuel-dev.com")
    me = await client.get("/auth/me", headers=auth_headers(owner_token))
    roles = [r for r in me.json()["station_roles"] if r["organization_id"] == org_id]
    assert len(roles) == 1
    assert roles[0]["role_name"] == "Owner"
    assert roles[0]["station_id"] is None

    org = (await db.execute(select(Organization).where(Organization.id == org_id))).scalar_one()
    assert org.city == "Karachi"
    assert org.country == "Pakistan"

    sub = (await db.execute(select(Subscription).where(Subscription.organization_id == org_id))).scalar_one()
    assert sub.status.value == "trial"


async def test_platform_onboarding_rejects_duplicate_owner_email(
    client: AsyncClient, db: AsyncSession, superuser, owner_user, seeded_roles
):
    await _seed_starter_plan(db)
    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    resp = await client.post(
        "/platform/organizations",
        json={
            "company_name": "Second Co",
            "owner_full_name": "Someone",
            "owner_email": owner_user.email,
            "owner_password": "a-strong-password-123",
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 409


async def test_tenant_owner_cannot_call_platform_onboarding(client: AsyncClient, owner_user, seeded_roles):
    owner_token = await login(client, owner_user.email)
    resp = await client.post(
        "/platform/organizations",
        json={
            "company_name": "Should Not Work",
            "owner_full_name": "Someone",
            "owner_email": "shouldnotwork@example-dev.com",
            "owner_password": "a-strong-password-123",
        },
        headers=auth_headers(owner_token),
    )
    assert resp.status_code == 403


async def test_tenant_owner_cannot_access_platform_stats_or_audit_log(client: AsyncClient, owner_user, seeded_roles):
    owner_token = await login(client, owner_user.email)
    stats_resp = await client.get("/platform/stats", headers=auth_headers(owner_token))
    assert stats_resp.status_code == 403
    audit_resp = await client.get("/platform/audit-log", headers=auth_headers(owner_token))
    assert audit_resp.status_code == 403


async def test_platform_stats_reflect_real_counts(
    client: AsyncClient, db: AsyncSession, superuser, owner_user, org, seeded_roles
):
    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    resp = await client.get("/platform/stats", headers=auth_headers(admin_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_organizations"] >= 1
    assert body["active_organizations"] >= 1
    assert body["suspended_organizations"] == body["total_organizations"] - body["active_organizations"]
    assert body["total_owners"] >= 1
    assert any(o["id"] == str(org.id) for o in body["recent_organizations"])


async def test_platform_stats_reflect_suspension(client: AsyncClient, db: AsyncSession, superuser, org, seeded_roles):
    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    before = (await client.get("/platform/stats", headers=auth_headers(admin_token))).json()

    suspend = await client.patch(f"/organizations/{org.id}", json={"is_active": False}, headers=auth_headers(admin_token))
    assert suspend.status_code == 200

    after = (await client.get("/platform/stats", headers=auth_headers(admin_token))).json()
    assert after["suspended_organizations"] == before["suspended_organizations"] + 1
    assert after["active_organizations"] == before["active_organizations"] - 1


async def test_organization_search_and_status_filter(client: AsyncClient, db: AsyncSession, superuser, seeded_roles):
    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    db.add(Organization(name="Lahore Petrol Point"))
    db.add(Organization(name="Multan Fuel Depot"))
    await db.commit()

    search = await client.get("/organizations?q=Lahore", headers=auth_headers(admin_token))
    assert search.status_code == 200
    names = [o["name"] for o in search.json()]
    assert names == ["Lahore Petrol Point"]

    status_filter = await client.get("/organizations?status=active", headers=auth_headers(admin_token))
    assert status_filter.status_code == 200
    assert all(o["is_active"] for o in status_filter.json())


async def test_platform_audit_log_spans_every_organization(
    client: AsyncClient, db: AsyncSession, superuser, seeded_roles
):
    await _seed_starter_plan(db)
    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    await client.post(
        "/platform/organizations",
        json={
            "company_name": "Peshawar Fuel Co",
            "owner_full_name": "Owner X",
            "owner_email": "ownerx@peshawarfuel-dev.com",
            "owner_password": "a-strong-password-123",
        },
        headers=auth_headers(admin_token),
    )
    resp = await client.get("/platform/audit-log", headers=auth_headers(admin_token))
    assert resp.status_code == 200
    actions = [e["action"] for e in resp.json()]
    assert "organization.onboard_by_platform_admin" in actions


async def test_user_create_payload_cannot_set_is_superuser(
    client: AsyncClient, db: AsyncSession, owner_user, org, seeded_roles
):
    """A tenant owner creating a staff account has no field to request
    platform-admin privileges for them - UserCreate simply has no
    is_superuser field, so sending one is silently ignored, not honored."""
    owner_token = await login(client, owner_user.email)
    resp = await client.post(
        f"/organizations/{org.id}/users",
        json={
            "email": "newstaff@acmefuel-dev.com",
            "full_name": "New Staff",
            "password": "a-strong-password-123",
            "is_superuser": True,
        },
        headers=auth_headers(owner_token),
    )
    assert resp.status_code == 201
    from app.models.user import User as UserModel

    created = (await db.execute(select(UserModel).where(UserModel.email == "newstaff@acmefuel-dev.com"))).scalar_one()
    assert created.is_superuser is False
