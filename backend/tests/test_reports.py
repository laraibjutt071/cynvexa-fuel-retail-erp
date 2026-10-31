from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers, login

pytestmark = pytest.mark.asyncio

# A shift opens at utcnow() when created - this brackets "today" with a
# couple of days of margin on each side, well within the report's own
# 366-day cap, rather than hardcoding a date range that could miss
# whatever day the suite actually runs on.
_DATE_FROM = (datetime.now(timezone.utc) - timedelta(days=2)).date().isoformat()
_DATE_TO = (datetime.now(timezone.utc) + timedelta(days=2)).date().isoformat()


def _shifts_base(org, station) -> str:
    return f"/organizations/{org.id}/stations/{station.id}/shifts"


def _reports_base(org, station) -> str:
    return f"/organizations/{org.id}/stations/{station.id}/reports"


async def _full_approved_shift(
    client: AsyncClient, token: str, org, station, tank_with_stock, nozzle, cash_payment_method, *, litres="800"
) -> str:
    base = _shifts_base(org, station)
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
    await client.patch(
        f"{base}/{shift_id}/nozzle-readings/{nr['id']}/close",
        json={"closing_totalizer": closing_totalizer},
        headers=auth_headers(token),
    )
    closing_dip = str(Decimal("10000") - Decimal(litres))
    await client.post(
        f"{base}/{shift_id}/tank-readings/closing",
        json={"tank_id": str(tank_with_stock.id), "dip_reading": closing_dip},
        headers=auth_headers(token),
    )
    await client.patch(f"{base}/{shift_id}/close", headers=auth_headers(token))

    expected_revenue = str(Decimal(litres) * Decimal("280.00"))
    await client.post(
        f"{base}/{shift_id}/tenders",
        json={"payment_method_id": str(cash_payment_method.id), "amount": expected_revenue},
        headers=auth_headers(token),
    )
    recon = await client.post(
        f"{base}/{shift_id}/reconciliation",
        json={"actual_physical_cash": expected_revenue},
        headers=auth_headers(token),
    )
    assert recon.status_code == 201, recon.text
    approve = await client.patch(f"{base}/{shift_id}/approve", headers=auth_headers(token))
    assert approve.status_code == 200, approve.text
    return shift_id


async def test_daily_fuel_sales_report_matches_shift_figures(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, fuel_grade, fuel_price, cash_payment_method
):
    token = await login(client, "owner@acmefuel-dev.com")
    await _full_approved_shift(client, token, org, station, tank_with_stock, nozzle, cash_payment_method)

    resp = await client.get(
        f"{_reports_base(org, station)}/daily-fuel-sales?date_from={_DATE_FROM}&date_to={_DATE_TO}",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    days = resp.json()
    assert len(days) == 1
    day = days[0]
    assert day["shift_count"] == 1
    assert day["total_litres_sold"] == "800.000"
    assert day["total_expected_revenue"] == "224000.00"
    assert day["total_tender_amount"] == "224000.00"
    grade_row = day["grades"][0]
    assert grade_row["fuel_grade_id"] == str(fuel_grade.id)
    assert grade_row["litres_sold"] == "800.000"
    assert grade_row["expected_revenue"] == "224000.00"


async def test_daily_fuel_sales_csv_export_matches_json(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, fuel_price, cash_payment_method
):
    token = await login(client, "owner@acmefuel-dev.com")
    await _full_approved_shift(client, token, org, station, tank_with_stock, nozzle, cash_payment_method)

    resp = await client.get(
        f"{_reports_base(org, station)}/daily-fuel-sales/export?date_from={_DATE_FROM}&date_to={_DATE_TO}",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    body = resp.text
    assert "224000.00" in body
    assert "800.000" in body


async def test_invalid_date_range_is_rejected(client: AsyncClient, owner_user, org, station):
    token = await login(client, "owner@acmefuel-dev.com")
    resp = await client.get(
        f"{_reports_base(org, station)}/daily-fuel-sales?date_from=2026-02-01&date_to=2026-01-01",
        headers=auth_headers(token),
    )
    assert resp.status_code == 422


async def test_date_range_too_large_is_rejected(client: AsyncClient, owner_user, org, station):
    token = await login(client, "owner@acmefuel-dev.com")
    resp = await client.get(
        f"{_reports_base(org, station)}/daily-fuel-sales?date_from=2020-01-01&date_to=2026-01-01",
        headers=auth_headers(token),
    )
    assert resp.status_code == 422


async def test_tank_variance_report_includes_approved_shift(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, fuel_price, cash_payment_method
):
    token = await login(client, "owner@acmefuel-dev.com")
    shift_id = await _full_approved_shift(client, token, org, station, tank_with_stock, nozzle, cash_payment_method)

    resp = await client.get(
        f"{_reports_base(org, station)}/tank-variance?date_from={_DATE_FROM}&date_to={_DATE_TO}",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["shift_id"] == shift_id
    assert rows[0]["closing_book_stock"] == "9200.000"
    assert rows[0]["within_tolerance"] is True


async def test_shift_reconciliation_report_returns_persisted_figures(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, fuel_price, cash_payment_method
):
    token = await login(client, "owner@acmefuel-dev.com")
    await _full_approved_shift(client, token, org, station, tank_with_stock, nozzle, cash_payment_method)

    resp = await client.get(
        f"{_reports_base(org, station)}/shift-reconciliation?date_from={_DATE_FROM}&date_to={_DATE_TO}",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["expected_fuel_revenue"] == "224000.00"
    assert rows[0]["requires_authorization"] is False


async def test_pending_approvals_counts_reflect_real_records(
    client: AsyncClient, owner_user, org, station
):
    token = await login(client, "owner@acmefuel-dev.com")
    before = await client.get(f"/organizations/{org.id}/reports/pending-approvals", headers=auth_headers(token))
    assert before.status_code == 200
    assert before.json()["pending_expenses"] == 0

    await client.post(
        f"/organizations/{org.id}/expenses",
        json={"category": "misc", "description": "x", "amount": "10", "expense_date": "2026-01-01"},
        headers=auth_headers(token),
    )

    after = await client.get(f"/organizations/{org.id}/reports/pending-approvals", headers=auth_headers(token))
    assert after.json()["pending_expenses"] == 1


async def test_pending_approvals_reflects_low_stock_item(
    client: AsyncClient, owner_user, org, station, inventory_item
):
    token = await login(client, "owner@acmefuel-dev.com")
    # reorder_level is 10 - 5 on hand is below it.
    await client.post(
        f"/organizations/{org.id}/stations/{station.id}/inventory-movements",
        json={"inventory_item_id": str(inventory_item.id), "movement_type": "receipt", "quantity": "5"},
        headers=auth_headers(token),
    )
    resp = await client.get(f"/organizations/{org.id}/reports/pending-approvals", headers=auth_headers(token))
    assert resp.json()["low_stock_inventory_items"] == 1


async def test_cashier_cannot_read_reports(client: AsyncClient, cashier_user, org, station):
    token = await login(client, "cashier@acmefuel-dev.com")
    resp = await client.get(
        f"{_reports_base(org, station)}/daily-fuel-sales?date_from={_DATE_FROM}&date_to={_DATE_TO}",
        headers=auth_headers(token),
    )
    assert resp.status_code == 403


async def test_audit_log_filter_by_action_and_export(client: AsyncClient, owner_user, org):
    token = await login(client, "owner@acmefuel-dev.com")
    await client.post(
        f"/organizations/{org.id}/expenses",
        json={"category": "misc", "description": "x", "amount": "10", "expense_date": "2026-01-01"},
        headers=auth_headers(token),
    )
    resp = await client.get(
        f"/organizations/{org.id}/audit-log?action=expense.create", headers=auth_headers(token)
    )
    assert resp.status_code == 200
    assert all(r["action"] == "expense.create" for r in resp.json())
    assert len(resp.json()) >= 1

    export = await client.get(f"/organizations/{org.id}/audit-log/export", headers=auth_headers(token))
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("text/csv")
    assert "expense.create" in export.text
