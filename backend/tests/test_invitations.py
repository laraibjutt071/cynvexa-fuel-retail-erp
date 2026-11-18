import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invitation import Invitation
from tests.conftest import auth_headers, login

pytestmark = pytest.mark.asyncio


async def test_create_invitation_returns_token_once(client: AsyncClient, owner_user, org, station, seeded_roles):
    token = await login(client, owner_user.email)
    cashier_role = seeded_roles["Cashier / Operator"]
    resp = await client.post(
        f"/organizations/{org.id}/invitations",
        json={
            "email": "invited@acmefuel-dev.com",
            "full_name": "Invited Person",
            "role_id": str(cashier_role.id),
            "station_id": str(station.id),
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert "token" in body and len(body["token"]) > 20
    assert body["email"] == "invited@acmefuel-dev.com"


async def test_preview_invitation_before_accepting(client: AsyncClient, owner_user, org, station, seeded_roles):
    token = await login(client, owner_user.email)
    cashier_role = seeded_roles["Cashier / Operator"]
    create = await client.post(
        f"/organizations/{org.id}/invitations",
        json={"email": "preview@acmefuel-dev.com", "full_name": "Preview Person", "role_id": str(cashier_role.id), "station_id": str(station.id)},
        headers=auth_headers(token),
    )
    raw_token = create.json()["token"]

    preview = await client.get(f"/invitations/{raw_token}/preview")
    assert preview.status_code == 200
    body = preview.json()
    assert body["valid"] is True
    assert body["organization_name"] == org.name
    assert body["role_name"] == "Cashier / Operator"
    assert body["station_name"] == station.name


async def test_accept_invitation_creates_user_with_role_and_logs_in(
    client: AsyncClient, db: AsyncSession, owner_user, org, station, seeded_roles
):
    token = await login(client, owner_user.email)
    cashier_role = seeded_roles["Cashier / Operator"]
    create = await client.post(
        f"/organizations/{org.id}/invitations",
        json={"email": "accepted@acmefuel-dev.com", "full_name": "Accepted Person", "role_id": str(cashier_role.id), "station_id": str(station.id)},
        headers=auth_headers(token),
    )
    raw_token = create.json()["token"]

    accept = await client.post("/invitations/accept", json={"token": raw_token, "password": "a-strong-password-123"})
    assert accept.status_code == 200, accept.text
    assert "access_token" in accept.json()

    # The new account is real and can log in independently afterward too.
    new_token = await login(client, "accepted@acmefuel-dev.com")
    me = await client.get("/auth/me", headers=auth_headers(new_token))
    roles = [r for r in me.json()["station_roles"] if r["organization_id"] == str(org.id)]
    assert len(roles) == 1
    assert roles[0]["station_id"] == str(station.id)


async def test_accepted_invitation_cannot_be_reused(client: AsyncClient, owner_user, org, station, seeded_roles):
    token = await login(client, owner_user.email)
    cashier_role = seeded_roles["Cashier / Operator"]
    create = await client.post(
        f"/organizations/{org.id}/invitations",
        json={"email": "reuse@acmefuel-dev.com", "full_name": "Reuse Person", "role_id": str(cashier_role.id), "station_id": str(station.id)},
        headers=auth_headers(token),
    )
    raw_token = create.json()["token"]
    first = await client.post("/invitations/accept", json={"token": raw_token, "password": "a-strong-password-123"})
    assert first.status_code == 200

    second = await client.post("/invitations/accept", json={"token": raw_token, "password": "a-different-password-456"})
    assert second.status_code == 422


async def test_expired_invitation_is_rejected(client: AsyncClient, db: AsyncSession, owner_user, org, station, seeded_roles):
    token = await login(client, owner_user.email)
    cashier_role = seeded_roles["Cashier / Operator"]
    create = await client.post(
        f"/organizations/{org.id}/invitations",
        json={"email": "expired@acmefuel-dev.com", "full_name": "Expired Person", "role_id": str(cashier_role.id), "station_id": str(station.id)},
        headers=auth_headers(token),
    )
    raw_token = create.json()["token"]

    from datetime import datetime, timedelta, timezone

    inv = (await db.execute(select(Invitation).where(Invitation.email == "expired@acmefuel-dev.com"))).scalar_one()
    inv.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await db.commit()

    accept = await client.post("/invitations/accept", json={"token": raw_token, "password": "a-strong-password-123"})
    assert accept.status_code == 422


async def test_revoked_invitation_is_rejected(client: AsyncClient, owner_user, org, station, seeded_roles):
    token = await login(client, owner_user.email)
    cashier_role = seeded_roles["Cashier / Operator"]
    create = await client.post(
        f"/organizations/{org.id}/invitations",
        json={"email": "revoked@acmefuel-dev.com", "full_name": "Revoked Person", "role_id": str(cashier_role.id), "station_id": str(station.id)},
        headers=auth_headers(token),
    )
    invitation_id = create.json()["id"]
    raw_token = create.json()["token"]

    revoke = await client.delete(f"/organizations/{org.id}/invitations/{invitation_id}", headers=auth_headers(token))
    assert revoke.status_code == 204

    accept = await client.post("/invitations/accept", json={"token": raw_token, "password": "a-strong-password-123"})
    assert accept.status_code == 422


async def test_invalid_token_is_rejected(client: AsyncClient):
    resp = await client.post("/invitations/accept", json={"token": "not-a-real-token", "password": "a-strong-password-123"})
    assert resp.status_code == 404


async def test_cashier_cannot_invite_anyone(client: AsyncClient, cashier_user, org, seeded_roles):
    """Cashier/Operator holds no user:create permission at all (the same
    seed-role catalog every other RBAC test uses) - confirms invitations
    go through the ordinary require_permission(USER_CREATE) gate, not a
    separate, weaker check."""
    token = await login(client, cashier_user.email)
    owner_role = seeded_roles["Owner"]
    resp = await client.post(
        f"/organizations/{org.id}/invitations",
        json={"email": "shouldfail@acmefuel-dev.com", "full_name": "Should Fail", "role_id": str(owner_role.id)},
        headers=auth_headers(token),
    )
    assert resp.status_code == 403


async def test_tenant_a_cannot_invite_into_tenant_b(client: AsyncClient, owner_user, other_org, seeded_roles):
    token = await login(client, owner_user.email)
    resp = await client.post(
        f"/organizations/{other_org.id}/invitations",
        json={"email": "crosstenant@acmefuel-dev.com", "full_name": "Cross Tenant", "role_id": "00000000-0000-0000-0000-000000000000"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 403
