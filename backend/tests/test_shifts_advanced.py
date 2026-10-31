import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers, login

pytestmark = pytest.mark.asyncio


def _base(org, station) -> str:
    return f"/organizations/{org.id}/stations/{station.id}/shifts"


# ---------------------------------------------------------------------------
# Meter replacement / reset / rollover
# ---------------------------------------------------------------------------


async def test_meter_rollover_computes_segmented_dispensed_correctly(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)
    shift = (await client.post(base, json={}, headers=auth_headers(token))).json()
    shift_id = shift["id"]

    nr = (
        await client.post(
            f"{base}/{shift_id}/nozzle-readings",
            json={"nozzle_id": str(nozzle.id), "opening_totalizer": "99990"},
            headers=auth_headers(token),
        )
    ).json()

    close_resp = await client.patch(
        f"{base}/{shift_id}/nozzle-readings/{nr['id']}/close",
        json={
            "closing_totalizer": "100",
            "meter_event_type": "rollover",
            "meter_event_pre_reading": "99999",
            "meter_event_post_reading": "0",
            "meter_event_notes": "Rolled past max digits",
        },
        headers=auth_headers(token),
    )
    assert close_resp.status_code == 200, close_resp.text
    # (99999 - 99990) + (100 - 0) = 9 + 100 = 109
    assert close_resp.json()["dispensed_litres"] == "109.000"


async def test_meter_event_with_negative_segment_is_rejected(
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

    # pre_reading (4000) < opening (5000) -> first segment negative.
    resp = await client.patch(
        f"{base}/{shift_id}/nozzle-readings/{nr['id']}/close",
        json={
            "closing_totalizer": "100",
            "meter_event_type": "replacement",
            "meter_event_pre_reading": "4000",
            "meter_event_post_reading": "0",
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 422


async def test_shift_cannot_be_approved_with_unapproved_meter_event(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, fuel_price, cash_payment_method
):
    token = await login(client, "owner@acmefuel-dev.com")
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
            json={"nozzle_id": str(nozzle.id), "opening_totalizer": "99990"},
            headers=auth_headers(token),
        )
    ).json()
    await client.patch(
        f"{base}/{shift_id}/nozzle-readings/{nr['id']}/close",
        json={
            "closing_totalizer": "100",
            "meter_event_type": "rollover",
            "meter_event_pre_reading": "99999",
            "meter_event_post_reading": "0",
        },
        headers=auth_headers(token),
    )
    await client.post(
        f"{base}/{shift_id}/tank-readings/closing",
        json={"tank_id": str(tank_with_stock.id), "dip_reading": "9891"},
        headers=auth_headers(token),
    )
    await client.patch(f"{base}/{shift_id}/close", headers=auth_headers(token))

    approve_resp = await client.patch(f"{base}/{shift_id}/approve", headers=auth_headers(token))
    assert approve_resp.status_code == 422
    assert "meter event" in approve_resp.json()["detail"].lower()

    approve_meter_resp = await client.patch(
        f"{base}/{shift_id}/nozzle-readings/{nr['id']}/approve-meter-event",
        json={},
        headers=auth_headers(token),
    )
    assert approve_meter_resp.status_code == 200

    # (99999 - 99990) + (100 - 0) = 109L dispensed * 280.00/L fuel_price.
    await client.post(
        f"{base}/{shift_id}/tenders",
        json={"payment_method_id": str(cash_payment_method.id), "amount": "30520"},
        headers=auth_headers(token),
    )
    recon_resp = await client.post(
        f"{base}/{shift_id}/reconciliation",
        json={"actual_physical_cash": "30520"},
        headers=auth_headers(token),
    )
    assert recon_resp.status_code == 201, recon_resp.text

    second_approve = await client.patch(f"{base}/{shift_id}/approve", headers=auth_headers(token))
    assert second_approve.status_code == 200, second_approve.text


async def test_approving_the_same_meter_event_twice_is_rejected(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)
    shift = (await client.post(base, json={}, headers=auth_headers(token))).json()
    shift_id = shift["id"]
    nr = (
        await client.post(
            f"{base}/{shift_id}/nozzle-readings",
            json={"nozzle_id": str(nozzle.id), "opening_totalizer": "99990"},
            headers=auth_headers(token),
        )
    ).json()
    await client.patch(
        f"{base}/{shift_id}/nozzle-readings/{nr['id']}/close",
        json={
            "closing_totalizer": "100",
            "meter_event_type": "rollover",
            "meter_event_pre_reading": "99999",
            "meter_event_post_reading": "0",
        },
        headers=auth_headers(token),
    )
    first = await client.patch(
        f"{base}/{shift_id}/nozzle-readings/{nr['id']}/approve-meter-event",
        json={},
        headers=auth_headers(token),
    )
    assert first.status_code == 200
    second = await client.patch(
        f"{base}/{shift_id}/nozzle-readings/{nr['id']}/approve-meter-event",
        json={},
        headers=auth_headers(token),
    )
    assert second.status_code == 409


# ---------------------------------------------------------------------------
# Mid-shift price changes
# ---------------------------------------------------------------------------


async def test_price_change_requires_boundary_reading_before_close_when_required(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, fuel_grade
):
    """Station default require_price_change_reading is True."""
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)

    now = datetime.now(timezone.utc)
    price_resp = await client.post(
        f"/organizations/{org.id}/stations/{station.id}/fuel-prices",
        json={
            "fuel_grade_id": str(fuel_grade.id),
            "price_per_litre": "280.00",
            "effective_from": (now - timedelta(minutes=5)).isoformat(),
        },
        headers=auth_headers(token),
    )
    assert price_resp.status_code == 201
    new_price_id = price_resp.json()["id"]

    shift = (await client.post(base, json={}, headers=auth_headers(token))).json()
    shift_id = shift["id"]
    await client.post(
        f"{base}/{shift_id}/tank-readings/opening",
        json={"tank_id": str(tank_with_stock.id), "dip_reading": "10000"},
        headers=auth_headers(token),
    )
    await client.post(
        f"{base}/{shift_id}/tank-readings/closing",
        json={"tank_id": str(tank_with_stock.id), "dip_reading": "9200"},
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

    # Captured fresh, after the shift was opened - effective_at must fall
    # within [shift.opened_at, now], and the shift was opened well after
    # the `now` variable above was captured.
    effective_at = datetime.now(timezone.utc)
    price_change_resp = await client.post(
        f"{base}/{shift_id}/price-changes",
        json={
            "fuel_grade_id": str(fuel_grade.id),
            "new_price_id": new_price_id,
            "effective_at": effective_at.isoformat(),
        },
        headers=auth_headers(token),
    )
    assert price_change_resp.status_code == 201, price_change_resp.text
    price_change_id = price_change_resp.json()["id"]

    # Close blocked: no boundary reading recorded yet for the affected nozzle.
    close_resp = await client.patch(f"{base}/{shift_id}/close", headers=auth_headers(token))
    assert close_resp.status_code == 422
    assert "boundary" in close_resp.json()["detail"].lower()

    boundary_resp = await client.post(
        f"{base}/{shift_id}/price-changes/{price_change_id}/readings",
        json={"nozzle_id": str(nozzle.id), "totalizer_reading": "5500"},
        headers=auth_headers(token),
    )
    assert boundary_resp.status_code == 201, boundary_resp.text

    close_resp_2 = await client.patch(f"{base}/{shift_id}/close", headers=auth_headers(token))
    assert close_resp_2.status_code == 200, close_resp_2.text


async def test_price_change_reading_not_required_when_station_flag_off(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, fuel_grade
):
    token = await login(client, "owner@acmefuel-dev.com")
    off_resp = await client.patch(
        f"/organizations/{org.id}/stations/{station.id}",
        json={"require_price_change_reading": False},
        headers=auth_headers(token),
    )
    assert off_resp.status_code == 200

    base = _base(org, station)
    now = datetime.now(timezone.utc)
    new_price_id = (
        await client.post(
            f"/organizations/{org.id}/stations/{station.id}/fuel-prices",
            json={
                "fuel_grade_id": str(fuel_grade.id),
                "price_per_litre": "280.00",
                "effective_from": (now - timedelta(minutes=5)).isoformat(),
            },
            headers=auth_headers(token),
        )
    ).json()["id"]

    shift = (await client.post(base, json={}, headers=auth_headers(token))).json()
    shift_id = shift["id"]
    await client.post(
        f"{base}/{shift_id}/tank-readings/opening",
        json={"tank_id": str(tank_with_stock.id), "dip_reading": "10000"},
        headers=auth_headers(token),
    )
    await client.post(
        f"{base}/{shift_id}/tank-readings/closing",
        json={"tank_id": str(tank_with_stock.id), "dip_reading": "9200"},
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
    effective_at = datetime.now(timezone.utc)
    await client.post(
        f"{base}/{shift_id}/price-changes",
        json={
            "fuel_grade_id": str(fuel_grade.id),
            "new_price_id": new_price_id,
            "effective_at": effective_at.isoformat(),
        },
        headers=auth_headers(token),
    )

    # No boundary reading recorded, but the station flag is off -> close succeeds.
    close_resp = await client.patch(f"{base}/{shift_id}/close", headers=auth_headers(token))
    assert close_resp.status_code == 200, close_resp.text


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


async def test_concurrent_approval_of_the_same_shift_only_succeeds_once(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, fuel_price, cash_payment_method
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station)
    shift = (await client.post(base, json={}, headers=auth_headers(token))).json()
    shift_id = shift["id"]
    await client.post(
        f"{base}/{shift_id}/tank-readings/opening",
        json={"tank_id": str(tank_with_stock.id), "dip_reading": "10000"},
        headers=auth_headers(token),
    )
    await client.post(
        f"{base}/{shift_id}/tank-readings/closing",
        json={"tank_id": str(tank_with_stock.id), "dip_reading": "9200"},
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
    await client.patch(f"{base}/{shift_id}/close", headers=auth_headers(token))

    # 800L dispensed (5800 - 5000) * 280.00/L fuel_price.
    await client.post(
        f"{base}/{shift_id}/tenders",
        json={"payment_method_id": str(cash_payment_method.id), "amount": "224000"},
        headers=auth_headers(token),
    )
    recon_resp = await client.post(
        f"{base}/{shift_id}/reconciliation",
        json={"actual_physical_cash": "224000"},
        headers=auth_headers(token),
    )
    assert recon_resp.status_code == 201, recon_resp.text

    async def approve():
        return await client.patch(f"{base}/{shift_id}/approve", headers=auth_headers(token))

    results = await asyncio.gather(approve(), approve())
    statuses = sorted(r.status_code for r in results)
    assert statuses == [200, 409], f"expected exactly one 200 and one 409, got {statuses}"

    tank_resp = await client.get(
        f"/organizations/{org.id}/stations/{station.id}/tanks/{tank_with_stock.id}",
        headers=auth_headers(token),
    )
    assert tank_resp.json()["book_stock"] == "9200.000", "stock must be posted exactly once"
