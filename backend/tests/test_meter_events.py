from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.shift import Shift
from app.models.shift_nozzle_reading import ShiftNozzleReading
from tests.conftest import auth_headers, login

pytestmark = pytest.mark.asyncio


def _shifts_base(org, station) -> str:
    return f"/organizations/{org.id}/stations/{station.id}/shifts"


def _events_base(org, station) -> str:
    return f"/organizations/{org.id}/stations/{station.id}/meter-events"


async def _flag_meter_event(
    client: AsyncClient, token: str, org, station, nozzle, *, event_type="rollover", opening="99990"
) -> tuple[str, str]:
    """Opens a shift, opens a nozzle reading, and closes it with a flagged
    meter event. Returns (shift_id, nozzle_reading_id)."""
    base = _shifts_base(org, station)
    shift = (await client.post(base, json={}, headers=auth_headers(token))).json()
    shift_id = shift["id"]
    nr = (
        await client.post(
            f"{base}/{shift_id}/nozzle-readings",
            json={"nozzle_id": str(nozzle.id), "opening_totalizer": opening},
            headers=auth_headers(token),
        )
    ).json()
    close = await client.patch(
        f"{base}/{shift_id}/nozzle-readings/{nr['id']}/close",
        json={
            "closing_totalizer": "100",
            "meter_event_type": event_type,
            "meter_event_pre_reading": "99999",
            "meter_event_post_reading": "0",
            "meter_event_notes": "E2E test meter event",
        },
        headers=auth_headers(token),
    )
    assert close.status_code == 200, close.text
    return shift_id, nr["id"]


async def test_meter_event_appears_in_station_history(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, seeded_roles
):
    token = await login(client, "owner@acmefuel-dev.com")
    shift_id, reading_id = await _flag_meter_event(client, token, org, station, nozzle)

    resp = await client.get(_events_base(org, station), headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["nozzle_reading_id"] == reading_id
    assert row["shift_id"] == shift_id
    assert row["event_type"] == "rollover"
    assert row["meter_event_pre_reading"] == "99999.000"
    assert row["meter_event_post_reading"] == "0.000"
    assert row["dispensed_litres"] == "109.000"
    assert row["approved_by_user_id"] is None
    assert row["approved_at"] is None
    assert row["nozzle_code"] == nozzle.code
    assert row["station_id"] == str(station.id)


async def test_approved_event_shows_approver_in_history(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, seeded_roles
):
    token = await login(client, "owner@acmefuel-dev.com")
    shift_id, reading_id = await _flag_meter_event(client, token, org, station, nozzle)

    approve = await client.patch(
        f"{_shifts_base(org, station)}/{shift_id}/nozzle-readings/{reading_id}/approve-meter-event",
        json={},
        headers=auth_headers(token),
    )
    assert approve.status_code == 200, approve.text

    resp = await client.get(_events_base(org, station), headers=auth_headers(token))
    row = resp.json()[0]
    assert row["approved_by_user_id"] == str(owner_user.id)
    assert row["approved_at"] is not None


async def test_filter_by_event_type(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, seeded_roles
):
    token = await login(client, "owner@acmefuel-dev.com")
    await _flag_meter_event(client, token, org, station, nozzle, event_type="rollover")

    rollover_resp = await client.get(f"{_events_base(org, station)}?event_type=rollover", headers=auth_headers(token))
    assert len(rollover_resp.json()) == 1

    reset_resp = await client.get(f"{_events_base(org, station)}?event_type=reset", headers=auth_headers(token))
    assert reset_resp.json() == []


async def test_filter_by_approved_status(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, seeded_roles
):
    token = await login(client, "owner@acmefuel-dev.com")
    shift_id, reading_id = await _flag_meter_event(client, token, org, station, nozzle)

    pending_only = await client.get(f"{_events_base(org, station)}?approved=false", headers=auth_headers(token))
    assert len(pending_only.json()) == 1
    approved_only = await client.get(f"{_events_base(org, station)}?approved=true", headers=auth_headers(token))
    assert approved_only.json() == []

    await client.patch(
        f"{_shifts_base(org, station)}/{shift_id}/nozzle-readings/{reading_id}/approve-meter-event",
        json={},
        headers=auth_headers(token),
    )

    pending_only = await client.get(f"{_events_base(org, station)}?approved=false", headers=auth_headers(token))
    assert pending_only.json() == []
    approved_only = await client.get(f"{_events_base(org, station)}?approved=true", headers=auth_headers(token))
    assert len(approved_only.json()) == 1


async def test_date_range_excludes_events_outside_it(
    client: AsyncClient, db: AsyncSession, owner_user, org, station, tank_with_stock, nozzle, seeded_roles
):
    token = await login(client, "owner@acmefuel-dev.com")
    shift_id, _ = await _flag_meter_event(client, token, org, station, nozzle)

    shift = (await db.execute(select(Shift).where(Shift.id == shift_id))).scalar_one()
    shift.opened_at = datetime.now(timezone.utc) - timedelta(days=10)
    await db.commit()

    today = datetime.now(timezone.utc).date().isoformat()
    resp = await client.get(
        f"{_events_base(org, station)}?date_from={today}&date_to={today}", headers=auth_headers(token)
    )
    assert resp.json() == []

    wide = await client.get(
        f"{_events_base(org, station)}?date_from=2000-01-01&date_to={today}", headers=auth_headers(token)
    )
    assert len(wide.json()) == 1


async def test_a_meter_event_remains_visible_beyond_the_24_hour_correction_window(
    client: AsyncClient, db: AsyncSession, owner_user, org, station, tank_with_stock, nozzle, seeded_roles
):
    """This history view introduces no new deadline of its own - an old,
    unapproved or approved event stays visible exactly like a recent one.
    The 24-hour window belongs entirely to the existing, separate
    reading-correction system (ReadingType.METER_EVENT_PRE/POST), which
    this endpoint neither reads nor duplicates."""
    token = await login(client, "owner@acmefuel-dev.com")
    shift_id, reading_id = await _flag_meter_event(client, token, org, station, nozzle)

    reading = (
        await db.execute(select(ShiftNozzleReading).where(ShiftNozzleReading.id == reading_id))
    ).scalar_one()
    reading.closing_recorded_at = datetime.now(timezone.utc) - timedelta(days=30)
    shift = (await db.execute(select(Shift).where(Shift.id == shift_id))).scalar_one()
    shift.opened_at = datetime.now(timezone.utc) - timedelta(days=30)
    await db.commit()

    resp = await client.get(_events_base(org, station), headers=auth_headers(token))
    assert len(resp.json()) == 1


async def test_invalid_date_range_is_rejected(client: AsyncClient, owner_user, org, station, seeded_roles):
    token = await login(client, "owner@acmefuel-dev.com")
    resp = await client.get(
        f"{_events_base(org, station)}?date_from=2026-01-10&date_to=2026-01-01", headers=auth_headers(token)
    )
    assert resp.status_code == 422


async def test_cross_organization_access_is_denied(
    client: AsyncClient, owner_user, org, other_org, station, seeded_roles
):
    """owner_user holds no role in other_org at all - require_permission
    rejects on organization membership before the (real, but
    other_org's own) station_id is even looked up."""
    token = await login(client, "owner@acmefuel-dev.com")
    resp = await client.get(_events_base(other_org, station), headers=auth_headers(token))
    assert resp.status_code == 403


async def test_station_scoped_user_cannot_see_another_stations_history(
    client: AsyncClient, db: AsyncSession, cashier_user, org, station, tank_with_stock, nozzle, seeded_roles
):
    from app.models.station import Station

    other_station = Station(organization_id=org.id, name="Other Station", code="OTH-1")
    db.add(other_station)
    await db.commit()
    await db.refresh(other_station)

    token = await login(client, cashier_user.email)
    resp = await client.get(_events_base(org, other_station), headers=auth_headers(token))
    assert resp.status_code == 403


async def test_superuser_needs_an_active_support_session(client: AsyncClient, superuser, org, station, seeded_roles):
    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    resp = await client.get(_events_base(org, station), headers=auth_headers(admin_token))
    assert resp.status_code == 403


async def test_support_session_grants_read_only_history_access(
    client: AsyncClient, superuser, org, station, tank_with_stock, nozzle, owner_user, seeded_roles
):
    token = await login(client, "owner@acmefuel-dev.com")
    await _flag_meter_event(client, token, org, station, nozzle)

    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    session_resp = await client.post(
        "/platform/support-sessions",
        json={"organization_id": str(org.id), "reason": "Investigating a client-reported meter event question.", "duration_minutes": 15},
        headers=auth_headers(admin_token),
    )
    assert session_resp.status_code == 201

    resp = await client.get(_events_base(org, station), headers=auth_headers(admin_token))
    assert resp.status_code == 200
    assert len(resp.json()) == 1
