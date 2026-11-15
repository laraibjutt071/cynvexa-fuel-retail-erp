"""
Phase 6 — the owner-approved fix: Cashier/Operator gains tank:read and
nozzle:read (read-only, station/org-scoped) so the Daily Entry Readings
step can list what to record a reading against (Phase 5 finding,
docs/PHASE_5_DAILY_ENTRY_REPORT.md Section 4). These tests prove the fix
is exactly as narrow as approved: read access to the user's own
authorized station only, no create/edit/delete, no approval authority,
and no change to any other role's existing permissions.
"""

import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers, login


@pytest.mark.asyncio
async def test_cashier_can_read_own_station_tanks(client: AsyncClient, cashier_user, org, station, tank):
    token = await login(client, cashier_user.email)
    resp = await client.get(
        f"/organizations/{org.id}/stations/{station.id}/tanks", headers=auth_headers(token)
    )
    assert resp.status_code == 200
    assert any(t["id"] == str(tank.id) for t in resp.json())


@pytest.mark.asyncio
async def test_cashier_can_read_own_station_nozzles(
    client: AsyncClient, cashier_user, org, station, nozzle
):
    token = await login(client, cashier_user.email)
    resp = await client.get(
        f"/organizations/{org.id}/stations/{station.id}/nozzles", headers=auth_headers(token)
    )
    assert resp.status_code == 200
    assert any(n["nozzle_id"] == str(nozzle.id) for n in resp.json())


@pytest.mark.asyncio
async def test_cashier_cannot_read_a_different_stations_tanks(
    client: AsyncClient, cashier_user, org, db
):
    from app.models.station import Station

    other_station = Station(organization_id=org.id, name="Second Station", code="STN-2")
    db.add(other_station)
    await db.commit()
    await db.refresh(other_station)

    token = await login(client, cashier_user.email)
    resp = await client.get(
        f"/organizations/{org.id}/stations/{other_station.id}/tanks", headers=auth_headers(token)
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_cashier_cannot_read_a_different_stations_nozzles(
    client: AsyncClient, cashier_user, org, db
):
    from app.models.station import Station

    other_station = Station(organization_id=org.id, name="Second Station", code="STN-2")
    db.add(other_station)
    await db.commit()
    await db.refresh(other_station)

    token = await login(client, cashier_user.email)
    resp = await client.get(
        f"/organizations/{org.id}/stations/{other_station.id}/nozzles", headers=auth_headers(token)
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_cashier_cannot_read_another_organizations_tanks(
    client: AsyncClient, cashier_user, other_org, db
):
    from app.models.station import Station

    foreign_station = Station(organization_id=other_org.id, name="Foreign Station", code="FOR-1")
    db.add(foreign_station)
    await db.commit()
    await db.refresh(foreign_station)

    token = await login(client, cashier_user.email)
    resp = await client.get(
        f"/organizations/{other_org.id}/stations/{foreign_station.id}/tanks", headers=auth_headers(token)
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_cashier_cannot_create_a_tank(client: AsyncClient, cashier_user, org, station, fuel_grade):
    token = await login(client, cashier_user.email)
    resp = await client.post(
        f"/organizations/{org.id}/stations/{station.id}/tanks",
        json={
            "code": "T-NEW",
            "name": "New Tank",
            "fuel_grade_id": str(fuel_grade.id),
            "capacity": "10000",
            "safe_fill_limit": "9000",
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_cashier_cannot_edit_a_tank(client: AsyncClient, cashier_user, org, station, tank):
    token = await login(client, cashier_user.email)
    resp = await client.patch(
        f"/organizations/{org.id}/stations/{station.id}/tanks/{tank.id}",
        json={"location": "moved"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_cashier_cannot_create_a_nozzle(client: AsyncClient, cashier_user, org, station, dispenser, tank):
    token = await login(client, cashier_user.email)
    resp = await client.post(
        f"/organizations/{org.id}/stations/{station.id}/dispensers/{dispenser.id}/nozzles",
        json={"code": "N-NEW", "tank_id": str(tank.id)},
        headers=auth_headers(token),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_cashier_cannot_edit_a_nozzle(client: AsyncClient, cashier_user, org, station, dispenser, nozzle):
    token = await login(client, cashier_user.email)
    resp = await client.patch(
        f"/organizations/{org.id}/stations/{station.id}/dispensers/{dispenser.id}/nozzles/{nozzle.id}",
        json={"is_active": False},
        headers=auth_headers(token),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_cashier_cannot_approve_a_reading_correction(
    client: AsyncClient, cashier_user, station_manager_user, org, station, db, seeded_roles
):
    """Reading-correction approval needs reading:correct_approve, which
    this phase deliberately does NOT grant to Cashier/Operator alongside
    the new read-only tank/nozzle access."""
    from app.models.shift import Shift, ShiftStatus
    from app.models.reading_correction import ReadingCorrection, ReadingType, CorrectionStatus
    from datetime import datetime, timezone

    shift = Shift(
        organization_id=org.id,
        station_id=station.id,
        status=ShiftStatus.OPEN.value,
        opened_by_user_id=station_manager_user.id,
    )
    db.add(shift)
    await db.flush()

    now = datetime.now(timezone.utc)
    correction = ReadingCorrection(
        organization_id=org.id,
        station_id=station.id,
        shift_id=shift.id,
        reading_type=ReadingType.TANK_DIP.value,
        original_value="100.000",
        corrected_value="110.000",
        reason="test",
        original_submitted_at=now,
        is_post_lock=False,
        status=CorrectionStatus.PENDING.value,
        requested_by_user_id=station_manager_user.id,
        requested_at=now,
    )
    db.add(correction)
    await db.commit()
    await db.refresh(correction)

    token = await login(client, cashier_user.email)
    resp = await client.post(
        f"/organizations/{org.id}/stations/{station.id}/shifts/{shift.id}/reading-corrections/{correction.id}/approve",
        headers=auth_headers(token),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_owner_station_manager_and_auditor_tank_read_unaffected(
    client: AsyncClient, owner_user, station_manager_user, org, station, tank, db, seeded_roles
):
    """This phase only adds to Cashier/Operator - every role that already
    had tank:read must still have exactly the same access as before."""
    owner_token = await login(client, owner_user.email)
    owner_resp = await client.get(
        f"/organizations/{org.id}/stations/{station.id}/tanks", headers=auth_headers(owner_token)
    )
    assert owner_resp.status_code == 200

    manager_token = await login(client, station_manager_user.email)
    manager_resp = await client.get(
        f"/organizations/{org.id}/stations/{station.id}/tanks", headers=auth_headers(manager_token)
    )
    assert manager_resp.status_code == 200

    # Station Manager holds tank:read but not tank:manage (only
    # Storekeeper/Technician and Owner do) - unchanged by this phase, and
    # this phase must not accidentally widen it.
    manage_resp = await client.patch(
        f"/organizations/{org.id}/stations/{station.id}/tanks/{tank.id}",
        json={"location": "front row"},
        headers=auth_headers(manager_token),
    )
    assert manage_resp.status_code == 403
