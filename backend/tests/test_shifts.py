from decimal import Decimal

import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers, login

pytestmark = pytest.mark.asyncio


def _base(org, station) -> str:
    return f"/organizations/{org.id}/stations/{station.id}/shifts"


async def _open_shift_with_readings(
    client: AsyncClient,
    token: str,
    org,
    station,
    tank_with_stock,
    nozzle,
    *,
    opening_dip="10000",
    closing_dip="9200",
    opening_totalizer="5000",
    closing_totalizer="5800",
):
    base = _base(org, station)
    shift = (
        await client.post(base, json={"label": "Morning"}, headers=auth_headers(token))
    ).json()
    shift_id = shift["id"]

    await client.post(
        f"{base}/{shift_id}/tank-readings/opening",
        json={"tank_id": str(tank_with_stock.id), "dip_reading": opening_dip},
        headers=auth_headers(token),
    )
    nr = (
        await client.post(
            f"{base}/{shift_id}/nozzle-readings",
            json={"nozzle_id": str(nozzle.id), "opening_totalizer": opening_totalizer},
            headers=auth_headers(token),
        )
    ).json()

    if closing_dip is not None:
        await client.post(
            f"{base}/{shift_id}/tank-readings/closing",
            json={"tank_id": str(tank_with_stock.id), "dip_reading": closing_dip},
            headers=auth_headers(token),
        )
    if closing_totalizer is not None:
        await client.patch(
            f"{base}/{shift_id}/nozzle-readings/{nr['id']}/close",
            json={"closing_totalizer": closing_totalizer},
            headers=auth_headers(token),
        )
    return shift_id, nr["id"]


async def _reconcile(
    client: AsyncClient, token: str, org, station, shift_id: str, cash_payment_method, expected_revenue: str
):
    """
    Phase D made financial reconciliation a precondition of final shift
    approval (see shifts.py::approve_shift). These tests predate Phase D and
    only care about the OPERATIONAL outcome of approval (did the ledger
    post, was a duplicate rejected, ...) - this helper satisfies the
    financial precondition with a tender that exactly matches expected
    revenue (zero variance, no explanation/authorization needed) so it
    stays out of the way of what each test actually checks. A "0" expected
    revenue (zero dispensed litres) posts no tender at all, since
    ShiftTender.amount must be > 0.
    """
    base = _base(org, station)
    if expected_revenue != "0":
        await client.post(
            f"{base}/{shift_id}/tenders",
            json={"payment_method_id": str(cash_payment_method.id), "amount": expected_revenue},
            headers=auth_headers(token),
        )
    recon_resp = await client.post(
        f"{base}/{shift_id}/reconciliation",
        json={"actual_physical_cash": expected_revenue},
        headers=auth_headers(token),
    )
    assert recon_resp.status_code == 201, recon_resp.text
    return recon_resp


async def _reconcile_and_approve(
    client: AsyncClient, token: str, org, station, shift_id: str, cash_payment_method, expected_revenue: str
):
    await _reconcile(client, token, org, station, shift_id, cash_payment_method, expected_revenue)
    base = _base(org, station)
    return await client.patch(f"{base}/{shift_id}/approve", headers=auth_headers(token))


# ---------------------------------------------------------------------------
# Full lifecycle / reconciliation accuracy
# ---------------------------------------------------------------------------


async def test_full_shift_lifecycle_posts_sale_to_ledger(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, fuel_price, cash_payment_method
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)
    shift_id, nr_id = await _open_shift_with_readings(
        client, token, org, station, tank_with_stock, nozzle
    )

    close_resp = await client.patch(f"{base}/{shift_id}/close", headers=auth_headers(token))
    assert close_resp.status_code == 200, close_resp.text
    assert close_resp.json()["status"] == "closed"

    # 800L dispensed * 280.00/L (fuel_price fixture) = 224000.00
    approve_resp = await _reconcile_and_approve(
        client, token, org, station, shift_id, cash_payment_method, "224000"
    )
    assert approve_resp.status_code == 200, approve_resp.text
    assert approve_resp.json()["status"] == "approved"

    tank_resp = await client.get(
        f"/organizations/{org.id}/stations/{station.id}/tanks/{tank_with_stock.id}",
        headers=auth_headers(token),
    )
    # 10000 opening - 800 dispensed (5800 - 5000) = 9200
    assert tank_resp.json()["book_stock"] == "9200.000"


async def test_variance_report_matches_physical_and_book_after_approval(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)
    shift_id, _ = await _open_shift_with_readings(
        client, token, org, station, tank_with_stock, nozzle
    )
    await client.patch(f"{base}/{shift_id}/close", headers=auth_headers(token))
    await client.patch(f"{base}/{shift_id}/approve", headers=auth_headers(token))

    variance_resp = await client.get(f"{base}/{shift_id}/variance", headers=auth_headers(token))
    assert variance_resp.status_code == 200
    tanks = variance_resp.json()["tanks"]
    assert len(tanks) == 1
    tank_variance = tanks[0]
    assert tank_variance["opening_book_stock"] == "10000.000"
    assert tank_variance["closing_book_stock"] == "9200.000"
    assert tank_variance["physical_closing_reading"] == "9200.000"
    assert tank_variance["closing_variance"] == "0.000"
    assert tank_variance["within_tolerance"] is True


async def test_exceptional_litres_reduce_sale_but_still_consume_stock(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, fuel_price, cash_payment_method
):
    """100L of the 800L dispensed is a calibration test draw - book stock
    still drops by the full 800L, but it's posted as two separate ledger
    entries (sale 700 + test_calibration 100), never silently netted."""
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)
    shift_id, nr_id = await _open_shift_with_readings(
        client, token, org, station, tank_with_stock, nozzle
    )

    exceptional_resp = await client.post(
        f"{base}/{shift_id}/exceptional-events",
        json={
            "nozzle_id": str(nozzle.id),
            "event_type": "calibration",
            "litres": "100",
            "reason": "Monthly calibration check",
        },
        headers=auth_headers(token),
    )
    assert exceptional_resp.status_code == 201, exceptional_resp.text

    await client.patch(f"{base}/{shift_id}/close", headers=auth_headers(token))
    # Exceptional litres don't currently reduce expected fuel revenue (see
    # docs/ASSUMPTIONS.md) - revenue is still computed on the full 800L.
    approve_resp = await _reconcile_and_approve(
        client, token, org, station, shift_id, cash_payment_method, "224000"
    )
    assert approve_resp.status_code == 200, approve_resp.text

    tank_resp = await client.get(
        f"/organizations/{org.id}/stations/{station.id}/tanks/{tank_with_stock.id}",
        headers=auth_headers(token),
    )
    assert tank_resp.json()["book_stock"] == "9200.000"  # still 10000 - 800 total


async def test_exceptional_litres_exceeding_dispensed_is_rejected(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)
    shift_id, nr_id = await _open_shift_with_readings(
        client, token, org, station, tank_with_stock, nozzle
    )
    # Dispensed is 800; claim 900 litres of exceptional - impossible.
    await client.post(
        f"{base}/{shift_id}/exceptional-events",
        json={"nozzle_id": str(nozzle.id), "event_type": "test_draw", "litres": "900", "reason": "x"},
        headers=auth_headers(token),
    )
    await client.patch(f"{base}/{shift_id}/close", headers=auth_headers(token))
    resp = await client.patch(f"{base}/{shift_id}/approve", headers=auth_headers(token))
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Boundary cases
# ---------------------------------------------------------------------------


async def test_zero_dispensed_is_a_valid_boundary(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, fuel_price, cash_payment_method
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)
    shift_id, nr_id = await _open_shift_with_readings(
        client,
        token,
        org,
        station,
        tank_with_stock,
        nozzle,
        opening_dip="10000",
        closing_dip="10000",
        opening_totalizer="5000",
        closing_totalizer="5000",
    )
    close_resp = await client.patch(f"{base}/{shift_id}/close", headers=auth_headers(token))
    assert close_resp.status_code == 200
    approve_resp = await _reconcile_and_approve(
        client, token, org, station, shift_id, cash_payment_method, "0"
    )
    assert approve_resp.status_code == 200, approve_resp.text


async def test_variance_exactly_at_tolerance_boundary_is_within_tolerance(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, db
):
    """Station default shift_variance_tolerance_percent is 0.5%. A physical
    closing reading exactly 0.5% off the projected book stock must still
    read as within_tolerance=True (<=, not <)."""
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)
    # Dispensed 0 so closing_book_stock == opening_book_stock == 10000.
    # Physical closing reading off by exactly 50 (0.5% of 10000).
    shift_id, _ = await _open_shift_with_readings(
        client,
        token,
        org,
        station,
        tank_with_stock,
        nozzle,
        opening_dip="10000",
        closing_dip="9950",
        opening_totalizer="5000",
        closing_totalizer="5000",
    )
    await client.patch(f"{base}/{shift_id}/close", headers=auth_headers(token))
    await client.patch(f"{base}/{shift_id}/approve", headers=auth_headers(token))

    variance_resp = await client.get(f"{base}/{shift_id}/variance", headers=auth_headers(token))
    tank_variance = variance_resp.json()["tanks"][0]
    assert Decimal(tank_variance["closing_variance_percent"]) == Decimal("-0.5")
    assert tank_variance["within_tolerance"] is True


# ---------------------------------------------------------------------------
# Invalid readings
# ---------------------------------------------------------------------------


async def test_negative_dispensed_without_meter_event_is_rejected(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)
    shift = (await client.post(base, json={}, headers=auth_headers(token))).json()
    shift_id = shift["id"]
    nr = (
        await client.post(
            f"{base}/{shift_id}/nozzle-readings",
            json={"nozzle_id": str(nozzle.id), "opening_totalizer": "5000"},
            headers=auth_headers(token),
        )
    ).json()

    resp = await client.patch(
        f"{base}/{shift_id}/nozzle-readings/{nr['id']}/close",
        json={"closing_totalizer": "4000"},  # lower than opening, no meter event
        headers=auth_headers(token),
    )
    assert resp.status_code == 422


async def test_meter_event_without_pre_or_post_reading_is_rejected(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)
    shift = (await client.post(base, json={}, headers=auth_headers(token))).json()
    shift_id = shift["id"]
    nr = (
        await client.post(
            f"{base}/{shift_id}/nozzle-readings",
            json={"nozzle_id": str(nozzle.id), "opening_totalizer": "5000"},
            headers=auth_headers(token),
        )
    ).json()

    resp = await client.patch(
        f"{base}/{shift_id}/nozzle-readings/{nr['id']}/close",
        json={"closing_totalizer": "100", "meter_event_type": "rollover"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 422


async def test_closing_shift_blocked_until_all_readings_present(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)
    shift = (await client.post(base, json={}, headers=auth_headers(token))).json()
    shift_id = shift["id"]
    # No tank/nozzle readings recorded at all.
    resp = await client.patch(f"{base}/{shift_id}/close", headers=auth_headers(token))
    assert resp.status_code == 422
    assert "Missing" in resp.json()["detail"]


async def test_insufficient_book_stock_blocks_approval(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, fuel_price, cash_payment_method
):
    """Dispensed (e.g. 20,000L via totalizers) exceeding the tank's actual
    10,000L book stock must be rejected at approval, not silently posted
    into negative stock."""
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)
    shift_id, _ = await _open_shift_with_readings(
        client,
        token,
        org,
        station,
        tank_with_stock,
        nozzle,
        opening_dip="10000",
        closing_dip="0",
        opening_totalizer="0",
        closing_totalizer="20000",
    )
    await client.patch(f"{base}/{shift_id}/close", headers=auth_headers(token))
    # 20000L * 280.00/L - financial reconciliation has no notion of book
    # stock, so it succeeds; the stock-insufficiency check runs later in
    # approve_shift and is what this test actually exercises.
    await _reconcile(client, token, org, station, shift_id, cash_payment_method, "5600000")
    resp = await client.patch(f"{base}/{shift_id}/approve", headers=auth_headers(token))
    assert resp.status_code == 409
    assert "Insufficient book stock" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Duplicate / replayed submissions
# ---------------------------------------------------------------------------


async def test_closing_an_already_closed_shift_is_rejected(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)
    shift_id, _ = await _open_shift_with_readings(
        client, token, org, station, tank_with_stock, nozzle
    )
    await client.patch(f"{base}/{shift_id}/close", headers=auth_headers(token))
    resp = await client.patch(f"{base}/{shift_id}/close", headers=auth_headers(token))
    assert resp.status_code == 409


async def test_approving_an_already_approved_shift_is_rejected(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, fuel_price, cash_payment_method
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)
    shift_id, _ = await _open_shift_with_readings(
        client, token, org, station, tank_with_stock, nozzle
    )
    await client.patch(f"{base}/{shift_id}/close", headers=auth_headers(token))
    first = await _reconcile_and_approve(
        client, token, org, station, shift_id, cash_payment_method, "224000"
    )
    assert first.status_code == 200, first.text
    second = await client.patch(f"{base}/{shift_id}/approve", headers=auth_headers(token))
    assert second.status_code == 409


async def test_duplicate_opening_reading_for_same_tank_is_rejected(
    client: AsyncClient, owner_user, org, station, tank_with_stock
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)
    shift = (await client.post(base, json={}, headers=auth_headers(token))).json()
    shift_id = shift["id"]
    payload = {"tank_id": str(tank_with_stock.id), "dip_reading": "10000"}
    first = await client.post(
        f"{base}/{shift_id}/tank-readings/opening", json=payload, headers=auth_headers(token)
    )
    assert first.status_code == 201
    second = await client.post(
        f"{base}/{shift_id}/tank-readings/opening", json=payload, headers=auth_headers(token)
    )
    assert second.status_code == 409


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------


async def test_cashier_can_open_and_close_but_not_approve(
    client: AsyncClient, cashier_user, org, station, tank_with_stock, nozzle
):
    """Per blueprint §12, Cashier/Operator does shift submission and
    closure, but approval stays with management roles."""
    token = await login(client, "cashier@acmefuel-dev.com")
    base = _base(org, station)
    shift_id, _ = await _open_shift_with_readings(
        client, token, org, station, tank_with_stock, nozzle
    )
    close_resp = await client.patch(f"{base}/{shift_id}/close", headers=auth_headers(token))
    assert close_resp.status_code == 200

    approve_resp = await client.patch(f"{base}/{shift_id}/approve", headers=auth_headers(token))
    assert approve_resp.status_code == 403


async def test_station_manager_can_approve(
    client: AsyncClient, station_manager_user, org, station, tank_with_stock, nozzle, fuel_price, cash_payment_method
):
    token = await login(client, "manager@acmefuel-dev.com")
    base = _base(org, station)
    shift_id, _ = await _open_shift_with_readings(
        client, token, org, station, tank_with_stock, nozzle
    )
    await client.patch(f"{base}/{shift_id}/close", headers=auth_headers(token))
    resp = await _reconcile_and_approve(
        client, token, org, station, shift_id, cash_payment_method, "224000"
    )
    assert resp.status_code == 200, resp.text
