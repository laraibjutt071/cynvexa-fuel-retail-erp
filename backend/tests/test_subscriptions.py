from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers, login

pytestmark = pytest.mark.asyncio


async def _create_plan(client: AsyncClient, token: str, code: str = "starter") -> str:
    resp = await client.post(
        "/platform/plans",
        json={
            "code": code,
            "name": "Starter",
            "price_monthly": "15000.00",
            "price_annual": "150000.00",
            "max_stations": 1,
            "max_users": 5,
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_non_superuser_cannot_manage_plans(client: AsyncClient, owner_user, org):
    token = await login(client, "owner@acmefuel-dev.com")
    resp = await client.post(
        "/platform/plans",
        json={"code": "x", "name": "X", "price_monthly": "1", "price_annual": "1"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 403


async def test_public_plans_endpoint_needs_no_auth_and_hides_inactive_plans(client: AsyncClient, superuser):
    token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    active_id = await _create_plan(client, token, code="public-active")
    inactive_resp = await client.post(
        "/platform/plans",
        json={"code": "public-inactive", "name": "Hidden", "price_monthly": "1", "price_annual": "1"},
        headers=auth_headers(token),
    )
    inactive_id = inactive_resp.json()["id"]
    await client.patch(f"/platform/plans/{inactive_id}", json={"is_active": False}, headers=auth_headers(token))

    public_resp = await client.get("/plans")
    assert public_resp.status_code == 200
    ids = [p["id"] for p in public_resp.json()]
    assert active_id in ids
    assert inactive_id not in ids


async def test_superuser_can_create_and_list_plans(client: AsyncClient, superuser):
    token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    plan_id = await _create_plan(client, token)

    list_resp = await client.get("/platform/plans", headers=auth_headers(token))
    assert list_resp.status_code == 200
    assert any(p["id"] == plan_id for p in list_resp.json())


async def test_duplicate_plan_code_is_rejected(client: AsyncClient, superuser):
    token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    await _create_plan(client, token, code="dup")
    resp = await client.post(
        "/platform/plans",
        json={"code": "dup", "name": "Dup Again", "price_monthly": "1", "price_annual": "1"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 409


async def test_platform_admin_can_assign_and_update_a_subscription(
    client: AsyncClient, superuser, owner_user, org
):
    token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    plan_id = await _create_plan(client, token, code="biz")

    now = datetime.now(timezone.utc)
    create_resp = await client.post(
        f"/platform/organizations/{org.id}/subscription",
        json={
            "plan_id": plan_id,
            "billing_cycle": "monthly",
            "status": "trial",
            "trial_ends_at": (now + timedelta(days=14)).isoformat(),
            "current_period_start": now.isoformat(),
            "current_period_end": (now + timedelta(days=30)).isoformat(),
        },
        headers=auth_headers(token),
    )
    assert create_resp.status_code == 201, create_resp.text
    sub = create_resp.json()
    assert sub["status"] == "trial"
    assert sub["plan"]["code"] == "biz"

    # A second subscription for the same org is rejected - one row per org.
    dup_resp = await client.post(
        f"/platform/organizations/{org.id}/subscription",
        json={
            "plan_id": plan_id,
            "current_period_start": now.isoformat(),
            "current_period_end": (now + timedelta(days=30)).isoformat(),
        },
        headers=auth_headers(token),
    )
    assert dup_resp.status_code == 409

    update_resp = await client.patch(
        f"/platform/subscriptions/{sub['id']}",
        json={"status": "active"},
        headers=auth_headers(token),
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["status"] == "active"

    # Owner (not platform admin) can see their own org's subscription...
    owner_token = await login(client, "owner@acmefuel-dev.com")
    mine_resp = await client.get(f"/organizations/{org.id}/subscription", headers=auth_headers(owner_token))
    assert mine_resp.status_code == 200
    assert mine_resp.json()["status"] == "active"

    # ...but cannot change it - there is no write endpoint under /organizations/.
    forbidden_resp = await client.patch(
        f"/organizations/{org.id}/subscription", json={"status": "canceled"}, headers=auth_headers(owner_token)
    )
    assert forbidden_resp.status_code == 405


async def test_a_users_subscription_view_is_isolated_to_their_own_organization(
    client: AsyncClient, superuser, owner_user, org, other_org
):
    """owner_user has a role in `org`, not `other_org` - must never see or infer
    other_org's subscription, even if one exists."""
    token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    plan_id = await _create_plan(client, token, code="iso")
    now = datetime.now(timezone.utc)
    await client.post(
        f"/platform/organizations/{other_org.id}/subscription",
        json={
            "plan_id": plan_id,
            "current_period_start": now.isoformat(),
            "current_period_end": (now + timedelta(days=30)).isoformat(),
        },
        headers=auth_headers(token),
    )

    owner_token = await login(client, "owner@acmefuel-dev.com")
    resp = await client.get(f"/organizations/{other_org.id}/subscription", headers=auth_headers(owner_token))
    assert resp.status_code == 403


async def test_recording_a_manual_payment_is_immediately_verified_with_an_audit_trail(
    client: AsyncClient, superuser, owner_user, org
):
    token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    plan_id = await _create_plan(client, token, code="pay")
    now = datetime.now(timezone.utc)
    sub_resp = await client.post(
        f"/platform/organizations/{org.id}/subscription",
        json={
            "plan_id": plan_id,
            "status": "active",
            "current_period_start": now.isoformat(),
            "current_period_end": (now + timedelta(days=30)).isoformat(),
        },
        headers=auth_headers(token),
    )
    sub_id = sub_resp.json()["id"]

    pay_resp = await client.post(
        f"/platform/subscriptions/{sub_id}/payments",
        json={
            "amount": "35000.00",
            "method": "bank_transfer",
            "reference": "TXN-001",
            "period_start": now.isoformat(),
            "period_end": (now + timedelta(days=30)).isoformat(),
        },
        headers=auth_headers(token),
    )
    assert pay_resp.status_code == 201, pay_resp.text
    payment = pay_resp.json()
    assert payment["status"] == "verified"
    assert payment["recorded_by_user_id"] is not None

    # The owner can see their own payment history...
    owner_token = await login(client, "owner@acmefuel-dev.com")
    hist_resp = await client.get(
        f"/organizations/{org.id}/subscription/payments", headers=auth_headers(owner_token)
    )
    assert hist_resp.status_code == 200
    assert len(hist_resp.json()) == 1
    assert hist_resp.json()[0]["reference"] == "TXN-001"

    # ...and the audit log recorded it.
    audit_resp = await client.get(
        f"/organizations/{org.id}/audit-log?action=subscription_payment.record", headers=auth_headers(owner_token)
    )
    assert audit_resp.status_code == 200
    assert len(audit_resp.json()) == 1
