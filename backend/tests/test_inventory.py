import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers, login

pytestmark = pytest.mark.asyncio


def _items_base(org, station) -> str:
    return f"/organizations/{org.id}/stations/{station.id}/inventory-items"


def _movements_base(org, station) -> str:
    return f"/organizations/{org.id}/stations/{station.id}/inventory-movements"


async def test_brand_new_item_reports_zero_on_hand_with_consistent_formatting(
    client: AsyncClient, owner_user, org, station, inventory_item
):
    """A coalesce(sum(...), 0) over zero ledger rows must still report the
    same 3-decimal shape as a real sum ("0.000", not "0") - caught live
    while e2e-testing the dashboard (on_hand rendered as "0" before any
    movement, "17.000" after one)."""
    token = await login(client, "owner@acmefuel-dev.com")
    listing = await client.get(_items_base(org, station), headers=auth_headers(token))
    row = next(r for r in listing.json() if r["id"] == str(inventory_item.id))
    assert row["on_hand"] == "0.000"


async def test_receipt_then_sale_computes_correct_on_hand(
    client: AsyncClient, owner_user, org, station, inventory_item
):
    token = await login(client, "owner@acmefuel-dev.com")
    mbase = _movements_base(org, station)

    receipt = await client.post(
        mbase,
        json={"inventory_item_id": str(inventory_item.id), "movement_type": "receipt", "quantity": "20", "amount": "4000.00"},
        headers=auth_headers(token),
    )
    assert receipt.status_code == 201, receipt.text

    sale = await client.post(
        mbase,
        json={"inventory_item_id": str(inventory_item.id), "movement_type": "sale", "quantity": "3", "amount": "900.00"},
        headers=auth_headers(token),
    )
    assert sale.status_code == 201, sale.text

    listing = await client.get(_items_base(org, station), headers=auth_headers(token))
    row = next(r for r in listing.json() if r["id"] == str(inventory_item.id))
    assert row["on_hand"] == "17.000"
    assert row["below_reorder_level"] is False


async def test_decreasing_movement_beyond_on_hand_is_rejected(
    client: AsyncClient, owner_user, org, station, inventory_item
):
    token = await login(client, "owner@acmefuel-dev.com")
    resp = await client.post(
        _movements_base(org, station),
        json={"inventory_item_id": str(inventory_item.id), "movement_type": "issue", "quantity": "5"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 422
    assert "Insufficient stock" in resp.json()["detail"]


async def test_adjustment_without_reason_is_rejected(
    client: AsyncClient, owner_user, org, station, inventory_item
):
    token = await login(client, "owner@acmefuel-dev.com")
    await client.post(
        _movements_base(org, station),
        json={"inventory_item_id": str(inventory_item.id), "movement_type": "receipt", "quantity": "10"},
        headers=auth_headers(token),
    )
    resp = await client.post(
        _movements_base(org, station),
        json={"inventory_item_id": str(inventory_item.id), "movement_type": "adjustment_decrease", "quantity": "1"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 422
    assert "reason" in resp.json()["detail"].lower()


async def test_below_reorder_level_flag(client: AsyncClient, owner_user, org, station, inventory_item):
    # reorder_level is 10 (see tests/conftest.py's inventory_item fixture).
    token = await login(client, "owner@acmefuel-dev.com")
    await client.post(
        _movements_base(org, station),
        json={"inventory_item_id": str(inventory_item.id), "movement_type": "receipt", "quantity": "5"},
        headers=auth_headers(token),
    )
    listing = await client.get(_items_base(org, station), headers=auth_headers(token))
    row = next(r for r in listing.json() if r["id"] == str(inventory_item.id))
    assert row["on_hand"] == "5.000"
    assert row["below_reorder_level"] is True


async def test_duplicate_sku_at_same_station_is_rejected(client: AsyncClient, owner_user, org, station, inventory_item):
    token = await login(client, "owner@acmefuel-dev.com")
    resp = await client.post(
        _items_base(org, station),
        json={"sku": inventory_item.sku, "name": "Duplicate", "unit": "bottle"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 409


async def test_cashier_can_record_sale_but_not_adjustment(
    client: AsyncClient, owner_user, cashier_user, org, station, inventory_item
):
    owner_token = await login(client, "owner@acmefuel-dev.com")
    await client.post(
        _movements_base(org, station),
        json={"inventory_item_id": str(inventory_item.id), "movement_type": "receipt", "quantity": "10"},
        headers=auth_headers(owner_token),
    )

    cashier_token = await login(client, "cashier@acmefuel-dev.com")
    sale = await client.post(
        _movements_base(org, station),
        json={"inventory_item_id": str(inventory_item.id), "movement_type": "sale", "quantity": "1", "amount": "50"},
        headers=auth_headers(cashier_token),
    )
    assert sale.status_code == 201, sale.text

    adjust = await client.post(
        _movements_base(org, station),
        json={
            "inventory_item_id": str(inventory_item.id),
            "movement_type": "adjustment_decrease",
            "quantity": "1",
            "reason": "damaged stock",
        },
        headers=auth_headers(cashier_token),
    )
    assert adjust.status_code == 403
