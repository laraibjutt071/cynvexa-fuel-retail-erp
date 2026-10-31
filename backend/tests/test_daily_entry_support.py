from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers, login

pytestmark = pytest.mark.asyncio


def _shifts_base(org, station) -> str:
    return f"/organizations/{org.id}/stations/{station.id}/shifts"


async def test_list_shifts_filters_by_business_date(client: AsyncClient, owner_user, org, station):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _shifts_base(org, station)
    created = await client.post(base, json={}, headers=auth_headers(token))
    assert created.status_code == 201, created.text

    # Shift.opened_at is stored and filtered in UTC (see
    # app/api/shifts.py::list_shifts) - date.today() uses the local
    # system timezone and can disagree with UTC near midnight, which is
    # exactly what failed here on a UTC+5 machine; use UTC "today" to
    # match what the server actually means by business_date.
    now_utc = datetime.now(timezone.utc)
    today = now_utc.date().isoformat()
    yesterday = (now_utc.date() - timedelta(days=1)).isoformat()

    todays = await client.get(f"{base}?business_date={today}", headers=auth_headers(token))
    assert todays.status_code == 200, todays.text
    assert len(todays.json()) == 1

    yesterdays = await client.get(f"{base}?business_date={yesterday}", headers=auth_headers(token))
    assert yesterdays.status_code == 200
    assert yesterdays.json() == []


async def test_business_date_filter_uses_the_stations_own_timezone_not_utc(
    client: AsyncClient, owner_user, org, db
):
    """
    A shift opened at 23:00 UTC on Jan 1st is 04:00 local time on Jan 2nd
    for a station in Asia/Karachi (UTC+5) - business_date=2026-01-02 must
    find it, business_date=2026-01-01 must not, even though the row's own
    opened_at column is still Jan 1st in UTC. See app/api/shifts.py's own
    docstring on list_shifts for why this matters for a real deployment.
    """
    from app.models.station import Station
    from app.models.shift import Shift

    # owner_user's own fixture already grants an org-wide (station_id=None)
    # role, which covers any station created afterward in the same org -
    # no extra grant needed for this new station.
    station = Station(organization_id=org.id, name="Karachi Station", code="KHI-1", timezone="Asia/Karachi")
    db.add(station)
    await db.flush()

    shift = Shift(
        organization_id=org.id,
        station_id=station.id,
        status="open",
        opened_by_user_id=owner_user.id,
        opened_at=datetime(2026, 1, 1, 23, 0, tzinfo=timezone.utc),
    )
    db.add(shift)
    await db.commit()

    token = await login(client, "owner@acmefuel-dev.com")
    base = f"/organizations/{org.id}/stations/{station.id}/shifts"

    local_day = await client.get(f"{base}?business_date=2026-01-02", headers=auth_headers(token))
    assert local_day.status_code == 200, local_day.text
    assert len(local_day.json()) == 1

    utc_day = await client.get(f"{base}?business_date=2026-01-01", headers=auth_headers(token))
    assert utc_day.status_code == 200
    assert utc_day.json() == []


async def test_nozzle_overview_shows_current_price_and_no_prior_reading(
    client: AsyncClient, owner_user, org, station, dispenser, nozzle, fuel_grade, fuel_price
):
    token = await login(client, "owner@acmefuel-dev.com")
    resp = await client.get(
        f"/organizations/{org.id}/stations/{station.id}/nozzles", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    row = next(r for r in rows if r["nozzle_id"] == str(nozzle.id))
    assert row["fuel_grade_name"] == fuel_grade.name
    assert row["current_price_per_litre"] == "280.0000"
    assert row["last_closing_totalizer"] is None


async def test_nozzle_overview_shows_last_closing_totalizer_after_a_shift(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, fuel_price
):
    token = await login(client, "owner@acmefuel-dev.com")
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
    close = await client.patch(
        f"{base}/{shift_id}/nozzle-readings/{nr['id']}/close",
        json={"closing_totalizer": "5800"},
        headers=auth_headers(token),
    )
    assert close.status_code == 200, close.text

    resp = await client.get(
        f"/organizations/{org.id}/stations/{station.id}/nozzles", headers=auth_headers(token)
    )
    row = next(r for r in resp.json() if r["nozzle_id"] == str(nozzle.id))
    assert row["last_closing_totalizer"] == "5800.000"
