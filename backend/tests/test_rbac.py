import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.station import Station
from app.models.user_station_role import UserStationRole
from tests.conftest import auth_headers, login

pytestmark = pytest.mark.asyncio


async def test_owner_can_create_and_read_station(client: AsyncClient, owner_user, org):
    token = await login(client, "owner@acmefuel-dev.com")
    create_resp = await client.post(
        f"/organizations/{org.id}/stations",
        json={"name": "Main Station", "code": "STN-1"},
        headers=auth_headers(token),
    )
    assert create_resp.status_code == 201, create_resp.text

    list_resp = await client.get(f"/organizations/{org.id}/stations", headers=auth_headers(token))
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


async def test_cashier_cannot_create_station(client: AsyncClient, cashier_user, org):
    token = await login(client, "cashier@acmefuel-dev.com")
    resp = await client.post(
        f"/organizations/{org.id}/stations",
        json={"name": "New Station", "code": "STN-2"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 403
    assert resp.json() == {"detail": "You do not have permission to perform this action."}


async def test_user_with_no_role_in_org_is_denied(client: AsyncClient, owner_user, other_org):
    """owner_user has a role in `org`, not in `other_org` -> must be denied, not merely hidden."""
    token = await login(client, "owner@acmefuel-dev.com")
    resp = await client.get(f"/organizations/{other_org.id}", headers=auth_headers(token))
    assert resp.status_code == 403


async def test_cashier_scoped_to_one_station_cannot_read_a_different_station(
    client: AsyncClient, cashier_user, org, station, db
):
    other_station = Station(organization_id=org.id, name="Second Station", code="STN-2")
    db.add(other_station)
    await db.commit()
    await db.refresh(other_station)

    token = await login(client, "cashier@acmefuel-dev.com")

    own_station_resp = await client.get(
        f"/organizations/{org.id}/stations/{station.id}", headers=auth_headers(token)
    )
    assert own_station_resp.status_code == 200

    other_station_resp = await client.get(
        f"/organizations/{org.id}/stations/{other_station.id}", headers=auth_headers(token)
    )
    assert other_station_resp.status_code == 403


async def test_org_wide_role_can_read_every_station_in_its_org(
    client: AsyncClient, owner_user, org, db
):
    s1 = Station(organization_id=org.id, name="Station One", code="S1")
    s2 = Station(organization_id=org.id, name="Station Two", code="S2")
    db.add_all([s1, s2])
    await db.commit()
    await db.refresh(s1)
    await db.refresh(s2)

    token = await login(client, "owner@acmefuel-dev.com")
    for station_id in (s1.id, s2.id):
        resp = await client.get(
            f"/organizations/{org.id}/stations/{station_id}", headers=auth_headers(token)
        )
        assert resp.status_code == 200


async def test_revoked_role_assignment_loses_access_immediately(
    client: AsyncClient, owner_user, org, db, seeded_roles
):
    token = await login(client, "owner@acmefuel-dev.com")

    assignment = (
        await db.execute(select(UserStationRole).where(UserStationRole.user_id == owner_user.id))
    ).scalar_one()

    # Still works before revocation.
    resp = await client.get(f"/organizations/{org.id}", headers=auth_headers(token))
    assert resp.status_code == 200

    assignment.is_active = False
    db.add(assignment)
    await db.commit()

    # Same still-valid access token, but the role is now inactive -> denied.
    # Permissions are re-checked against the DB on every request, not cached in the token.
    resp = await client.get(f"/organizations/{org.id}", headers=auth_headers(token))
    assert resp.status_code == 403


async def test_owner_can_list_a_users_role_assignments(
    client: AsyncClient, owner_user, cashier_user, org, station, seeded_roles
):
    """GET /organizations/{id}/users/{id}/roles - added so a Users & Settings
    screen has a way to show who already holds what role (previously only
    POST/DELETE existed for role assignments, with no corresponding read)."""
    token = await login(client, "owner@acmefuel-dev.com")

    resp = await client.get(
        f"/organizations/{org.id}/users/{cashier_user.id}/roles", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["role_id"] == str(seeded_roles["Cashier / Operator"].id)
    assert rows[0]["station_id"] == str(station.id)
    assert rows[0]["is_active"] is True


async def test_cannot_list_roles_for_a_user_not_in_this_organization(
    client: AsyncClient, owner_user, org, superuser
):
    """superuser has no UserStationRole row in `org` at all - not a member,
    so the owner (who can read org, has USER_READ) gets a 404, not a leak."""
    token = await login(client, "owner@acmefuel-dev.com")
    resp = await client.get(
        f"/organizations/{org.id}/users/{superuser.id}/roles", headers=auth_headers(token)
    )
    assert resp.status_code == 404


async def test_superuser_only_can_create_organization(client: AsyncClient, owner_user, superuser):
    owner_token = await login(client, "owner@acmefuel-dev.com")
    denied = await client.post(
        "/organizations", json={"name": "New Co"}, headers=auth_headers(owner_token)
    )
    assert denied.status_code == 403

    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    allowed = await client.post(
        "/organizations", json={"name": "New Co"}, headers=auth_headers(admin_token)
    )
    assert allowed.status_code == 201
