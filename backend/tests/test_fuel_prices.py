import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers, login

pytestmark = pytest.mark.asyncio


async def test_create_fuel_price_and_read_current(
    client: AsyncClient, owner_user, org, station, fuel_grade
):
    token = await login(client, "owner@acmefuel-dev.com")
    resp = await client.post(
        f"/organizations/{org.id}/stations/{station.id}/fuel-prices",
        json={
            "fuel_grade_id": str(fuel_grade.id),
            "price_per_litre": "272.50",
            "effective_from": "2026-01-01T00:00:00Z",
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text

    current = await client.get(
        f"/organizations/{org.id}/stations/{station.id}/fuel-prices/current",
        params={"fuel_grade_id": str(fuel_grade.id)},
        headers=auth_headers(token),
    )
    assert current.status_code == 200
    assert current.json()["price_per_litre"] == "272.5000"


async def test_price_history_is_never_overwritten_newest_effective_wins(
    client: AsyncClient, owner_user, org, station, fuel_grade
):
    token = await login(client, "owner@acmefuel-dev.com")
    await client.post(
        f"/organizations/{org.id}/stations/{station.id}/fuel-prices",
        json={
            "fuel_grade_id": str(fuel_grade.id),
            "price_per_litre": "272.50",
            "effective_from": "2026-01-01T00:00:00Z",
        },
        headers=auth_headers(token),
    )
    await client.post(
        f"/organizations/{org.id}/stations/{station.id}/fuel-prices",
        json={
            "fuel_grade_id": str(fuel_grade.id),
            "price_per_litre": "280.00",
            "effective_from": "2026-02-01T00:00:00Z",
        },
        headers=auth_headers(token),
    )

    history = await client.get(
        f"/organizations/{org.id}/stations/{station.id}/fuel-prices",
        headers=auth_headers(token),
    )
    assert len(history.json()) == 2  # both rows kept - never overwritten

    current = await client.get(
        f"/organizations/{org.id}/stations/{station.id}/fuel-prices/current",
        params={"fuel_grade_id": str(fuel_grade.id)},
        headers=auth_headers(token),
    )
    assert current.json()["price_per_litre"] == "280.0000"

    # Asking for the price as of a date BEFORE the second change still
    # resolves to the first price - history is reproducible, not just "latest wins".
    as_of_resp = await client.get(
        f"/organizations/{org.id}/stations/{station.id}/fuel-prices",
        headers=auth_headers(token),
    )
    prices_by_effective = {p["effective_from"]: p["price_per_litre"] for p in as_of_resp.json()}
    assert prices_by_effective["2026-01-01T00:00:00Z"] == "272.5000"


async def test_duplicate_effective_from_for_same_grade_is_rejected(
    client: AsyncClient, owner_user, org, station, fuel_grade
):
    token = await login(client, "owner@acmefuel-dev.com")
    payload = {
        "fuel_grade_id": str(fuel_grade.id),
        "price_per_litre": "272.50",
        "effective_from": "2026-01-01T00:00:00Z",
    }
    first = await client.post(
        f"/organizations/{org.id}/stations/{station.id}/fuel-prices",
        json=payload,
        headers=auth_headers(token),
    )
    assert first.status_code == 201
    second = await client.post(
        f"/organizations/{org.id}/stations/{station.id}/fuel-prices",
        json=payload,
        headers=auth_headers(token),
    )
    assert second.status_code == 409


async def test_only_owner_can_set_fuel_price_not_station_manager(
    client: AsyncClient, station_manager_user, org, station, fuel_grade
):
    """Per blueprint §12: fuel price change is an Owner/GM-protected action."""
    token = await login(client, "manager@acmefuel-dev.com")
    resp = await client.post(
        f"/organizations/{org.id}/stations/{station.id}/fuel-prices",
        json={
            "fuel_grade_id": str(fuel_grade.id),
            "price_per_litre": "272.50",
            "effective_from": "2026-01-01T00:00:00Z",
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 403


async def test_no_current_price_returns_404_not_a_default(
    client: AsyncClient, owner_user, org, station, fuel_grade
):
    token = await login(client, "owner@acmefuel-dev.com")
    resp = await client.get(
        f"/organizations/{org.id}/stations/{station.id}/fuel-prices/current",
        params={"fuel_grade_id": str(fuel_grade.id)},
        headers=auth_headers(token),
    )
    assert resp.status_code == 404
