import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers, login

pytestmark = pytest.mark.asyncio


def _base(org, station) -> str:
    return f"/organizations/{org.id}/stations/{station.id}/shifts"


# ---------------------------------------------------------------------------
# Authorization / permission boundaries
# ---------------------------------------------------------------------------


async def test_cashier_can_record_tenders_and_movements_but_not_approve_or_authorize(
    client: AsyncClient, cashier_user, org, station, cash_payment_method
):
    token = await login(client, "cashier@acmefuel-dev.com")
    base = _base(org, station)
    shift = (await client.post(base, json={}, headers=auth_headers(token))).json()
    shift_id = shift["id"]

    tender_resp = await client.post(
        f"{base}/{shift_id}/tenders",
        json={"payment_method_id": str(cash_payment_method.id), "amount": "1000"},
        headers=auth_headers(token),
    )
    assert tender_resp.status_code == 201, tender_resp.text

    expense_resp = await client.post(
        f"{base}/{shift_id}/cash-movements",
        json={"movement_type": "expense", "amount": "100", "reason": "x"},
        headers=auth_headers(token),
    )
    assert expense_resp.status_code == 201
    expense_id = expense_resp.json()["id"]

    approve_resp = await client.patch(
        f"{base}/{shift_id}/cash-movements/{expense_id}/approve", headers=auth_headers(token)
    )
    assert approve_resp.status_code == 403


async def test_only_accountant_and_owner_can_authorize_material_discrepancy(
    client: AsyncClient,
    owner_user,
    station_manager_user,
    org,
    station,
    tank_with_stock,
    nozzle,
    fuel_price,
    cash_payment_method,
    seeded_roles,
    db,
):
    """Per blueprint §12, only "Accountant" is explicitly named for cash
    variance approval - Station Manager is deliberately NOT given
    shift_reconcile:approve (see docs/ASSUMPTIONS.md). This is the
    strictest, most literal reading of the source document."""
    from app.core.security import hash_password
    from app.models.user import User
    from app.models.user_station_role import UserStationRole

    accountant = User(
        email="accountant@acmefuel-dev.com",
        full_name="Accountant",
        hashed_password=hash_password("a-strong-password-123"),
    )
    db.add(accountant)
    await db.flush()
    db.add(
        UserStationRole(
            user_id=accountant.id,
            organization_id=org.id,
            station_id=station.id,
            role_id=seeded_roles["Accountant"].id,
        )
    )
    await db.commit()

    owner_token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)

    shift = (await client.post(base, json={}, headers=auth_headers(owner_token))).json()
    shift_id = shift["id"]
    await client.post(
        f"{base}/{shift_id}/tank-readings/opening",
        json={"tank_id": str(tank_with_stock.id), "dip_reading": "10000"},
        headers=auth_headers(owner_token),
    )
    await client.post(
        f"{base}/{shift_id}/tank-readings/closing",
        json={"tank_id": str(tank_with_stock.id), "dip_reading": "9500"},
        headers=auth_headers(owner_token),
    )
    nr = (
        await client.post(
            f"{base}/{shift_id}/nozzle-readings",
            json={"nozzle_id": str(nozzle.id), "opening_totalizer": "5000"},
            headers=auth_headers(owner_token),
        )
    ).json()
    await client.patch(
        f"{base}/{shift_id}/nozzle-readings/{nr['id']}/close",
        json={"closing_totalizer": "5500"},
        headers=auth_headers(owner_token),
    )
    await client.patch(f"{base}/{shift_id}/close", headers=auth_headers(owner_token))
    await client.post(
        f"{base}/{shift_id}/tenders",
        json={"payment_method_id": str(cash_payment_method.id), "amount": "100000"},  # far short of 140000
        headers=auth_headers(owner_token),
    )
    await client.post(
        f"{base}/{shift_id}/reconciliation",
        json={"actual_physical_cash": "100000", "explanation": "investigating"},
        headers=auth_headers(owner_token),
    )

    manager_token = await login(client, "manager@acmefuel-dev.com")
    denied = await client.patch(
        f"{base}/{shift_id}/reconciliation/authorize", json={}, headers=auth_headers(manager_token)
    )
    assert denied.status_code == 403

    accountant_token = await login(client, "accountant@acmefuel-dev.com")
    allowed = await client.patch(
        f"{base}/{shift_id}/reconciliation/authorize", json={}, headers=auth_headers(accountant_token)
    )
    assert allowed.status_code == 200, allowed.text


# ---------------------------------------------------------------------------
# Reversals
# ---------------------------------------------------------------------------


async def test_reversed_tender_is_excluded_from_totals(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, fuel_price, cash_payment_method
):
    from tests.test_shift_reconciliation import _closed_shift

    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)
    shift_id = await _closed_shift(client, token, org, station, tank_with_stock, nozzle, litres="500")

    bad_tender = await client.post(
        f"{base}/{shift_id}/tenders",
        json={"payment_method_id": str(cash_payment_method.id), "amount": "999999"},
        headers=auth_headers(token),
    )
    bad_tender_id = bad_tender.json()["id"]
    good_tender = await client.post(
        f"{base}/{shift_id}/tenders",
        json={"payment_method_id": str(cash_payment_method.id), "amount": "140000"},
        headers=auth_headers(token),
    )
    assert good_tender.status_code == 201

    reverse_resp = await client.patch(
        f"{base}/{shift_id}/tenders/{bad_tender_id}/reverse",
        json={"reason": "fat-fingered amount, entered 999999 instead of nothing"},
        headers=auth_headers(token),
    )
    assert reverse_resp.status_code == 200, reverse_resp.text

    recon_resp = await client.post(
        f"{base}/{shift_id}/reconciliation",
        json={"actual_physical_cash": "140000"},
        headers=auth_headers(token),
    )
    assert recon_resp.status_code == 201, recon_resp.text
    assert recon_resp.json()["total_tender_amount"] == "140000.00"  # the bad one excluded


async def test_reversing_an_already_reversed_tender_is_rejected(
    client: AsyncClient, owner_user, org, station, cash_payment_method
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)
    shift = (await client.post(base, json={}, headers=auth_headers(token))).json()
    shift_id = shift["id"]
    tender = await client.post(
        f"{base}/{shift_id}/tenders",
        json={"payment_method_id": str(cash_payment_method.id), "amount": "1000"},
        headers=auth_headers(token),
    )
    tender_id = tender.json()["id"]

    first = await client.patch(
        f"{base}/{shift_id}/tenders/{tender_id}/reverse", json={"reason": "mistake"}, headers=auth_headers(token)
    )
    assert first.status_code == 200
    second = await client.patch(
        f"{base}/{shift_id}/tenders/{tender_id}/reverse", json={"reason": "mistake again"}, headers=auth_headers(token)
    )
    assert second.status_code == 409


async def test_reversed_cash_movement_cannot_then_be_approved(
    client: AsyncClient, owner_user, org, station
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)
    shift = (await client.post(base, json={}, headers=auth_headers(token))).json()
    shift_id = shift["id"]
    movement = await client.post(
        f"{base}/{shift_id}/cash-movements",
        json={"movement_type": "expense", "amount": "500", "reason": "x"},
        headers=auth_headers(token),
    )
    movement_id = movement.json()["id"]

    reverse_resp = await client.patch(
        f"{base}/{shift_id}/cash-movements/{movement_id}/reverse",
        json={"reason": "recorded by mistake"},
        headers=auth_headers(token),
    )
    assert reverse_resp.status_code == 200

    approve_resp = await client.patch(
        f"{base}/{shift_id}/cash-movements/{movement_id}/approve", headers=auth_headers(token)
    )
    assert approve_resp.status_code == 409


# ---------------------------------------------------------------------------
# Amendments - correcting an already-approved reconciliation
# ---------------------------------------------------------------------------


async def test_amendment_corrects_an_approved_reconciliation_without_editing_the_original_silently(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, fuel_price, cash_payment_method
):
    from tests.test_shift_reconciliation import _closed_shift

    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)
    shift_id = await _closed_shift(client, token, org, station, tank_with_stock, nozzle, litres="500")
    await client.post(
        f"{base}/{shift_id}/tenders",
        json={"payment_method_id": str(cash_payment_method.id), "amount": "140000"},
        headers=auth_headers(token),
    )
    await client.post(
        f"{base}/{shift_id}/reconciliation",
        json={"actual_physical_cash": "140000"},
        headers=auth_headers(token),
    )
    approve_resp = await client.patch(f"{base}/{shift_id}/approve", headers=auth_headers(token))
    assert approve_resp.status_code == 200, approve_resp.text

    amend_resp = await client.post(
        f"{base}/{shift_id}/reconciliation/amendments",
        json={
            "field_name": "actual_physical_cash",
            "new_value": "140050",
            "reason": "Recount found an extra note stuck to the drawer",
        },
        headers=auth_headers(token),
    )
    assert amend_resp.status_code == 201, amend_resp.text
    amendment_id = amend_resp.json()["id"]
    assert amend_resp.json()["previous_value"] == "140000.00"
    assert amend_resp.json()["status"] == "pending"

    # Not yet applied - the reconciliation is untouched until approved.
    unchanged = await client.get(f"{base}/{shift_id}/reconciliation", headers=auth_headers(token))
    assert unchanged.json()["actual_physical_cash"] == "140000.00"

    approve_amend_resp = await client.patch(
        f"{base}/{shift_id}/reconciliation/amendments/{amendment_id}/approve", headers=auth_headers(token)
    )
    assert approve_amend_resp.status_code == 200, approve_amend_resp.text

    after_resp = await client.get(f"{base}/{shift_id}/reconciliation", headers=auth_headers(token))
    after = after_resp.json()
    assert after["actual_physical_cash"] == "140050.00"
    assert after["cash_shortage_excess"] == "50.00"
    # The original authorization state (none needed here) is untouched by
    # the amendment; only the amended figures recompute.
    assert after["authorized_by_user_id"] is None


async def test_amendment_on_a_non_amendable_field_is_rejected(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, fuel_price, cash_payment_method
):
    from tests.test_shift_reconciliation import _closed_shift

    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)
    shift_id = await _closed_shift(client, token, org, station, tank_with_stock, nozzle, litres="500")
    await client.post(
        f"{base}/{shift_id}/tenders",
        json={"payment_method_id": str(cash_payment_method.id), "amount": "140000"},
        headers=auth_headers(token),
    )
    await client.post(
        f"{base}/{shift_id}/reconciliation",
        json={"actual_physical_cash": "140000"},
        headers=auth_headers(token),
    )
    resp = await client.post(
        f"{base}/{shift_id}/reconciliation/amendments",
        json={
            "field_name": "expected_fuel_revenue",
            "new_value": "999999",
            "reason": "I just feel like it should be higher",
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 422


async def test_rejecting_an_amendment_requires_a_reason_and_leaves_reconciliation_untouched(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, fuel_price, cash_payment_method
):
    from tests.test_shift_reconciliation import _closed_shift

    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)
    shift_id = await _closed_shift(client, token, org, station, tank_with_stock, nozzle, litres="500")
    await client.post(
        f"{base}/{shift_id}/tenders",
        json={"payment_method_id": str(cash_payment_method.id), "amount": "140000"},
        headers=auth_headers(token),
    )
    await client.post(
        f"{base}/{shift_id}/reconciliation",
        json={"actual_physical_cash": "140000"},
        headers=auth_headers(token),
    )
    amend_resp = await client.post(
        f"{base}/{shift_id}/reconciliation/amendments",
        json={"field_name": "actual_physical_cash", "new_value": "1", "reason": "test"},
        headers=auth_headers(token),
    )
    amendment_id = amend_resp.json()["id"]

    no_reason_resp = await client.patch(
        f"{base}/{shift_id}/reconciliation/amendments/{amendment_id}/reject", json={}, headers=auth_headers(token)
    )
    assert no_reason_resp.status_code == 422

    reject_resp = await client.patch(
        f"{base}/{shift_id}/reconciliation/amendments/{amendment_id}/reject",
        json={"rejection_reason": "Not a real discrepancy, recount confirmed original figure"},
        headers=auth_headers(token),
    )
    assert reject_resp.status_code == 200
    assert reject_resp.json()["status"] == "rejected"

    unchanged = await client.get(f"{base}/{shift_id}/reconciliation", headers=auth_headers(token))
    assert unchanged.json()["actual_physical_cash"] == "140000.00"
