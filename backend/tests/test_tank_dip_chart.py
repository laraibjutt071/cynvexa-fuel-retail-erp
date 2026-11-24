import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers, login

pytestmark = pytest.mark.asyncio


def _base(org, station, tank) -> str:
    return f"/organizations/{org.id}/stations/{station.id}/tanks/{tank.id}/dip-chart"


async def test_owner_can_add_calibration_points_and_list_them(
    client: AsyncClient, owner_user, org, station, tank
):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station, tank)

    for dip, vol in [("0.0", "0.000"), ("500.0", "3000.000"), ("1000.0", "7000.000")]:
        resp = await client.post(base, json={"dip_mm": dip, "volume_litres": vol}, headers=auth_headers(token))
        assert resp.status_code == 201, resp.text

    listed = await client.get(base, headers=auth_headers(token))
    assert listed.status_code == 200
    assert [e["dip_mm"] for e in listed.json()] == ["0.0", "500.0", "1000.0"]


async def test_duplicate_dip_mm_for_same_tank_is_rejected(client: AsyncClient, owner_user, org, station, tank):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station, tank)
    payload = {"dip_mm": "500.0", "volume_litres": "3000.000"}
    first = await client.post(base, json=payload, headers=auth_headers(token))
    assert first.status_code == 201
    second = await client.post(base, json=payload, headers=auth_headers(token))
    assert second.status_code == 409


async def test_lookup_exact_match(client: AsyncClient, owner_user, org, station, tank):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station, tank)
    await client.post(base, json={"dip_mm": "0.0", "volume_litres": "0.000"}, headers=auth_headers(token))
    await client.post(base, json={"dip_mm": "500.0", "volume_litres": "3000.000"}, headers=auth_headers(token))

    resp = await client.get(f"{base}/lookup", params={"dip_mm": "500.0"}, headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["volume_litres"] == "3000.000"
    assert body["exact_match"] is True


async def test_lookup_interpolates_linearly_between_two_points(client: AsyncClient, owner_user, org, station, tank):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station, tank)
    await client.post(base, json={"dip_mm": "500.0", "volume_litres": "3000.000"}, headers=auth_headers(token))
    await client.post(base, json={"dip_mm": "1000.0", "volume_litres": "7000.000"}, headers=auth_headers(token))

    resp = await client.get(f"{base}/lookup", params={"dip_mm": "750.0"}, headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["volume_litres"] == "5000.000"
    assert body["exact_match"] is False


async def test_lookup_outside_calibrated_range_is_rejected(client: AsyncClient, owner_user, org, station, tank):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station, tank)
    await client.post(base, json={"dip_mm": "500.0", "volume_litres": "3000.000"}, headers=auth_headers(token))
    await client.post(base, json={"dip_mm": "1000.0", "volume_litres": "7000.000"}, headers=auth_headers(token))

    resp = await client.get(f"{base}/lookup", params={"dip_mm": "2000.0"}, headers=auth_headers(token))
    assert resp.status_code == 422


async def test_lookup_with_fewer_than_two_points_is_rejected(client: AsyncClient, owner_user, org, station, tank):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station, tank)
    await client.post(base, json={"dip_mm": "500.0", "volume_litres": "3000.000"}, headers=auth_headers(token))

    resp = await client.get(f"{base}/lookup", params={"dip_mm": "500.0"}, headers=auth_headers(token))
    # Even an exact-match lookup is refused below 2 points - a single point
    # cannot distinguish "this tank's chart only has this one entry so far"
    # from a real calibration, so neither path is trusted yet.
    assert resp.status_code == 422


async def test_station_manager_cannot_add_calibration_points(
    client: AsyncClient, station_manager_user, org, station, tank
):
    token = await login(client, "manager@acmefuel-dev.com")
    resp = await client.post(
        _base(org, station, tank), json={"dip_mm": "500.0", "volume_litres": "3000.000"}, headers=auth_headers(token)
    )
    assert resp.status_code == 403


async def test_delete_calibration_point(client: AsyncClient, owner_user, org, station, tank):
    token = await login(client, "owner@acmefuel-dev.com")
    base = _base(org, station, tank)
    created = await client.post(base, json={"dip_mm": "500.0", "volume_litres": "3000.000"}, headers=auth_headers(token))
    entry_id = created.json()["id"]

    deleted = await client.delete(f"{base}/{entry_id}", headers=auth_headers(token))
    assert deleted.status_code == 204

    listed = await client.get(base, headers=auth_headers(token))
    assert listed.json() == []
