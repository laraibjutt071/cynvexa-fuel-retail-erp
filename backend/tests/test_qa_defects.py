"""
Regression tests for defects found during an independent QA pass over Phase 1
(2026-10-26), before the fixes landed in the same commit. Kept as their own
file so the reasoning for each is easy to find later.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permission_codes import USER_ASSIGN_ROLE
from app.models.role import Permission, Role
from app.models.station import Station
from app.models.user import User
from app.models.user_station_role import UserStationRole
from tests.conftest import auth_headers, login

pytestmark = pytest.mark.asyncio


async def test_station_scoped_assigner_cannot_grant_an_org_wide_role(
    client: AsyncClient, db: AsyncSession, org, station, seeded_roles
):
    """
    Defect: `require_permission` for POST /organizations/{org}/users/{user}/roles
    only resolves scope from the URL (organization_id) - there is no station_id
    in that route - so ANY active role in the org granting USER_ASSIGN_ROLE was
    accepted, regardless of whether the assignment being CREATED (whose scope
    comes from the request body, payload.station_id) exceeds the actor's own
    scope. A user trusted only at one station could therefore grant someone
    else org-wide access. This must be rejected: a station-scoped assigner may
    only grant roles scoped to their own station, never an org-wide (station_id
    = null) role.
    """
    # A custom role holding ONLY the assign-role permission - mirrors a future
    # "Regional Manager" style role, not just the all-powerful seeded Owner.
    perm = (
        await db.execute(select(Permission).where(Permission.code == USER_ASSIGN_ROLE))
    ).scalar_one()
    limited_role = Role(name="Assigner-only", description="test role", is_system=False)
    limited_role.permissions = [perm]
    db.add(limited_role)
    await db.flush()

    assigner = User(
        email="station-assigner@acmefuel-dev.com",
        full_name="Station Assigner",
        hashed_password="irrelevant-not-used-to-login-directly",
    )
    db.add(assigner)
    await db.flush()
    db.add(
        UserStationRole(
            user_id=assigner.id,
            organization_id=org.id,
            station_id=station.id,  # scoped to ONE station, not org-wide
            role_id=limited_role.id,
        )
    )

    victim = User(
        email="victim@acmefuel-dev.com",
        full_name="Victim",
        hashed_password="irrelevant",
    )
    db.add(victim)
    await db.commit()
    await db.refresh(assigner)
    await db.refresh(victim)

    # Log the assigner in through the real API (set a real password via the ORM
    # hash so /auth/login works for them).
    from app.core.security import hash_password

    assigner.hashed_password = hash_password("a-strong-password-123")
    db.add(assigner)
    await db.commit()

    token = await login(client, "station-assigner@acmefuel-dev.com")

    owner_role_id = seeded_roles["Owner"].id
    resp = await client.post(
        f"/organizations/{org.id}/users/{victim.id}/roles",
        json={"role_id": str(owner_role_id), "station_id": None},  # org-wide grant
        headers=auth_headers(token),
    )
    assert resp.status_code == 403, (
        "A station-scoped actor was able to grant an ORG-WIDE role - "
        f"privilege escalation. Response: {resp.status_code} {resp.text}"
    )


async def test_create_station_for_nonexistent_organization_gives_404_not_409(
    client: AsyncClient, superuser
):
    """
    Defect: create_station's except IntegrityError always raises a 409
    "code already exists" ConflictError, which is correct for the unique
    constraint but WRONG when the real cause is a foreign-key violation
    because organization_id doesn't exist (only reachable today via the
    superuser bypass, which skips the org-membership check that would
    otherwise guarantee the org exists). The client gets a misleading
    "duplicate code" error for what is actually a "no such organization".
    """
    token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    fake_org_id = uuid.uuid4()
    resp = await client.post(
        f"/organizations/{fake_org_id}/stations",
        json={"name": "Ghost Station", "code": "GHOST-1"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 404, (
        "Expected 404 Organization not found, got a misleading response: "
        f"{resp.status_code} {resp.text}"
    )


async def test_malformed_organization_id_in_path_is_422_not_403(client: AsyncClient, owner_user):
    """
    Defect: require_permission manually parses organization_id out of
    request.path_params as a raw string and used to raise PermissionDeniedError
    (403) on a ValueError - conflating "malformed input" with "access denied".
    A client sending garbage in the URL should get 422/400, not 403.
    """
    token = await login(client, "owner@acmefuel-dev.com")
    resp = await client.get("/organizations/not-a-uuid", headers=auth_headers(token))
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code} {resp.text}"


async def test_org_wide_owner_can_still_grant_and_revoke_any_scope(
    client: AsyncClient, db: AsyncSession, org, station, owner_user, seeded_roles
):
    """Positive-path check for the scope-grant fix: an org-wide role must
    still be able to grant AND revoke both org-wide and station-scoped roles.
    The fix must not have made legitimate delegation impossible."""
    victim = User(email="grant-target@acmefuel-dev.com", full_name="Target", hashed_password="x")
    db.add(victim)
    await db.commit()
    await db.refresh(victim)

    token = await login(client, "owner@acmefuel-dev.com")
    cashier_role_id = seeded_roles["Cashier / Operator"].id

    grant_resp = await client.post(
        f"/organizations/{org.id}/users/{victim.id}/roles",
        json={"role_id": str(cashier_role_id), "station_id": str(station.id)},
        headers=auth_headers(token),
    )
    assert grant_resp.status_code == 201, grant_resp.text
    assignment_id = grant_resp.json()["id"]

    revoke_resp = await client.delete(
        f"/organizations/{org.id}/users/{victim.id}/roles/{assignment_id}",
        headers=auth_headers(token),
    )
    assert revoke_resp.status_code == 204, revoke_resp.text


async def test_station_scoped_assigner_can_grant_within_their_own_station(
    client: AsyncClient, db: AsyncSession, org, station, seeded_roles
):
    """Positive-path check: the fix must not block the legitimate case of a
    station-scoped delegate granting a role scoped to THEIR OWN station."""
    from app.core.security import hash_password

    perm = (
        await db.execute(select(Permission).where(Permission.code == USER_ASSIGN_ROLE))
    ).scalar_one()
    limited_role = Role(name="Station Assigner", description="test role", is_system=False)
    limited_role.permissions = [perm]
    db.add(limited_role)
    await db.flush()

    assigner = User(
        email="legit-station-assigner@acmefuel-dev.com",
        full_name="Legit Assigner",
        hashed_password=hash_password("a-strong-password-123"),
    )
    db.add(assigner)
    await db.flush()
    db.add(
        UserStationRole(
            user_id=assigner.id, organization_id=org.id, station_id=station.id, role_id=limited_role.id
        )
    )
    victim = User(email="legit-victim@acmefuel-dev.com", full_name="Victim", hashed_password="x")
    db.add(victim)
    await db.commit()
    await db.refresh(victim)

    token = await login(client, "legit-station-assigner@acmefuel-dev.com")
    cashier_role_id = seeded_roles["Cashier / Operator"].id

    resp = await client.post(
        f"/organizations/{org.id}/users/{victim.id}/roles",
        json={"role_id": str(cashier_role_id), "station_id": str(station.id)},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, (
        "Granting a role scoped to the assigner's OWN station must still work: "
        f"{resp.status_code} {resp.text}"
    )
