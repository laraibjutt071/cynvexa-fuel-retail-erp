import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import auth_headers, login

pytestmark = pytest.mark.asyncio


async def test_create_employee_with_profile_fields(client: AsyncClient, owner_user, org, seeded_roles):
    token = await login(client, owner_user.email)
    resp = await client.post(
        f"/organizations/{org.id}/users",
        json={
            "email": "newhire@acmefuel-dev.com",
            "full_name": "New Hire",
            "password": "a-strong-password-123",
            "employee_code": "EMP-042",
            "job_title": "Shift Cashier",
            "phone": "+92-300-1112233",
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["employee_code"] == "EMP-042"
    assert body["job_title"] == "Shift Cashier"
    assert body["phone"] == "+92-300-1112233"


async def test_update_employee_profile_fields(client: AsyncClient, owner_user, org, station, seeded_roles):
    token = await login(client, owner_user.email)
    create = await client.post(
        f"/organizations/{org.id}/users",
        json={"email": "editme@acmefuel-dev.com", "full_name": "Edit Me", "password": "a-strong-password-123"},
        headers=auth_headers(token),
    )
    user_id = create.json()["id"]
    # A user with zero role assignments is invisible to this org's own
    # endpoints by design (_get_org_user_or_404) - give them a role first,
    # the same two-step flow Staff Management's "Add employee" uses.
    cashier_role = seeded_roles["Cashier / Operator"]
    await client.post(
        f"/organizations/{org.id}/users/{user_id}/roles",
        json={"role_id": str(cashier_role.id), "station_id": str(station.id)},
        headers=auth_headers(token),
    )

    resp = await client.patch(
        f"/organizations/{org.id}/users/{user_id}",
        json={"job_title": "Station Manager", "employee_code": "EMP-099"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    assert resp.json()["job_title"] == "Station Manager"
    assert resp.json()["employee_code"] == "EMP-099"


async def test_search_users_by_name_email_or_employee_code(client: AsyncClient, owner_user, org, station, seeded_roles):
    token = await login(client, owner_user.email)
    cashier_role = seeded_roles["Cashier / Operator"]

    zahid = await client.post(
        f"/organizations/{org.id}/users",
        json={
            "email": "zahid@acmefuel-dev.com",
            "full_name": "Zahid Hussain",
            "password": "a-strong-password-123",
            "employee_code": "ZH-01",
        },
        headers=auth_headers(token),
    )
    await client.post(
        f"/organizations/{org.id}/users/{zahid.json()['id']}/roles",
        json={"role_id": str(cashier_role.id), "station_id": str(station.id)},
        headers=auth_headers(token),
    )
    bilal = await client.post(
        f"/organizations/{org.id}/users",
        json={"email": "bilal@acmefuel-dev.com", "full_name": "Bilal Akhtar", "password": "a-strong-password-123"},
        headers=auth_headers(token),
    )
    await client.post(
        f"/organizations/{org.id}/users/{bilal.json()['id']}/roles",
        json={"role_id": str(cashier_role.id), "station_id": str(station.id)},
        headers=auth_headers(token),
    )

    by_name = await client.get(f"/organizations/{org.id}/users?q=Zahid", headers=auth_headers(token))
    assert [u["full_name"] for u in by_name.json()] == ["Zahid Hussain"]

    by_code = await client.get(f"/organizations/{org.id}/users?q=ZH-01", headers=auth_headers(token))
    assert [u["full_name"] for u in by_code.json()] == ["Zahid Hussain"]

    by_email = await client.get(f"/organizations/{org.id}/users?q=bilal@acmefuel-dev.com", headers=auth_headers(token))
    assert [u["full_name"] for u in by_email.json()] == ["Bilal Akhtar"]


async def test_filter_users_by_status(client: AsyncClient, owner_user, org, station, seeded_roles):
    token = await login(client, owner_user.email)
    create = await client.post(
        f"/organizations/{org.id}/users",
        json={"email": "tobedeactivated@acmefuel-dev.com", "full_name": "Soon Inactive", "password": "a-strong-password-123"},
        headers=auth_headers(token),
    )
    user_id = create.json()["id"]
    cashier_role = seeded_roles["Cashier / Operator"]
    await client.post(
        f"/organizations/{org.id}/users/{user_id}/roles",
        json={"role_id": str(cashier_role.id), "station_id": str(station.id)},
        headers=auth_headers(token),
    )
    await client.patch(f"/organizations/{org.id}/users/{user_id}", json={"is_active": False}, headers=auth_headers(token))

    active = await client.get(f"/organizations/{org.id}/users?status=active", headers=auth_headers(token))
    assert all(u["is_active"] for u in active.json())
    assert not any(u["id"] == user_id for u in active.json())

    inactive = await client.get(f"/organizations/{org.id}/users?status=inactive", headers=auth_headers(token))
    assert any(u["id"] == user_id for u in inactive.json())
    assert all(not u["is_active"] for u in inactive.json())


async def test_filter_users_by_station(client: AsyncClient, owner_user, org, station, db: AsyncSession, seeded_roles):
    token = await login(client, owner_user.email)
    create = await client.post(
        f"/organizations/{org.id}/users",
        json={"email": "stationstaff@acmefuel-dev.com", "full_name": "Station Staff", "password": "a-strong-password-123"},
        headers=auth_headers(token),
    )
    user_id = create.json()["id"]
    cashier_role = seeded_roles["Cashier / Operator"]
    await client.post(
        f"/organizations/{org.id}/users/{user_id}/roles",
        json={"role_id": str(cashier_role.id), "station_id": str(station.id)},
        headers=auth_headers(token),
    )

    resp = await client.get(f"/organizations/{org.id}/users?station_id={station.id}", headers=auth_headers(token))
    ids = [u["id"] for u in resp.json()]
    assert user_id in ids
    # The Owner is org-wide (station_id is NULL on their own assignment), not
    # scoped to this one station, so a station filter correctly excludes them.
    assert str(owner_user.id) not in ids


async def test_deactivated_employee_cannot_access_protected_apis(
    client: AsyncClient, owner_user, org, station, seeded_roles
):
    """UserUpdate's is_active already flows into the real User row, and
    get_current_user already rejects an inactive user - this proves the
    whole chain works for a real staff member, not just by reading the
    dependency code."""
    token = await login(client, owner_user.email)
    create = await client.post(
        f"/organizations/{org.id}/users",
        json={"email": "fireme@acmefuel-dev.com", "full_name": "Fire Me", "password": "a-strong-password-123"},
        headers=auth_headers(token),
    )
    user_id = create.json()["id"]
    cashier_role = seeded_roles["Cashier / Operator"]
    await client.post(
        f"/organizations/{org.id}/users/{user_id}/roles",
        json={"role_id": str(cashier_role.id), "station_id": str(station.id)},
        headers=auth_headers(token),
    )

    staff_token = await login(client, "fireme@acmefuel-dev.com")
    still_works = await client.get(f"/organizations/{org.id}/stations/{station.id}", headers=auth_headers(staff_token))
    assert still_works.status_code == 200

    await client.patch(f"/organizations/{org.id}/users/{user_id}", json={"is_active": False}, headers=auth_headers(token))

    blocked = await client.get(f"/organizations/{org.id}/stations/{station.id}", headers=auth_headers(staff_token))
    assert blocked.status_code == 401


async def test_owner_cannot_create_platform_administrator_via_staff_creation(
    client: AsyncClient, owner_user, org, db: AsyncSession, seeded_roles
):
    """UserCreate has no is_superuser field at all - sending one is simply
    ignored by Pydantic, never honored, confirmed against the real row."""
    token = await login(client, owner_user.email)
    resp = await client.post(
        f"/organizations/{org.id}/users",
        json={
            "email": "wannabeadmin@acmefuel-dev.com",
            "full_name": "Wannabe Admin",
            "password": "a-strong-password-123",
            "is_superuser": True,
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    from sqlalchemy import select

    from app.models.user import User

    created = (await db.execute(select(User).where(User.email == "wannabeadmin@acmefuel-dev.com"))).scalar_one()
    assert created.is_superuser is False
