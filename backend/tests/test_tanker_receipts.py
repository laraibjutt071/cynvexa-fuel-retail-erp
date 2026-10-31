import asyncio

import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers, login

pytestmark = pytest.mark.asyncio


def _receipt_payload(tank, supplier, **overrides):
    payload = {
        "tank_id": str(tank.id),
        "supplier_id": str(supplier.id),
        "tanker_registration": "TRK-001",
        "invoice_quantity": "10000",
        "pre_receipt_tank_reading": "2000",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Full lifecycle (positive path)
# ---------------------------------------------------------------------------


async def test_full_receipt_lifecycle_posts_to_stock_ledger(
    client: AsyncClient, owner_user, org, station, tank, supplier
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = f"/organizations/{org.id}/stations/{station.id}/tanker-receipts"

    create_resp = await client.post(base, json=_receipt_payload(tank, supplier), headers=auth_headers(token))
    assert create_resp.status_code == 201, create_resp.text
    receipt = create_resp.json()
    assert receipt["status"] == "pending_unload"
    receipt_id = receipt["id"]

    unload_resp = await client.patch(
        f"{base}/{receipt_id}/record-unload",
        json={"post_receipt_tank_reading": "11950"},
        headers=auth_headers(token),
    )
    assert unload_resp.status_code == 200
    assert unload_resp.json()["status"] == "awaiting_approval"
    assert unload_resp.json()["tank_gain_quantity"] == "9950.000"

    approve_resp = await client.patch(
        f"{base}/{receipt_id}/approve",
        json={"accepted_quantity": "9950", "payable_quantity_basis": "invoice_quantity"},
        headers=auth_headers(token),
    )
    assert approve_resp.status_code == 200, approve_resp.text
    approved = approve_resp.json()
    assert approved["status"] == "approved"
    assert approved["variance_quantity"] == "-50.000"
    assert approved["within_tolerance"] is True  # 0.5% off, default tolerance is 0.5%

    tank_resp = await client.get(
        f"/organizations/{org.id}/stations/{station.id}/tanks/{tank.id}", headers=auth_headers(token)
    )
    assert tank_resp.json()["book_stock"] == "9950.000"


async def test_reject_receipt_does_not_post_to_ledger(
    client: AsyncClient, owner_user, org, station, tank, supplier
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = f"/organizations/{org.id}/stations/{station.id}/tanker-receipts"

    create_resp = await client.post(base, json=_receipt_payload(tank, supplier), headers=auth_headers(token))
    receipt_id = create_resp.json()["id"]

    reject_resp = await client.patch(
        f"{base}/{receipt_id}/reject",
        json={"rejection_reason": "Wrong tanker arrived, seals broken."},
        headers=auth_headers(token),
    )
    assert reject_resp.status_code == 200
    assert reject_resp.json()["status"] == "rejected"

    tank_resp = await client.get(
        f"/organizations/{org.id}/stations/{station.id}/tanks/{tank.id}", headers=auth_headers(token)
    )
    assert tank_resp.json()["book_stock"] == "0.000"


# ---------------------------------------------------------------------------
# Duplicate / replayed submissions
# ---------------------------------------------------------------------------


async def test_approving_an_already_approved_receipt_is_rejected(
    client: AsyncClient, owner_user, org, station, tank, supplier
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = f"/organizations/{org.id}/stations/{station.id}/tanker-receipts"

    receipt_id = (
        await client.post(base, json=_receipt_payload(tank, supplier), headers=auth_headers(token))
    ).json()["id"]
    await client.patch(
        f"{base}/{receipt_id}/record-unload",
        json={"post_receipt_tank_reading": "11950"},
        headers=auth_headers(token),
    )
    first_approve = await client.patch(
        f"{base}/{receipt_id}/approve",
        json={"accepted_quantity": "9950", "payable_quantity_basis": "invoice_quantity"},
        headers=auth_headers(token),
    )
    assert first_approve.status_code == 200

    duplicate_approve = await client.patch(
        f"{base}/{receipt_id}/approve",
        json={"accepted_quantity": "9950", "payable_quantity_basis": "invoice_quantity"},
        headers=auth_headers(token),
    )
    assert duplicate_approve.status_code == 409

    # Still exactly one ledger posting worth of stock, not two.
    tank_resp = await client.get(
        f"/organizations/{org.id}/stations/{station.id}/tanks/{tank.id}", headers=auth_headers(token)
    )
    assert tank_resp.json()["book_stock"] == "9950.000"


async def test_recording_unload_twice_is_rejected(
    client: AsyncClient, owner_user, org, station, tank, supplier
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = f"/organizations/{org.id}/stations/{station.id}/tanker-receipts"
    receipt_id = (
        await client.post(base, json=_receipt_payload(tank, supplier), headers=auth_headers(token))
    ).json()["id"]

    first = await client.patch(
        f"{base}/{receipt_id}/record-unload",
        json={"post_receipt_tank_reading": "11950"},
        headers=auth_headers(token),
    )
    assert first.status_code == 200

    second = await client.patch(
        f"{base}/{receipt_id}/record-unload",
        json={"post_receipt_tank_reading": "12000"},
        headers=auth_headers(token),
    )
    assert second.status_code == 409


async def test_rejecting_an_approved_receipt_is_rejected(
    client: AsyncClient, owner_user, org, station, tank, supplier
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = f"/organizations/{org.id}/stations/{station.id}/tanker-receipts"
    receipt_id = (
        await client.post(base, json=_receipt_payload(tank, supplier), headers=auth_headers(token))
    ).json()["id"]
    await client.patch(
        f"{base}/{receipt_id}/record-unload",
        json={"post_receipt_tank_reading": "11950"},
        headers=auth_headers(token),
    )
    await client.patch(
        f"{base}/{receipt_id}/approve",
        json={"accepted_quantity": "9950", "payable_quantity_basis": "invoice_quantity"},
        headers=auth_headers(token),
    )

    resp = await client.patch(
        f"{base}/{receipt_id}/reject",
        json={"rejection_reason": "too late"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Invalid quantities
# ---------------------------------------------------------------------------


async def test_negative_tank_gain_is_rejected(client: AsyncClient, owner_user, org, station, tank, supplier):
    token = await login(client, "owner@acmefuel-dev.com")
    base = f"/organizations/{org.id}/stations/{station.id}/tanker-receipts"
    receipt_id = (
        await client.post(base, json=_receipt_payload(tank, supplier), headers=auth_headers(token))
    ).json()["id"]

    resp = await client.patch(
        f"{base}/{receipt_id}/record-unload",
        json={"post_receipt_tank_reading": "1000"},  # below pre_receipt_tank_reading of 2000
        headers=auth_headers(token),
    )
    assert resp.status_code == 422


async def test_zero_or_negative_declared_quantity_is_rejected(
    client: AsyncClient, owner_user, org, station, tank, supplier
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = f"/organizations/{org.id}/stations/{station.id}/tanker-receipts"
    resp = await client.post(
        base,
        json=_receipt_payload(tank, supplier, invoice_quantity="-500"),
        headers=auth_headers(token),
    )
    assert resp.status_code == 422


async def test_no_declared_quantity_at_all_is_rejected(
    client: AsyncClient, owner_user, org, station, tank, supplier
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = f"/organizations/{org.id}/stations/{station.id}/tanker-receipts"
    payload = _receipt_payload(tank, supplier)
    del payload["invoice_quantity"]
    resp = await client.post(base, json=payload, headers=auth_headers(token))
    assert resp.status_code == 422


async def test_approving_with_more_than_accepted_capacity_allows_but_payable_basis_must_exist(
    client: AsyncClient, owner_user, org, station, tank, supplier
):
    """approve() must reject a payable basis that was never recorded (e.g.
    choosing calibrated_quantity when it was never provided)."""
    token = await login(client, "owner@acmefuel-dev.com")
    base = f"/organizations/{org.id}/stations/{station.id}/tanker-receipts"
    receipt_id = (
        await client.post(base, json=_receipt_payload(tank, supplier), headers=auth_headers(token))
    ).json()["id"]
    await client.patch(
        f"{base}/{receipt_id}/record-unload",
        json={"post_receipt_tank_reading": "11950"},
        headers=auth_headers(token),
    )

    resp = await client.patch(
        f"{base}/{receipt_id}/approve",
        json={"accepted_quantity": "9950", "payable_quantity_basis": "calibrated_quantity"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Insufficient tank capacity
# ---------------------------------------------------------------------------


async def test_insufficient_capacity_blocks_receipt_creation(
    client: AsyncClient, owner_user, org, station, tank, supplier
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = f"/organizations/{org.id}/stations/{station.id}/tanker-receipts"
    # tank.safe_fill_limit is 18000, book stock is 0 -> only 18000 available.
    resp = await client.post(
        base,
        json=_receipt_payload(tank, supplier, invoice_quantity="19000", pre_receipt_tank_reading="0"),
        headers=auth_headers(token),
    )
    assert resp.status_code == 409
    assert "Insufficient tank capacity" in resp.json()["detail"]


async def test_capacity_is_rechecked_at_approval_against_current_stock(
    client: AsyncClient, owner_user, org, station, tank, supplier
):
    """
    Two receipts are created when capacity allows each individually (ledger
    isn't posted until approval), but approving BOTH in full must not be
    possible - the second approval has to re-check against the first's
    now-posted stock, not the stale snapshot taken when it was created.
    """
    token = await login(client, "owner@acmefuel-dev.com")
    base = f"/organizations/{org.id}/stations/{station.id}/tanker-receipts"

    # Tank capacity 18000 available. Two receipts of 10000 each both fit
    # individually at creation time (ledger still empty for both).
    r1 = (
        await client.post(
            base,
            json=_receipt_payload(tank, supplier, tanker_registration="TRK-A", invoice_quantity="10000"),
            headers=auth_headers(token),
        )
    ).json()["id"]
    r2 = (
        await client.post(
            base,
            json=_receipt_payload(
                tank, supplier, tanker_registration="TRK-B", invoice_quantity="10000", pre_receipt_tank_reading="2000"
            ),
            headers=auth_headers(token),
        )
    ).json()["id"]

    for rid in (r1, r2):
        resp = await client.patch(
            f"{base}/{rid}/record-unload",
            json={"post_receipt_tank_reading": "11950"},
            headers=auth_headers(token),
        )
        assert resp.status_code == 200

    first_approve = await client.patch(
        f"{base}/{r1}/approve",
        json={"accepted_quantity": "9950", "payable_quantity_basis": "invoice_quantity"},
        headers=auth_headers(token),
    )
    assert first_approve.status_code == 200

    second_approve = await client.patch(
        f"{base}/{r2}/approve",
        json={"accepted_quantity": "9950", "payable_quantity_basis": "invoice_quantity"},
        headers=auth_headers(token),
    )
    assert second_approve.status_code == 409
    assert "Insufficient tank capacity" in second_approve.json()["detail"]


# ---------------------------------------------------------------------------
# Permission failures
# ---------------------------------------------------------------------------


async def test_cashier_cannot_create_or_approve_receipts(
    client: AsyncClient, cashier_user, owner_user, org, station, tank, supplier
):
    cashier_token = await login(client, "cashier@acmefuel-dev.com")
    base = f"/organizations/{org.id}/stations/{station.id}/tanker-receipts"

    create_resp = await client.post(
        base, json=_receipt_payload(tank, supplier), headers=auth_headers(cashier_token)
    )
    assert create_resp.status_code == 403

    owner_token = await login(client, "owner@acmefuel-dev.com")
    receipt_id = (
        await client.post(base, json=_receipt_payload(tank, supplier), headers=auth_headers(owner_token))
    ).json()["id"]
    await client.patch(
        f"{base}/{receipt_id}/record-unload",
        json={"post_receipt_tank_reading": "11950"},
        headers=auth_headers(owner_token),
    )

    approve_resp = await client.patch(
        f"{base}/{receipt_id}/approve",
        json={"accepted_quantity": "9950", "payable_quantity_basis": "invoice_quantity"},
        headers=auth_headers(cashier_token),
    )
    assert approve_resp.status_code == 403


async def test_station_manager_can_create_and_approve(
    client: AsyncClient, station_manager_user, org, station, tank, supplier
):
    """Per blueprint §12: tanker acceptance is a Station Manager action."""
    token = await login(client, "manager@acmefuel-dev.com")
    base = f"/organizations/{org.id}/stations/{station.id}/tanker-receipts"
    receipt_id = (
        await client.post(base, json=_receipt_payload(tank, supplier), headers=auth_headers(token))
    ).json()["id"]
    await client.patch(
        f"{base}/{receipt_id}/record-unload",
        json={"post_receipt_tank_reading": "11950"},
        headers=auth_headers(token),
    )
    resp = await client.patch(
        f"{base}/{receipt_id}/approve",
        json={"accepted_quantity": "9950", "payable_quantity_basis": "invoice_quantity"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200


async def test_receipt_at_one_station_invisible_to_role_scoped_to_another_station(
    client: AsyncClient, org, station, tank, supplier, db, seeded_roles
):
    from app.core.security import hash_password
    from app.models.station import Station
    from app.models.user import User
    from app.models.user_station_role import UserStationRole

    other_station = Station(organization_id=org.id, name="Other Station", code="STN-2")
    db.add(other_station)
    await db.flush()

    owner = User(
        email="owner2@acmefuel-dev.com", full_name="Owner", hashed_password=hash_password("a-strong-password-123")
    )
    db.add(owner)
    await db.flush()
    db.add(
        UserStationRole(
            user_id=owner.id, organization_id=org.id, station_id=None, role_id=seeded_roles["Owner"].id
        )
    )

    other_station_manager = User(
        email="other-manager@acmefuel-dev.com",
        full_name="Other Manager",
        hashed_password=hash_password("a-strong-password-123"),
    )
    db.add(other_station_manager)
    await db.flush()
    db.add(
        UserStationRole(
            user_id=other_station_manager.id,
            organization_id=org.id,
            station_id=other_station.id,
            role_id=seeded_roles["Station Manager"].id,
        )
    )
    await db.commit()

    owner_token = await login(client, "owner2@acmefuel-dev.com")
    base = f"/organizations/{org.id}/stations/{station.id}/tanker-receipts"
    await client.post(base, json=_receipt_payload(tank, supplier), headers=auth_headers(owner_token))

    other_manager_token = await login(client, "other-manager@acmefuel-dev.com")
    denied_list = await client.get(base, headers=auth_headers(other_manager_token))
    assert denied_list.status_code == 403


# ---------------------------------------------------------------------------
# Conflicting / concurrent updates
# ---------------------------------------------------------------------------


async def test_concurrent_approval_of_the_same_receipt_only_succeeds_once(
    client: AsyncClient, org, station, tank, supplier, owner_user
):
    """
    Fires two approve requests at the same receipt concurrently (the
    `client` fixture's get_db override hands each request its own DB
    session, so this is a real concurrent-connection race, not an
    in-process illusion). The approve handler takes SELECT ... FOR UPDATE
    on the receipt row, so the two requests must serialize: exactly one
    succeeds (200) and the other sees the already-approved status and is
    rejected (409) - never both succeeding, never a double ledger posting.
    """
    token = await login(client, "owner@acmefuel-dev.com")
    base = f"/organizations/{org.id}/stations/{station.id}/tanker-receipts"
    receipt_id = (
        await client.post(base, json=_receipt_payload(tank, supplier), headers=auth_headers(token))
    ).json()["id"]
    await client.patch(
        f"{base}/{receipt_id}/record-unload",
        json={"post_receipt_tank_reading": "11950"},
        headers=auth_headers(token),
    )

    approve_body = {"accepted_quantity": "9950", "payable_quantity_basis": "invoice_quantity"}

    async def approve():
        return await client.patch(
            f"{base}/{receipt_id}/approve", json=approve_body, headers=auth_headers(token)
        )

    results = await asyncio.gather(approve(), approve())
    statuses = sorted(r.status_code for r in results)
    assert statuses == [200, 409], f"expected exactly one 200 and one 409, got {statuses}"

    tank_resp = await client.get(
        f"/organizations/{org.id}/stations/{station.id}/tanks/{tank.id}", headers=auth_headers(token)
    )
    assert tank_resp.json()["book_stock"] == "9950.000", "stock must be posted exactly once"
