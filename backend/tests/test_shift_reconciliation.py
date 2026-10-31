from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers, login

pytestmark = pytest.mark.asyncio


def _base(org, station) -> str:
    return f"/organizations/{org.id}/stations/{station.id}/shifts"


async def _closed_shift(
    client: AsyncClient, token: str, org, station, tank_with_stock, nozzle, *, litres: str = "500"
) -> str:
    base = _base(org, station)
    shift = (await client.post(base, json={}, headers=auth_headers(token))).json()
    shift_id = shift["id"]

    await client.post(
        f"{base}/{shift_id}/tank-readings/opening",
        json={"tank_id": str(tank_with_stock.id), "dip_reading": "10000"},
        headers=auth_headers(token),
    )
    nr = (
        await client.post(
            f"{base}/{shift_id}/nozzle-readings",
            json={"nozzle_id": str(nozzle.id), "opening_totalizer": "5000"},
            headers=auth_headers(token),
        )
    ).json()
    closing_totalizer = str(Decimal("5000") + Decimal(litres))
    close_resp = await client.patch(
        f"{base}/{shift_id}/nozzle-readings/{nr['id']}/close",
        json={"closing_totalizer": closing_totalizer},
        headers=auth_headers(token),
    )
    assert close_resp.status_code == 200, close_resp.text
    closing_dip = str(Decimal("10000") - Decimal(litres))
    await client.post(
        f"{base}/{shift_id}/tank-readings/closing",
        json={"tank_id": str(tank_with_stock.id), "dip_reading": closing_dip},
        headers=auth_headers(token),
    )
    close_shift_resp = await client.patch(f"{base}/{shift_id}/close", headers=auth_headers(token))
    assert close_shift_resp.status_code == 200, close_shift_resp.text
    return shift_id


# ---------------------------------------------------------------------------
# Expected revenue calculation
# ---------------------------------------------------------------------------


async def test_expected_revenue_is_litres_times_price_with_no_price_change(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, fuel_price, cash_payment_method
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)
    shift_id = await _closed_shift(client, token, org, station, tank_with_stock, nozzle, litres="500")

    # A tender is needed first, else total_tender_amount=0 trips the
    # material-discrepancy gate before we even get to assert the revenue figure.
    await client.post(
        f"{base}/{shift_id}/tenders",
        json={"payment_method_id": str(cash_payment_method.id), "amount": "140000"},
        headers=auth_headers(token),
    )
    resp = await client.post(
        f"{base}/{shift_id}/reconciliation",
        json={"actual_physical_cash": "140000"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["expected_fuel_revenue"] == "140000.00"  # 500L * 280.00
    assert body["total_tender_amount"] == "140000.00"
    assert body["revenue_variance"] == "0.00"
    assert body["revenue_within_tolerance"] is True


async def test_expected_revenue_splits_across_mid_shift_price_change(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, fuel_price, fuel_grade, cash_payment_method
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)

    now = datetime.now(timezone.utc)
    new_price_resp = await client.post(
        f"/organizations/{org.id}/stations/{station.id}/fuel-prices",
        json={
            "fuel_grade_id": str(fuel_grade.id),
            "price_per_litre": "300.00",
            "effective_from": (now - timedelta(seconds=1)).isoformat(),
        },
        headers=auth_headers(token),
    )
    new_price_id = new_price_resp.json()["id"]

    shift = (await client.post(base, json={}, headers=auth_headers(token))).json()
    shift_id = shift["id"]
    await client.post(
        f"{base}/{shift_id}/tank-readings/opening",
        json={"tank_id": str(tank_with_stock.id), "dip_reading": "10000"},
        headers=auth_headers(token),
    )
    nr = (
        await client.post(
            f"{base}/{shift_id}/nozzle-readings",
            json={"nozzle_id": str(nozzle.id), "opening_totalizer": "5000"},
            headers=auth_headers(token),
        )
    ).json()

    # 100L @ 280 before the change, 200L @ 300 after -> boundary at 5100.
    effective_at = datetime.now(timezone.utc)
    pc_resp = await client.post(
        f"{base}/{shift_id}/price-changes",
        json={"fuel_grade_id": str(fuel_grade.id), "new_price_id": new_price_id, "effective_at": effective_at.isoformat()},
        headers=auth_headers(token),
    )
    assert pc_resp.status_code == 201, pc_resp.text
    price_change_id = pc_resp.json()["id"]
    boundary_resp = await client.post(
        f"{base}/{shift_id}/price-changes/{price_change_id}/readings",
        json={"nozzle_id": str(nozzle.id), "totalizer_reading": "5100"},
        headers=auth_headers(token),
    )
    assert boundary_resp.status_code == 201, boundary_resp.text

    await client.patch(
        f"{base}/{shift_id}/nozzle-readings/{nr['id']}/close",
        json={"closing_totalizer": "5300"},
        headers=auth_headers(token),
    )
    await client.post(
        f"{base}/{shift_id}/tank-readings/closing",
        json={"tank_id": str(tank_with_stock.id), "dip_reading": "9700"},
        headers=auth_headers(token),
    )
    close_resp = await client.patch(f"{base}/{shift_id}/close", headers=auth_headers(token))
    assert close_resp.status_code == 200, close_resp.text

    # 100*280 + 200*300 = 28000 + 60000 = 88000
    await client.post(
        f"{base}/{shift_id}/tenders",
        json={"payment_method_id": str(cash_payment_method.id), "amount": "88000"},
        headers=auth_headers(token),
    )
    recon_resp = await client.post(
        f"{base}/{shift_id}/reconciliation",
        json={"actual_physical_cash": "88000"},
        headers=auth_headers(token),
    )
    assert recon_resp.status_code == 201, recon_resp.text
    assert recon_resp.json()["expected_fuel_revenue"] == "88000.00"


async def test_rounding_half_up_to_two_decimals(
    client: AsyncClient, owner_user, org, station, db, cash_payment_method
):
    """
    333L at a price of 3.335/litre = 1110.555 exactly - round-half-up to 2dp
    must give 1110.56, not 1110.55 (round-half-even) or 1110.5 (truncated).
    """
    from app.core.revenue import round_money

    assert round_money(Decimal("1110.555")) == Decimal("1110.56")
    assert round_money(Decimal("1110.554")) == Decimal("1110.55")
    assert round_money(Decimal("1110.005")) == Decimal("1110.01")


async def test_no_price_set_for_grade_blocks_reconciliation_with_a_clear_error(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, cash_payment_method
):
    """No fuel_price fixture used here on purpose - revenue cannot be
    computed with no price on record, and the API must say so, not guess
    zero or crash."""
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)
    shift_id = await _closed_shift(client, token, org, station, tank_with_stock, nozzle, litres="500")
    await client.post(
        f"{base}/{shift_id}/tenders",
        json={"payment_method_id": str(cash_payment_method.id), "amount": "1000"},
        headers=auth_headers(token),
    )
    resp = await client.post(
        f"{base}/{shift_id}/reconciliation",
        json={"actual_physical_cash": "1000"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 422
    assert "no fuel price" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Tender / cash movement separation - the "don't double count, don't
# confuse deposits with revenue" requirement
# ---------------------------------------------------------------------------


async def test_total_tender_sums_cash_card_and_credit(
    client: AsyncClient,
    owner_user,
    org,
    station,
    tank_with_stock,
    nozzle,
    fuel_price,
    cash_payment_method,
    card_payment_method,
    credit_payment_method,
    credit_customer,
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)
    shift_id = await _closed_shift(client, token, org, station, tank_with_stock, nozzle, litres="500")

    for method, amount in [(cash_payment_method, "80000"), (card_payment_method, "40000"), (credit_payment_method, "20000")]:
        payload = {"payment_method_id": str(method.id), "amount": amount}
        if method.category == "credit":
            payload["credit_customer_id"] = str(credit_customer.id)
        resp = await client.post(f"{base}/{shift_id}/tenders", json=payload, headers=auth_headers(token))
        assert resp.status_code == 201, resp.text

    recon_resp = await client.post(
        f"{base}/{shift_id}/reconciliation",
        json={"actual_physical_cash": "80000"},
        headers=auth_headers(token),
    )
    assert recon_resp.status_code == 201, recon_resp.text
    body = recon_resp.json()
    assert body["total_tender_amount"] == "140000.00"
    assert body["expected_physical_cash"] == "80000.00"  # ONLY the cash-category tender


async def test_expense_is_subtracted_exactly_once_from_expected_cash(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, fuel_price, cash_payment_method
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)
    shift_id = await _closed_shift(client, token, org, station, tank_with_stock, nozzle, litres="500")

    await client.post(
        f"{base}/{shift_id}/cash-movements",
        json={"movement_type": "opening_cash", "amount": "5000", "reason": "float"},
        headers=auth_headers(token),
    )
    expense_resp = await client.post(
        f"{base}/{shift_id}/cash-movements",
        json={"movement_type": "expense", "amount": "500", "reason": "cleaning"},
        headers=auth_headers(token),
    )
    expense_id = expense_resp.json()["id"]
    await client.patch(
        f"{base}/{shift_id}/cash-movements/{expense_id}/approve", headers=auth_headers(token)
    )
    await client.post(
        f"{base}/{shift_id}/tenders",
        json={"payment_method_id": str(cash_payment_method.id), "amount": "140000"},
        headers=auth_headers(token),
    )

    recon_resp = await client.post(
        f"{base}/{shift_id}/reconciliation",
        json={"actual_physical_cash": "144500"},
        headers=auth_headers(token),
    )
    assert recon_resp.status_code == 201, recon_resp.text
    # 5000 (opening) + 140000 (cash tender) - 500 (expense, once) = 144500
    assert recon_resp.json()["expected_physical_cash"] == "144500.00"


async def test_deposit_reduces_expected_cash_but_never_affects_revenue_variance(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, fuel_price, cash_payment_method
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)
    shift_id = await _closed_shift(client, token, org, station, tank_with_stock, nozzle, litres="500")

    await client.post(
        f"{base}/{shift_id}/tenders",
        json={"payment_method_id": str(cash_payment_method.id), "amount": "140000"},
        headers=auth_headers(token),
    )
    deposit_resp = await client.post(
        f"{base}/{shift_id}/cash-movements",
        json={"movement_type": "deposit", "amount": "100000", "reason": "bank deposit"},
        headers=auth_headers(token),
    )
    deposit_id = deposit_resp.json()["id"]
    await client.patch(f"{base}/{shift_id}/cash-movements/{deposit_id}/approve", headers=auth_headers(token))

    recon_resp = await client.post(
        f"{base}/{shift_id}/reconciliation",
        json={"actual_physical_cash": "40000"},
        headers=auth_headers(token),
    )
    assert recon_resp.status_code == 201, recon_resp.text
    body = recon_resp.json()
    assert body["expected_fuel_revenue"] == "140000.00"  # untouched by the deposit
    assert body["revenue_variance"] == "0.00"  # tender total still matches revenue exactly
    assert body["expected_physical_cash"] == "40000.00"  # 140000 - 100000 deposit
    assert body["cash_shortage_excess"] == "0.00"


async def test_unapproved_decreasing_movement_blocks_reconciliation(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, fuel_price, cash_payment_method
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)
    shift_id = await _closed_shift(client, token, org, station, tank_with_stock, nozzle, litres="500")

    await client.post(
        f"{base}/{shift_id}/cash-movements",
        json={"movement_type": "expense", "amount": "500", "reason": "cleaning"},
        headers=auth_headers(token),
    )
    await client.post(
        f"{base}/{shift_id}/tenders",
        json={"payment_method_id": str(cash_payment_method.id), "amount": "140000"},
        headers=auth_headers(token),
    )
    resp = await client.post(
        f"{base}/{shift_id}/reconciliation",
        json={"actual_physical_cash": "139500"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 422
    assert "awaiting approval" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Material discrepancy / authorization gate
# ---------------------------------------------------------------------------


async def test_material_discrepancy_without_explanation_is_rejected(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, fuel_price, cash_payment_method
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)
    shift_id = await _closed_shift(client, token, org, station, tank_with_stock, nozzle, litres="500")
    await client.post(
        f"{base}/{shift_id}/tenders",
        json={"payment_method_id": str(cash_payment_method.id), "amount": "100000"},  # way short of 140000
        headers=auth_headers(token),
    )
    resp = await client.post(
        f"{base}/{shift_id}/reconciliation",
        json={"actual_physical_cash": "100000"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 422
    assert "explanation" in resp.json()["detail"].lower()


async def test_shift_cannot_be_approved_without_reconciliation(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, fuel_price
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)
    shift_id = await _closed_shift(client, token, org, station, tank_with_stock, nozzle, litres="500")
    resp = await client.patch(f"{base}/{shift_id}/approve", headers=auth_headers(token))
    assert resp.status_code == 422
    assert "reconciliation" in resp.json()["detail"].lower()


async def test_shift_cannot_be_approved_while_material_discrepancy_unauthorized(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, fuel_price, cash_payment_method
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)
    shift_id = await _closed_shift(client, token, org, station, tank_with_stock, nozzle, litres="500")
    await client.post(
        f"{base}/{shift_id}/tenders",
        json={"payment_method_id": str(cash_payment_method.id), "amount": "100000"},
        headers=auth_headers(token),
    )
    await client.post(
        f"{base}/{shift_id}/reconciliation",
        json={"actual_physical_cash": "100000", "explanation": "investigating"},
        headers=auth_headers(token),
    )
    resp = await client.patch(f"{base}/{shift_id}/approve", headers=auth_headers(token))
    assert resp.status_code == 422
    assert "not yet been authorized" in resp.json()["detail"]

    await client.patch(f"{base}/{shift_id}/reconciliation/authorize", json={}, headers=auth_headers(token))
    resp2 = await client.patch(f"{base}/{shift_id}/approve", headers=auth_headers(token))
    assert resp2.status_code == 200, resp2.text


# ---------------------------------------------------------------------------
# Duplicate submissions
# ---------------------------------------------------------------------------


async def test_duplicate_reconciliation_for_same_shift_is_rejected(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, fuel_price, cash_payment_method
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)
    shift_id = await _closed_shift(client, token, org, station, tank_with_stock, nozzle, litres="500")
    await client.post(
        f"{base}/{shift_id}/tenders",
        json={"payment_method_id": str(cash_payment_method.id), "amount": "140000"},
        headers=auth_headers(token),
    )
    first = await client.post(
        f"{base}/{shift_id}/reconciliation",
        json={"actual_physical_cash": "140000"},
        headers=auth_headers(token),
    )
    assert first.status_code == 201
    second = await client.post(
        f"{base}/{shift_id}/reconciliation",
        json={"actual_physical_cash": "140000"},
        headers=auth_headers(token),
    )
    assert second.status_code == 409


async def test_approving_an_already_approved_cash_movement_is_rejected(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)
    shift = (await client.post(base, json={}, headers=auth_headers(token))).json()
    shift_id = shift["id"]
    expense_resp = await client.post(
        f"{base}/{shift_id}/cash-movements",
        json={"movement_type": "expense", "amount": "500", "reason": "x"},
        headers=auth_headers(token),
    )
    expense_id = expense_resp.json()["id"]
    first = await client.patch(f"{base}/{shift_id}/cash-movements/{expense_id}/approve", headers=auth_headers(token))
    assert first.status_code == 200
    second = await client.patch(f"{base}/{shift_id}/cash-movements/{expense_id}/approve", headers=auth_headers(token))
    assert second.status_code == 409


async def test_authorizing_an_already_authorized_reconciliation_is_rejected(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, fuel_price, cash_payment_method
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)
    shift_id = await _closed_shift(client, token, org, station, tank_with_stock, nozzle, litres="500")
    await client.post(
        f"{base}/{shift_id}/tenders",
        json={"payment_method_id": str(cash_payment_method.id), "amount": "100000"},
        headers=auth_headers(token),
    )
    await client.post(
        f"{base}/{shift_id}/reconciliation",
        json={"actual_physical_cash": "100000", "explanation": "investigating"},
        headers=auth_headers(token),
    )
    first = await client.patch(f"{base}/{shift_id}/reconciliation/authorize", json={}, headers=auth_headers(token))
    assert first.status_code == 200
    second = await client.patch(f"{base}/{shift_id}/reconciliation/authorize", json={}, headers=auth_headers(token))
    assert second.status_code == 409


# ---------------------------------------------------------------------------
# Credit tender validation
# ---------------------------------------------------------------------------


async def test_credit_tender_requires_a_customer(
    client: AsyncClient, owner_user, org, station, credit_payment_method
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)
    shift = (await client.post(base, json={}, headers=auth_headers(token))).json()
    resp = await client.post(
        f"{base}/{shift['id']}/tenders",
        json={"payment_method_id": str(credit_payment_method.id), "amount": "1000"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 422


async def test_non_credit_tender_rejects_a_customer(
    client: AsyncClient, owner_user, org, station, cash_payment_method, credit_customer
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)
    shift = (await client.post(base, json={}, headers=auth_headers(token))).json()
    resp = await client.post(
        f"{base}/{shift['id']}/tenders",
        json={
            "payment_method_id": str(cash_payment_method.id),
            "amount": "1000",
            "credit_customer_id": str(credit_customer.id),
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 422
