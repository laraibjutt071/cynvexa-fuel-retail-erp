import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user_station_role import UserStationRole
from tests.conftest import auth_headers

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


async def test_self_registration_creates_org_station_owner_and_trial_subscription(
    client: AsyncClient, db: AsyncSession, seeded_roles
):
    await _seed_starter_plan(db)

    resp = await client.post(
        "/auth/register",
        json={
            "company_name": "Khan Fuel Station",
            "station_name": "Main Station",
            "full_name": "Ahmed Khan",
            "email": "ahmed@khanfuel-dev.com",
            "password": "a-strong-password-123",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert "access_token" in body
    org_id = body["organization_id"]
    station_id = body["station_id"]

    # The caller is immediately signed in and can use the token.
    me_resp = await client.get("/auth/me", headers=auth_headers(body["access_token"]))
    assert me_resp.status_code == 200
    me = me_resp.json()
    roles = [r for r in me["station_roles"] if r["organization_id"] == org_id]
    assert len(roles) == 1
    assert roles[0]["role_name"] == "Owner"
    assert roles[0]["station_id"] is None  # org-wide, not station-scoped

    # The organization, station, and role assignment are real rows.
    org = (await db.execute(select(Organization).where(Organization.id == org_id))).scalar_one()
    assert org.name == "Khan Fuel Station"
    assignment = (
        await db.execute(select(UserStationRole).where(UserStationRole.organization_id == org_id))
    ).scalar_one()
    assert assignment.station_id is None

    # A trial subscription on the requested (default) plan exists.
    sub = (await db.execute(select(Subscription).where(Subscription.organization_id == org_id))).scalar_one()
    assert sub.status.value == "trial"

    # They can immediately use their new station.
    station_resp = await client.get(
        f"/organizations/{org_id}/stations/{station_id}", headers=auth_headers(body["access_token"])
    )
    assert station_resp.status_code == 200


async def test_registering_with_an_already_used_email_is_rejected(
    client: AsyncClient, db: AsyncSession, seeded_roles
):
    await _seed_starter_plan(db)
    payload = {
        "company_name": "Co A",
        "full_name": "Person A",
        "email": "dup@khanfuel-dev.com",
        "password": "a-strong-password-123",
    }
    first = await client.post("/auth/register", json=payload)
    assert first.status_code == 201

    second = await client.post(
        "/auth/register",
        json={**payload, "company_name": "Co B", "full_name": "Person B"},
    )
    assert second.status_code == 409


async def test_registering_without_any_seeded_plan_fails_cleanly(client: AsyncClient, seeded_roles):
    # No plan seeded at all in this test - the endpoint must not crash, it
    # must report a real, honest "not set up yet" error.
    resp = await client.post(
        "/auth/register",
        json={
            "company_name": "No Plan Co",
            "full_name": "Someone",
            "email": "noplan@khanfuel-dev.com",
            "password": "a-strong-password-123",
        },
    )
    assert resp.status_code == 503


async def test_two_self_registered_organizations_cannot_see_each_others_data(
    client: AsyncClient, db: AsyncSession, seeded_roles
):
    await _seed_starter_plan(db)
    resp_a = await client.post(
        "/auth/register",
        json={
            "company_name": "Org A Fuel",
            "full_name": "Owner A",
            "email": "ownera@khanfuel-dev.com",
            "password": "a-strong-password-123",
        },
    )
    resp_b = await client.post(
        "/auth/register",
        json={
            "company_name": "Org B Fuel",
            "full_name": "Owner B",
            "email": "ownerb@khanfuel-dev.com",
            "password": "a-strong-password-123",
        },
    )
    org_a = resp_a.json()["organization_id"]
    token_b = resp_b.json()["access_token"]

    resp = await client.get(f"/organizations/{org_a}", headers=auth_headers(token_b))
    assert resp.status_code == 403
