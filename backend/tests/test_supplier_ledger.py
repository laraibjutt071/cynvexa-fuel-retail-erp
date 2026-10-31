from decimal import Decimal

import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers, login

pytestmark = pytest.mark.asyncio


def _base(org, supplier) -> str:
    return f"/organizations/{org.id}/suppliers/{supplier.id}"


async def test_supplier_with_no_invoices_reports_zero_with_consistent_formatting(
    client: AsyncClient, owner_user, org, supplier
):
    token = await login(client, "owner@acmefuel-dev.com")
    balance = await client.get(f"{_base(org, supplier)}/balance", headers=auth_headers(token))
    assert balance.json()["balance"] == "0.00"


async def test_invoice_then_approved_payment_reduces_balance(
    client: AsyncClient, owner_user, org, supplier
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, supplier)

    inv = await client.post(
        f"{base}/invoices",
        json={"amount": "50000.00", "invoice_date": "2026-01-01", "description": "Diesel delivery"},
        headers=auth_headers(token),
    )
    assert inv.status_code == 201, inv.text

    balance = await client.get(f"{base}/balance", headers=auth_headers(token))
    assert balance.json()["balance"] == "50000.00"

    pay = await client.post(
        f"{base}/payments",
        json={"amount": "20000.00", "payment_date": "2026-01-02"},
        headers=auth_headers(token),
    )
    assert pay.status_code == 201, pay.text
    payment_id = pay.json()["id"]

    # Unapproved payment must not reduce the balance yet.
    balance = await client.get(f"{base}/balance", headers=auth_headers(token))
    assert balance.json()["balance"] == "50000.00"

    approve = await client.patch(f"{base}/payments/{payment_id}/approve", headers=auth_headers(token))
    assert approve.status_code == 200, approve.text

    balance = await client.get(f"{base}/balance", headers=auth_headers(token))
    assert balance.json()["balance"] == "30000.00"


async def test_reversed_payment_is_excluded_from_balance(
    client: AsyncClient, owner_user, org, supplier
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, supplier)

    await client.post(
        f"{base}/invoices",
        json={"amount": "10000.00", "invoice_date": "2026-01-01"},
        headers=auth_headers(token),
    )
    pay = await client.post(
        f"{base}/payments", json={"amount": "4000.00", "payment_date": "2026-01-02"}, headers=auth_headers(token)
    )
    payment_id = pay.json()["id"]
    await client.patch(f"{base}/payments/{payment_id}/approve", headers=auth_headers(token))

    balance = await client.get(f"{base}/balance", headers=auth_headers(token))
    assert balance.json()["balance"] == "6000.00"

    reverse = await client.patch(
        f"{base}/payments/{payment_id}/reverse",
        json={"reason": "Bank rejected the transfer"},
        headers=auth_headers(token),
    )
    assert reverse.status_code == 200, reverse.text

    balance = await client.get(f"{base}/balance", headers=auth_headers(token))
    assert balance.json()["balance"] == "10000.00"


async def test_approving_an_already_approved_payment_is_rejected(
    client: AsyncClient, owner_user, org, supplier
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, supplier)
    await client.post(
        f"{base}/invoices", json={"amount": "1000.00", "invoice_date": "2026-01-01"}, headers=auth_headers(token)
    )
    pay = await client.post(
        f"{base}/payments", json={"amount": "500.00", "payment_date": "2026-01-02"}, headers=auth_headers(token)
    )
    payment_id = pay.json()["id"]
    first = await client.patch(f"{base}/payments/{payment_id}/approve", headers=auth_headers(token))
    assert first.status_code == 200
    second = await client.patch(f"{base}/payments/{payment_id}/approve", headers=auth_headers(token))
    assert second.status_code == 409


async def test_invalid_invoice_amount_is_rejected(client: AsyncClient, owner_user, org, supplier):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, supplier)
    resp = await client.post(
        f"{base}/invoices", json={"amount": "0", "invoice_date": "2026-01-01"}, headers=auth_headers(token)
    )
    assert resp.status_code == 422


async def test_cashier_cannot_record_or_approve_supplier_payments(
    client: AsyncClient, owner_user, cashier_user, org, supplier
):
    owner_token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, supplier)
    await client.post(
        f"{base}/invoices", json={"amount": "1000.00", "invoice_date": "2026-01-01"}, headers=auth_headers(owner_token)
    )

    cashier_token = await login(client, "cashier@acmefuel-dev.com")
    record_resp = await client.post(
        f"{base}/payments", json={"amount": "500.00", "payment_date": "2026-01-02"}, headers=auth_headers(cashier_token)
    )
    assert record_resp.status_code == 403


async def test_list_supplier_balances_across_organization(
    client: AsyncClient, owner_user, org, supplier
):
    token = await login(client, "owner@acmefuel-dev.com")
    await client.post(
        f"{_base(org, supplier)}/invoices",
        json={"amount": "2500.00", "invoice_date": "2026-01-01"},
        headers=auth_headers(token),
    )
    resp = await client.get(f"/organizations/{org.id}/suppliers/balances", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert any(r["supplier_id"] == str(supplier.id) and r["balance"] == "2500.00" for r in rows)
