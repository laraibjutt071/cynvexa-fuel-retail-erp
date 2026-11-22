from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers, login

pytestmark = pytest.mark.asyncio


def _cbase(org, credit_customer) -> str:
    return f"/organizations/{org.id}/credit-customers/{credit_customer.id}"


def _sbase(org, station) -> str:
    return f"/organizations/{org.id}/stations/{station.id}/shifts"


async def _closed_shift_with_credit_tender(
    client: AsyncClient,
    token: str,
    org,
    station,
    tank_with_stock,
    nozzle,
    credit_payment_method,
    credit_customer,
    *,
    amount: str,
) -> str:
    base = _sbase(org, station)
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
    await client.patch(
        f"{base}/{shift_id}/nozzle-readings/{nr['id']}/close",
        json={"closing_totalizer": "5800"},
        headers=auth_headers(token),
    )
    await client.post(
        f"{base}/{shift_id}/tank-readings/closing",
        json={"tank_id": str(tank_with_stock.id), "dip_reading": "9200"},
        headers=auth_headers(token),
    )
    await client.patch(f"{base}/{shift_id}/close", headers=auth_headers(token))
    tender = await client.post(
        f"{base}/{shift_id}/tenders",
        json={
            "payment_method_id": str(credit_payment_method.id),
            "amount": amount,
            "credit_customer_id": str(credit_customer.id),
        },
        headers=auth_headers(token),
    )
    assert tender.status_code == 201, tender.text
    return shift_id


async def test_customer_with_no_sales_reports_zero_with_consistent_formatting(
    client: AsyncClient, owner_user, org, credit_customer
):
    token = await login(client, "owner@acmefuel-dev.com")
    balance = await client.get(f"{_cbase(org, credit_customer)}/balance", headers=auth_headers(token))
    assert balance.json()["balance"] == "0.00"


async def test_credit_sale_then_collection_reduces_balance(
    client: AsyncClient,
    owner_user,
    org,
    station,
    tank_with_stock,
    nozzle,
    fuel_price,
    credit_payment_method,
    credit_customer,
):
    token = await login(client, "owner@acmefuel-dev.com")
    await _closed_shift_with_credit_tender(
        client, token, org, station, tank_with_stock, nozzle, credit_payment_method, credit_customer, amount="224000"
    )

    base = _cbase(org, credit_customer)
    balance = await client.get(f"{base}/balance", headers=auth_headers(token))
    assert balance.json()["balance"] == "224000.00"

    pay = await client.post(
        f"{base}/payments", json={"amount": "100000.00", "payment_date": "2026-01-02"}, headers=auth_headers(token)
    )
    assert pay.status_code == 201, pay.text

    balance = await client.get(f"{base}/balance", headers=auth_headers(token))
    assert balance.json()["balance"] == "124000.00"


async def test_reversed_collection_is_excluded_from_balance(
    client: AsyncClient,
    owner_user,
    org,
    station,
    tank_with_stock,
    nozzle,
    fuel_price,
    credit_payment_method,
    credit_customer,
):
    token = await login(client, "owner@acmefuel-dev.com")
    await _closed_shift_with_credit_tender(
        client, token, org, station, tank_with_stock, nozzle, credit_payment_method, credit_customer, amount="50000"
    )
    base = _cbase(org, credit_customer)
    pay = await client.post(
        f"{base}/payments", json={"amount": "20000.00", "payment_date": "2026-01-02"}, headers=auth_headers(token)
    )
    payment_id = pay.json()["id"]

    balance = await client.get(f"{base}/balance", headers=auth_headers(token))
    assert balance.json()["balance"] == "30000.00"

    reverse = await client.patch(
        f"{base}/payments/{payment_id}/reverse",
        json={"reason": "Entered against the wrong customer"},
        headers=auth_headers(token),
    )
    assert reverse.status_code == 200, reverse.text

    balance = await client.get(f"{base}/balance", headers=auth_headers(token))
    assert balance.json()["balance"] == "50000.00"


async def test_reversing_an_already_reversed_collection_is_rejected(
    client: AsyncClient, owner_user, org, credit_customer
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _cbase(org, credit_customer)
    pay = await client.post(
        f"{base}/payments", json={"amount": "100.00", "payment_date": "2026-01-02"}, headers=auth_headers(token)
    )
    payment_id = pay.json()["id"]
    first = await client.patch(
        f"{base}/payments/{payment_id}/reverse", json={"reason": "duplicate entry"}, headers=auth_headers(token)
    )
    assert first.status_code == 200
    second = await client.patch(
        f"{base}/payments/{payment_id}/reverse", json={"reason": "duplicate entry"}, headers=auth_headers(token)
    )
    assert second.status_code == 409


async def test_cashier_cannot_record_collections(client: AsyncClient, cashier_user, org, credit_customer):
    token = await login(client, "cashier@acmefuel-dev.com")
    resp = await client.post(
        f"{_cbase(org, credit_customer)}/payments",
        json={"amount": "100.00", "payment_date": "2026-01-02"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 403


async def test_ageing_report_reflects_unpaid_balance_in_current_bucket(
    client: AsyncClient,
    owner_user,
    org,
    station,
    tank_with_stock,
    nozzle,
    fuel_price,
    credit_payment_method,
    credit_customer,
):
    """Regression test: list_credit_customer_ageing() used to reference
    ShiftTender.created_at, a field that doesn't exist on that model (it's
    recorded_at) - every call 500'd. Never caught because nothing tested
    this endpoint at all."""
    token = await login(client, "owner@acmefuel-dev.com")
    await _closed_shift_with_credit_tender(
        client, token, org, station, tank_with_stock, nozzle, credit_payment_method, credit_customer, amount="42280"
    )

    resp = await client.get(f"/organizations/{org.id}/credit-customers/ageing", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    row = next(r for r in rows if r["credit_customer_id"] == str(credit_customer.id))
    # A sale recorded moments ago is unpaid and <=30 days old: it belongs
    # entirely in "current", every other bucket empty, total unchanged.
    assert row["current"] == "42280.00"
    assert row["days_30"] == row["days_60"] == row["days_90"] == row["over_90"] == "0.00"
    assert row["total"] == "42280.00"


async def test_statement_lists_sale_and_payment_with_correct_running_balance(
    client: AsyncClient,
    owner_user,
    org,
    station,
    tank_with_stock,
    nozzle,
    fuel_price,
    credit_payment_method,
    credit_customer,
):
    """Regression test: get_credit_customer_statement() had the same
    ShiftTender.created_at bug in three places - every call 500'd."""
    token = await login(client, "owner@acmefuel-dev.com")
    await _closed_shift_with_credit_tender(
        client, token, org, station, tank_with_stock, nozzle, credit_payment_method, credit_customer, amount="62280"
    )
    base = _cbase(org, credit_customer)
    today = datetime.now(timezone.utc).date()
    pay = await client.post(
        f"{base}/payments", json={"amount": "20000.00", "payment_date": today.isoformat()}, headers=auth_headers(token)
    )
    assert pay.status_code == 201, pay.text

    start = (today - timedelta(days=1)).isoformat()
    end = (today + timedelta(days=1)).isoformat()
    resp = await client.get(
        f"{base}/statement?start_date={start}&end_date={end}", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["opening_balance"] == "0.00"
    assert body["closing_balance"] == "42280.00"
    assert len(body["entries"]) == 2
    assert body["entries"][0]["debit"] == "62280.00"
    assert body["entries"][0]["running_balance"] == "62280.00"
    assert body["entries"][1]["credit"] == "20000.00"
    assert body["entries"][1]["running_balance"] == "42280.00"
