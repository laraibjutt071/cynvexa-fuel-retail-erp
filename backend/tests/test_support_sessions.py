import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.audit_log import AuditLog
from app.models.organization import Organization
from app.models.station import Station
from app.models.support_session import SupportSession
from app.models.user import User
from tests.conftest import auth_headers, login

pytestmark = pytest.mark.asyncio


async def _start_session(client: AsyncClient, admin_token: str, organization_id, station_id=None, duration_minutes=15, reason="Investigating a client-reported issue."):
    return await client.post(
        "/platform/support-sessions",
        json={
            "organization_id": str(organization_id),
            "station_id": str(station_id) if station_id else None,
            "reason": reason,
            "duration_minutes": duration_minutes,
        },
        headers=auth_headers(admin_token),
    )


# ---- A. Session creation ------------------------------------------------------


async def test_authorized_superuser_can_create_a_session(client: AsyncClient, superuser, org, seeded_roles):
    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    resp = await _start_session(client, admin_token, org.id)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["organization_id"] == str(org.id)
    assert body["status"] == "active"
    assert body["station_id"] is None


async def test_unauthorized_user_cannot_create_a_session(client: AsyncClient, owner_user, org, seeded_roles):
    token = await login(client, owner_user.email)
    resp = await _start_session(client, token, org.id)
    assert resp.status_code == 403


async def test_missing_reason_is_rejected(client: AsyncClient, superuser, org, seeded_roles):
    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    resp = await client.post(
        "/platform/support-sessions",
        json={"organization_id": str(org.id), "reason": "short", "duration_minutes": 15},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 422


async def test_invalid_duration_is_rejected(client: AsyncClient, superuser, org, seeded_roles):
    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    resp = await _start_session(client, admin_token, org.id, duration_minutes=999)
    assert resp.status_code == 422


async def test_nonexistent_organization_gives_404(client: AsyncClient, superuser):
    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    resp = await _start_session(client, admin_token, uuid.uuid4())
    assert resp.status_code == 404


async def test_station_not_belonging_to_organization_gives_404(
    client: AsyncClient, superuser, org, other_org, seeded_roles, db: AsyncSession
):
    other_station = Station(organization_id=other_org.id, name="Other Station", code="OTH-1")
    db.add(other_station)
    await db.commit()
    await db.refresh(other_station)

    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    resp = await _start_session(client, admin_token, org.id, station_id=other_station.id)
    assert resp.status_code == 404


async def test_suspended_organization_can_still_have_a_session_opened(
    client: AsyncClient, superuser, org, seeded_roles
):
    """Creating a session never silently reactivates a suspended org, and
    is not itself blocked by suspension - investigating why an org is
    suspended is a legitimate reason to open one."""
    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    suspend = await client.patch(f"/organizations/{org.id}", json={"is_active": False}, headers=auth_headers(admin_token))
    assert suspend.status_code == 200

    resp = await _start_session(client, admin_token, org.id)
    assert resp.status_code == 201

    refreshed = await client.get(f"/organizations/{org.id}", headers=auth_headers(admin_token))
    assert refreshed.json()["is_active"] is False


# ---- B. Session access --------------------------------------------------------


async def test_session_grants_access_to_its_own_organization(
    client: AsyncClient, superuser, org, station, seeded_roles
):
    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    assert (await _start_session(client, admin_token, org.id)).status_code == 201

    resp = await client.get(f"/organizations/{org.id}/stations", headers=auth_headers(admin_token))
    assert resp.status_code == 200


async def test_session_does_not_grant_access_to_a_different_organization(
    client: AsyncClient, superuser, org, other_org, seeded_roles
):
    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    assert (await _start_session(client, admin_token, org.id)).status_code == 201

    resp = await client.get(f"/organizations/{other_org.id}/stations", headers=auth_headers(admin_token))
    assert resp.status_code == 403


async def test_station_scoped_session_does_not_grant_a_different_station(
    client: AsyncClient, superuser, org, station, seeded_roles, db: AsyncSession
):
    other_station = Station(organization_id=org.id, name="Second Station", code="STN-2")
    db.add(other_station)
    await db.commit()
    await db.refresh(other_station)

    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    assert (await _start_session(client, admin_token, org.id, station_id=station.id)).status_code == 201

    allowed = await client.get(
        f"/organizations/{org.id}/stations/{station.id}", headers=auth_headers(admin_token)
    )
    assert allowed.status_code == 200

    denied = await client.get(
        f"/organizations/{org.id}/stations/{other_station.id}", headers=auth_headers(admin_token)
    )
    assert denied.status_code == 403


async def test_expired_session_loses_access(
    client: AsyncClient, db: AsyncSession, superuser, org, seeded_roles
):
    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    create = await _start_session(client, admin_token, org.id)
    assert create.status_code == 201

    session = (await db.execute(select(SupportSession).where(SupportSession.id == create.json()["id"]))).scalar_one()
    session.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db.commit()

    resp = await client.get(f"/organizations/{org.id}/stations", headers=auth_headers(admin_token))
    assert resp.status_code == 403


async def test_ended_session_loses_access_immediately(
    client: AsyncClient, superuser, org, seeded_roles
):
    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    create = await _start_session(client, admin_token, org.id)
    session_id = create.json()["id"]

    end_resp = await client.post(f"/platform/support-sessions/{session_id}/end", headers=auth_headers(admin_token))
    assert end_resp.status_code == 200
    assert end_resp.json()["status"] == "ended"

    resp = await client.get(f"/organizations/{org.id}/stations", headers=auth_headers(admin_token))
    assert resp.status_code == 403


async def test_a_session_belongs_to_the_admin_who_opened_it(
    client: AsyncClient, db: AsyncSession, superuser, org, seeded_roles
):
    """A second administrator has no access through someone else's
    session - and cannot even see or end it."""
    second_admin = User(
        email="second-admin@cynvexa-platform-dev.com",
        full_name="Second Admin",
        hashed_password=hash_password("a-strong-password-123"),
        is_superuser=True,
    )
    db.add(second_admin)
    await db.commit()

    first_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    create = await _start_session(client, first_token, org.id)
    session_id = create.json()["id"]

    second_token = await login(client, "second-admin@cynvexa-platform-dev.com")
    # The second admin has no session of their own - no access to org's data.
    resp = await client.get(f"/organizations/{org.id}/stations", headers=auth_headers(second_token))
    assert resp.status_code == 403

    # Nor can they end the first admin's session.
    end_resp = await client.post(f"/platform/support-sessions/{session_id}/end", headers=auth_headers(second_token))
    assert end_resp.status_code == 403


async def test_missing_support_context_is_denied(client: AsyncClient, superuser, org, seeded_roles):
    """No session at all - the bare is_superuser bypass this phase removed."""
    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    resp = await client.get(f"/organizations/{org.id}/stations", headers=auth_headers(admin_token))
    assert resp.status_code == 403


async def test_organization_id_cannot_be_widened_via_query_string(
    client: AsyncClient, superuser, org, other_org, seeded_roles
):
    """require_permission only ever resolves organization_id from the
    URL's own path parameters - a query string claiming a different,
    session-covered organization must not widen access to other_org."""
    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    assert (await _start_session(client, admin_token, org.id)).status_code == 201

    resp = await client.get(
        f"/organizations/{other_org.id}/stations?organization_id={org.id}", headers=auth_headers(admin_token)
    )
    assert resp.status_code == 403


# ---- C. Privilege separation --------------------------------------------------


async def test_tenant_owner_cannot_create_a_support_session(client: AsyncClient, owner_user, org, seeded_roles):
    token = await login(client, owner_user.email)
    resp = await _start_session(client, token, org.id)
    assert resp.status_code == 403


async def test_employee_cannot_create_a_support_session(client: AsyncClient, cashier_user, org, seeded_roles):
    token = await login(client, cashier_user.email)
    resp = await _start_session(client, token, org.id)
    assert resp.status_code == 403


async def test_support_session_cannot_reach_unrelated_platform_configuration(
    client: AsyncClient, superuser, org, seeded_roles
):
    """A support session is a tenant-business-data grant only - it has
    nothing to do with (and does not need to touch) platform-level
    routes, which already depend on require_superuser directly."""
    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    assert (await _start_session(client, admin_token, org.id)).status_code == 201

    resp = await client.get("/platform/plans", headers=auth_headers(admin_token))
    assert resp.status_code == 200  # superuser already could - unaffected by the session either way


async def test_support_session_cannot_grant_itself_additional_permissions(
    client: AsyncClient, superuser, org, seeded_roles
):
    """Nothing about the session payload lets the caller request a wider
    grant than org/station + read-only - there is no field for it."""
    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    resp = await client.post(
        "/platform/support-sessions",
        json={
            "organization_id": str(org.id),
            "reason": "Trying to smuggle in extra access.",
            "duration_minutes": 15,
            "write_enabled": True,
            "permissions": ["user:assign_role"],
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201  # unknown extra fields are simply ignored by the schema
    assert "write_enabled" not in resp.json()
    assert "permissions" not in resp.json()


# ---- D. Write restrictions -----------------------------------------------------


async def test_support_session_cannot_create_a_user(client: AsyncClient, superuser, org, seeded_roles):
    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    assert (await _start_session(client, admin_token, org.id)).status_code == 201

    resp = await client.post(
        f"/organizations/{org.id}/users",
        json={"email": "newbie@acmefuel-dev.com", "full_name": "Newbie", "password": "a-strong-password-123"},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 403


async def test_support_session_cannot_assign_a_role(
    client: AsyncClient, superuser, owner_user, org, seeded_roles
):
    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    assert (await _start_session(client, admin_token, org.id)).status_code == 201

    resp = await client.post(
        f"/organizations/{org.id}/users/{owner_user.id}/roles",
        json={"role_id": str(seeded_roles["Cashier / Operator"].id)},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 403


async def test_support_session_cannot_update_station_configuration(
    client: AsyncClient, superuser, org, station, seeded_roles
):
    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    assert (await _start_session(client, admin_token, org.id)).status_code == 201

    resp = await client.patch(
        f"/organizations/{org.id}/stations/{station.id}", json={"name": "Renamed"}, headers=auth_headers(admin_token)
    )
    assert resp.status_code == 403


async def test_support_session_read_access_still_works_alongside_the_write_denial(
    client: AsyncClient, superuser, org, station, seeded_roles
):
    """Confirms the write denials above are a real restriction, not a
    session that simply doesn't work at all."""
    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    assert (await _start_session(client, admin_token, org.id)).status_code == 201

    resp = await client.get(f"/organizations/{org.id}/stations/{station.id}", headers=auth_headers(admin_token))
    assert resp.status_code == 200


# ---- E. Concurrency ------------------------------------------------------------


async def test_one_active_session_per_admin_is_enforced(client: AsyncClient, superuser, org, other_org, seeded_roles):
    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    first = await _start_session(client, admin_token, org.id)
    assert first.status_code == 201

    second = await _start_session(client, admin_token, other_org.id)
    assert second.status_code == 409


async def test_concurrent_session_creation_cannot_both_succeed(
    client: AsyncClient, superuser, org, other_org, seeded_roles
):
    """Two simultaneous creation requests from the same admin, with no
    existing session row to lock yet - the partial unique index must
    still let only one through."""
    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    results = await asyncio.gather(
        _start_session(client, admin_token, org.id, reason="First concurrent attempt."),
        _start_session(client, admin_token, other_org.id, reason="Second concurrent attempt."),
    )
    statuses = sorted(r.status_code for r in results)
    assert statuses == [201, 409]


async def test_an_expired_session_cannot_be_renewed_by_repeating_requests(
    client: AsyncClient, db: AsyncSession, superuser, org, seeded_roles
):
    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    create = await _start_session(client, admin_token, org.id)
    session = (await db.execute(select(SupportSession).where(SupportSession.id == create.json()["id"]))).scalar_one()
    session.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db.commit()

    for _ in range(3):
        resp = await client.get(f"/organizations/{org.id}/stations", headers=auth_headers(admin_token))
        assert resp.status_code == 403

    # But a brand-new session is allowed, since the expired one auto-closes.
    second = await _start_session(client, admin_token, org.id)
    assert second.status_code == 201


# ---- F. Audit -------------------------------------------------------------------


async def test_session_creation_and_end_are_both_recorded(
    client: AsyncClient, db: AsyncSession, superuser, org, seeded_roles
):
    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    create = await _start_session(client, admin_token, org.id)
    session_id = create.json()["id"]
    await client.post(f"/platform/support-sessions/{session_id}/end", headers=auth_headers(admin_token))

    actions = (
        await db.execute(select(AuditLog.action).where(AuditLog.entity_id == session_id))
    ).scalars().all()
    assert "support_session.create" in actions
    assert "support_session.end" in actions


async def test_denied_cross_tenant_access_is_recorded(
    client: AsyncClient, db: AsyncSession, superuser, org, other_org, seeded_roles
):
    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    assert (await _start_session(client, admin_token, org.id)).status_code == 201

    resp = await client.get(f"/organizations/{other_org.id}/stations", headers=auth_headers(admin_token))
    assert resp.status_code == 403

    rows = (
        await db.execute(
            select(AuditLog).where(
                AuditLog.action == "support_session.access_denied",
                AuditLog.organization_id == other_org.id,
            )
        )
    ).scalars().all()
    assert len(rows) >= 1
