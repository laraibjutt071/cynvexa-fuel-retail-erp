from decimal import Decimal

import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers, login

pytestmark = pytest.mark.asyncio


# --- Fuel grades (org-level) ---


async def test_owner_can_create_and_list_fuel_grades(client: AsyncClient, owner_user, org):
    token = await login(client, "owner@acmefuel-dev.com")
    resp = await client.post(
        f"/organizations/{org.id}/fuel-grades",
        json={"name": "Diesel", "code": "DSL"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text

    list_resp = await client.get(f"/organizations/{org.id}/fuel-grades", headers=auth_headers(token))
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


async def test_duplicate_fuel_grade_code_in_same_org_is_rejected(client: AsyncClient, owner_user, org):
    token = await login(client, "owner@acmefuel-dev.com")
    first = await client.post(
        f"/organizations/{org.id}/fuel-grades",
        json={"name": "Diesel", "code": "DSL"},
        headers=auth_headers(token),
    )
    assert first.status_code == 201
    second = await client.post(
        f"/organizations/{org.id}/fuel-grades",
        json={"name": "Diesel Again", "code": "DSL"},
        headers=auth_headers(token),
    )
    assert second.status_code == 409


async def test_cashier_cannot_create_fuel_grade(client: AsyncClient, cashier_user, org):
    token = await login(client, "cashier@acmefuel-dev.com")
    resp = await client.post(
        f"/organizations/{org.id}/fuel-grades",
        json={"name": "Diesel", "code": "DSL"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 403


# --- Suppliers (org-level) ---


async def test_owner_can_create_supplier(client: AsyncClient, owner_user, org):
    token = await login(client, "owner@acmefuel-dev.com")
    resp = await client.post(
        f"/organizations/{org.id}/suppliers",
        json={"name": "Acme Fuel Supply", "contact_email": "ops@acme-supply.example"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text


async def test_cashier_cannot_manage_suppliers(client: AsyncClient, cashier_user, org):
    token = await login(client, "cashier@acmefuel-dev.com")
    resp = await client.post(
        f"/organizations/{org.id}/suppliers",
        json={"name": "Acme Fuel Supply"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 403


# --- Tanks (station-level) ---


async def test_owner_can_create_tank(client: AsyncClient, owner_user, org, station, fuel_grade):
    token = await login(client, "owner@acmefuel-dev.com")
    resp = await client.post(
        f"/organizations/{org.id}/stations/{station.id}/tanks",
        json={
            "fuel_grade_id": str(fuel_grade.id),
            "code": "T1",
            "name": "Tank 1",
            "capacity": "20000",
            "safe_fill_limit": "18000",
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert Decimal(body["capacity"]) == Decimal("20000")


async def test_tank_safe_fill_limit_cannot_exceed_capacity(
    client: AsyncClient, owner_user, org, station, fuel_grade
):
    token = await login(client, "owner@acmefuel-dev.com")
    resp = await client.post(
        f"/organizations/{org.id}/stations/{station.id}/tanks",
        json={
            "fuel_grade_id": str(fuel_grade.id),
            "code": "T1",
            "name": "Tank 1",
            "capacity": "10000",
            "safe_fill_limit": "15000",
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 422


async def test_tank_update_rejects_safe_fill_limit_above_existing_capacity(
    client: AsyncClient, owner_user, org, station, tank
):
    token = await login(client, "owner@acmefuel-dev.com")
    resp = await client.patch(
        f"/organizations/{org.id}/stations/{station.id}/tanks/{tank.id}",
        json={"safe_fill_limit": "25000"},  # tank.capacity is 20000
        headers=auth_headers(token),
    )
    assert resp.status_code == 422


async def test_tank_requires_fuel_grade_from_same_organization(
    client: AsyncClient, owner_user, org, other_org, station, db
):
    from app.models.fuel_grade import FuelGrade

    foreign_grade = FuelGrade(organization_id=other_org.id, name="Foreign Grade", code="FG1")
    db.add(foreign_grade)
    await db.commit()
    await db.refresh(foreign_grade)

    token = await login(client, "owner@acmefuel-dev.com")
    resp = await client.post(
        f"/organizations/{org.id}/stations/{station.id}/tanks",
        json={
            "fuel_grade_id": str(foreign_grade.id),
            "code": "T1",
            "name": "Tank 1",
            "capacity": "20000",
            "safe_fill_limit": "18000",
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 422


async def test_get_tank_includes_live_book_stock(client: AsyncClient, owner_user, org, station, tank):
    token = await login(client, "owner@acmefuel-dev.com")
    resp = await client.get(
        f"/organizations/{org.id}/stations/{station.id}/tanks/{tank.id}", headers=auth_headers(token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["book_stock"] == "0.000"
    assert body["safe_capacity_available"] == "18000.000"


# --- Dispensers & nozzles ---


async def test_create_dispenser_and_nozzle(client: AsyncClient, owner_user, org, station, tank):
    token = await login(client, "owner@acmefuel-dev.com")
    dispenser_resp = await client.post(
        f"/organizations/{org.id}/stations/{station.id}/dispensers",
        json={"code": "D1", "name": "Dispenser 1"},
        headers=auth_headers(token),
    )
    assert dispenser_resp.status_code == 201
    dispenser_id = dispenser_resp.json()["id"]

    nozzle_resp = await client.post(
        f"/organizations/{org.id}/stations/{station.id}/dispensers/{dispenser_id}/nozzles",
        json={"tank_id": str(tank.id), "code": "N1"},
        headers=auth_headers(token),
    )
    assert nozzle_resp.status_code == 201, nozzle_resp.text


async def test_nozzle_rejects_tank_from_different_station(
    client: AsyncClient, owner_user, org, station, db
):
    from decimal import Decimal

    from app.models.station import Station
    from app.models.tank import Tank

    other_station = Station(organization_id=org.id, name="Other Station", code="STN-2")
    db.add(other_station)
    await db.flush()
    foreign_tank = Tank(
        station_id=other_station.id,
        fuel_grade_id=None,
        code="FT1",
        name="Foreign Tank",
        capacity=Decimal("1000"),
        safe_fill_limit=Decimal("900"),
    )
    # fuel_grade_id is NOT NULL in the schema, so build the grade first.
    from app.models.fuel_grade import FuelGrade

    grade = FuelGrade(organization_id=org.id, name="G", code="G1")
    db.add(grade)
    await db.flush()
    foreign_tank.fuel_grade_id = grade.id
    db.add(foreign_tank)
    await db.commit()
    await db.refresh(foreign_tank)

    token = await login(client, "owner@acmefuel-dev.com")
    dispenser_resp = await client.post(
        f"/organizations/{org.id}/stations/{station.id}/dispensers",
        json={"code": "D1", "name": "Dispenser 1"},
        headers=auth_headers(token),
    )
    dispenser_id = dispenser_resp.json()["id"]

    resp = await client.post(
        f"/organizations/{org.id}/stations/{station.id}/dispensers/{dispenser_id}/nozzles",
        json={"tank_id": str(foreign_tank.id), "code": "N1"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 422
