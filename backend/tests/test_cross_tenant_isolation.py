"""
Explicit positive/negative coverage for unauthorized access, cross-station
access, and cross-organization data leakage across every list/read endpoint
that returns more than one row - the single-resource 404/403 cases are
already covered in test_rbac.py.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permission_codes import AUDIT_READ
from app.core.security import hash_password
from app.models.role import Permission, Role
from app.models.station import Station
from app.models.user import User
from app.models.user_station_role import UserStationRole
from tests.conftest import auth_headers, login

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Unauthorized access (no / bad token)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/organizations"),
        ("GET", "/roles"),
        ("GET", "/auth/me"),
    ],
)
async def test_unauthenticated_requests_are_rejected(client: AsyncClient, method: str, path: str):
    resp = await client.request(method, path)
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Cross-organization data leakage
# ---------------------------------------------------------------------------


async def test_list_organizations_never_shows_an_org_the_user_has_no_role_in(
    client: AsyncClient, owner_user, org, other_org
):
    """owner_user has a role only in `org`; `other_org` must never appear."""
    token = await login(client, "owner@acmefuel-dev.com")
    resp = await client.get("/organizations", headers=auth_headers(token))
    assert resp.status_code == 200
    org_ids = {o["id"] for o in resp.json()}
    assert str(org.id) in org_ids
    assert str(other_org.id) not in org_ids


async def test_list_users_does_not_leak_users_from_another_organization(
    client: AsyncClient, db: AsyncSession, owner_user, org, other_org, seeded_roles
):
    """A user who exists only in other_org must not appear when listing org's users."""
    foreign_user = User(
        email="foreign-org-user@acmefuel-dev.com", full_name="Foreign", hashed_password=hash_password("x")
    )
    db.add(foreign_user)
    await db.flush()
    db.add(
        UserStationRole(
            user_id=foreign_user.id,
            organization_id=other_org.id,
            station_id=None,
            role_id=seeded_roles["Owner"].id,
        )
    )
    await db.commit()

    token = await login(client, "owner@acmefuel-dev.com")
    resp = await client.get(f"/organizations/{org.id}/users", headers=auth_headers(token))
    assert resp.status_code == 200
    emails = {u["email"] for u in resp.json()}
    assert "foreign-org-user@acmefuel-dev.com" not in emails


async def test_list_stations_does_not_leak_stations_from_another_organization(
    client: AsyncClient, db: AsyncSession, owner_user, org, other_org
):
    foreign_station = Station(organization_id=other_org.id, name="Foreign Station", code="FOREIGN-1")
    db.add(foreign_station)
    await db.commit()

    token = await login(client, "owner@acmefuel-dev.com")
    resp = await client.get(f"/organizations/{org.id}/stations", headers=auth_headers(token))
    assert resp.status_code == 200
    codes = {s["code"] for s in resp.json()}
    assert "FOREIGN-1" not in codes

    # And the user has no role in other_org at all, so even asking directly is denied.
    denied = await client.get(f"/organizations/{other_org.id}/stations", headers=auth_headers(token))
    assert denied.status_code == 403


# ---------------------------------------------------------------------------
# Cross-station data leakage (same organization, different station)
# ---------------------------------------------------------------------------


async def test_station_scoped_audit_reader_cannot_see_another_stations_events(
    client: AsyncClient, db: AsyncSession, org, station, seeded_roles
):
    """
    A role holding AUDIT_READ scoped to ONE station must see that station's
    events and org-level events (station_id IS NULL), but NOT another
    station's events - even though both stations are in the same org the
    viewer does have (partial) access to.
    """
    other_station = Station(organization_id=org.id, name="Other Station", code="OTHER-1")
    db.add(other_station)
    await db.flush()

    perm = (
        await db.execute(select(Permission).where(Permission.code == AUDIT_READ))
    ).scalar_one()
    accountant_role = Role(name="Station Accountant", description="test role", is_system=False)
    accountant_role.permissions = [perm]
    db.add(accountant_role)
    await db.flush()

    viewer = User(
        email="station-accountant@acmefuel-dev.com",
        full_name="Station Accountant",
        hashed_password=hash_password("a-strong-password-123"),
    )
    db.add(viewer)
    await db.flush()
    db.add(
        UserStationRole(
            user_id=viewer.id, organization_id=org.id, station_id=station.id, role_id=accountant_role.id
        )
    )
    await db.commit()

    # Generate one audit event tied to `station` and one tied to `other_station`,
    # using the Owner (org-wide) to perform both updates.
    owner_login_email = "owner@acmefuel-dev.com"
    owner = User(
        email=owner_login_email, full_name="Owner", hashed_password=hash_password("a-strong-password-123")
    )
    db.add(owner)
    await db.flush()
    db.add(
        UserStationRole(
            user_id=owner.id, organization_id=org.id, station_id=None, role_id=seeded_roles["Owner"].id
        )
    )
    await db.commit()

    owner_token = await login(client, owner_login_email)
    for target_station, name in ((station, "Updated Own Station"), (other_station, "Updated Other Station")):
        resp = await client.patch(
            f"/organizations/{org.id}/stations/{target_station.id}",
            json={"name": name},
            headers=auth_headers(owner_token),
        )
        assert resp.status_code == 200

    viewer_token = await login(client, "station-accountant@acmefuel-dev.com")
    audit_resp = await client.get(
        f"/organizations/{org.id}/audit-log", headers=auth_headers(viewer_token)
    )
    assert audit_resp.status_code == 200
    entries = audit_resp.json()

    seen_station_ids = {e["station_id"] for e in entries if e["station_id"] is not None}
    assert str(station.id) in seen_station_ids
    assert str(other_station.id) not in seen_station_ids, (
        "A station-scoped audit viewer saw another station's audit event - cross-station leak."
    )


async def test_org_wide_audit_reader_sees_every_station(
    client: AsyncClient, db: AsyncSession, org, station, owner_user
):
    other_station = Station(organization_id=org.id, name="Other Station 2", code="OTHER-2")
    db.add(other_station)
    await db.commit()

    token = await login(client, "owner@acmefuel-dev.com")
    for target_station in (station, other_station):
        resp = await client.patch(
            f"/organizations/{org.id}/stations/{target_station.id}",
            json={"name": "Renamed"},
            headers=auth_headers(token),
        )
        assert resp.status_code == 200

    audit_resp = await client.get(f"/organizations/{org.id}/audit-log", headers=auth_headers(token))
    seen_station_ids = {e["station_id"] for e in audit_resp.json() if e["station_id"] is not None}
    assert str(station.id) in seen_station_ids
    assert str(other_station.id) in seen_station_ids
