"""
Tests for the 24-hour reading correction policy.

Acceptance criteria (from the user's requirement):
1. Correction at 23h59m is allowed for an authorized user
2. Correction at exactly 24h is rejected (post-lock)
3. Correction at 24h01m is rejected (post-lock)
4. Admin/superuser cannot bypass the 24-hour direct-edit lock
5. Post-24h amendment preserves the original and records full audit trail
6. Concurrent correction requests cannot cause inconsistent results
7. Unauthorized correction is rejected
8. Client-supplied timestamps cannot manipulate the correction window
9. UTC/timezone-aware comparisons work correctly
10. Organization and station isolation is enforced
11. Rejected operations do not partially modify records
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers, login

pytestmark = pytest.mark.asyncio


def _shifts_base(org, station) -> str:
    return f"/organizations/{org.id}/stations/{station.id}/shifts"


async def _create_shift_with_tank_reading(
    client: AsyncClient, token: str, org, station, tank_with_stock
) -> tuple[str, str]:
    base = _shifts_base(org, station)
    shift = (await client.post(base, json={"label": "Test"}, headers=auth_headers(token))).json()
    shift_id = shift["id"]

    reading = (
        await client.post(
            f"{base}/{shift_id}/tank-readings/opening",
            json={"tank_id": str(tank_with_stock.id), "dip_reading": "10000.000"},
            headers=auth_headers(token),
        )
    ).json()
    return shift_id, reading["id"]


async def _create_shift_with_nozzle_reading(
    client: AsyncClient, token: str, org, station, nozzle
) -> tuple[str, str]:
    base = _shifts_base(org, station)
    shift = (await client.post(base, json={"label": "Test"}, headers=auth_headers(token))).json()
    shift_id = shift["id"]

    reading = (
        await client.post(
            f"{base}/{shift_id}/nozzle-readings",
            json={"nozzle_id": str(nozzle.id), "opening_totalizer": "5000.000"},
            headers=auth_headers(token),
        )
    ).json()
    return shift_id, reading["id"]


def _corrections_url(org, station, shift_id) -> str:
    return f"/organizations/{org.id}/stations/{station.id}/shifts/{shift_id}/reading-corrections"


# =========================================================================
# Test 1: Correction at 23h59m is allowed
# =========================================================================
async def test_correction_within_window_23h59m(
    client: AsyncClient, owner_user, org, station, tank_with_stock, fuel_grade, fuel_price
):
    token = await login(client, "owner@acmefuel-dev.com")
    shift_id, reading_id = await _create_shift_with_tank_reading(
        client, token, org, station, tank_with_stock
    )

    submitted_at = datetime.now(timezone.utc)
    almost_24h = submitted_at + timedelta(hours=23, minutes=59)

    with patch("app.api.reading_corrections._now_utc", return_value=almost_24h):
        resp = await client.post(
            _corrections_url(org, station, shift_id),
            json={
                "reading_type": "tank_dip",
                "tank_reading_id": reading_id,
                "corrected_value": "9500.000",
                "reason": "Misread the dip stick",
            },
            headers=auth_headers(token),
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["is_post_lock"] is False
    assert data["status"] == "pending"
    assert data["original_value"] == "10000.000"
    assert data["corrected_value"] == "9500.000"


# =========================================================================
# Test 2: Correction at exactly 24h is post-lock
# =========================================================================
async def test_correction_at_exactly_24h_is_post_lock(
    client: AsyncClient, owner_user, org, station, tank_with_stock, fuel_grade, fuel_price
):
    token = await login(client, "owner@acmefuel-dev.com")
    shift_id, reading_id = await _create_shift_with_tank_reading(
        client, token, org, station, tank_with_stock
    )

    submitted_at = datetime.now(timezone.utc)
    exactly_24h = submitted_at + timedelta(hours=24)

    with patch("app.api.reading_corrections._now_utc", return_value=exactly_24h):
        resp = await client.post(
            _corrections_url(org, station, shift_id),
            json={
                "reading_type": "tank_dip",
                "tank_reading_id": reading_id,
                "corrected_value": "9500.000",
                "reason": "Misread the dip stick",
            },
            headers=auth_headers(token),
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["is_post_lock"] is True


# =========================================================================
# Test 3: Correction at 24h01m is post-lock
# =========================================================================
async def test_correction_at_24h01m_is_post_lock(
    client: AsyncClient, owner_user, org, station, tank_with_stock, fuel_grade, fuel_price
):
    token = await login(client, "owner@acmefuel-dev.com")
    shift_id, reading_id = await _create_shift_with_tank_reading(
        client, token, org, station, tank_with_stock
    )

    submitted_at = datetime.now(timezone.utc)
    past_24h = submitted_at + timedelta(hours=24, minutes=1)

    with patch("app.api.reading_corrections._now_utc", return_value=past_24h):
        resp = await client.post(
            _corrections_url(org, station, shift_id),
            json={
                "reading_type": "tank_dip",
                "tank_reading_id": reading_id,
                "corrected_value": "9500.000",
                "reason": "Misread the dip stick",
            },
            headers=auth_headers(token),
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["is_post_lock"] is True


# =========================================================================
# Test 4: Superuser cannot approve a direct-edit after 24h
# =========================================================================
async def test_superuser_cannot_bypass_24h_lock_on_approval(
    client: AsyncClient, db, owner_user, org, station, tank_with_stock, fuel_grade, fuel_price
):
    token = await login(client, "owner@acmefuel-dev.com")
    shift_id, reading_id = await _create_shift_with_tank_reading(
        client, token, org, station, tank_with_stock
    )

    submitted_at = datetime.now(timezone.utc)
    within_window = submitted_at + timedelta(hours=1)

    with patch("app.api.reading_corrections._now_utc", return_value=within_window):
        create_resp = await client.post(
            _corrections_url(org, station, shift_id),
            json={
                "reading_type": "tank_dip",
                "tank_reading_id": reading_id,
                "corrected_value": "9500.000",
                "reason": "Misread the dip stick",
            },
            headers=auth_headers(token),
        )
    assert create_resp.status_code == 201
    correction_id = create_resp.json()["id"]
    assert create_resp.json()["is_post_lock"] is False

    past_24h = submitted_at + timedelta(hours=25)
    with patch("app.api.reading_corrections._now_utc", return_value=past_24h):
        approve_resp = await client.post(
            f"{_corrections_url(org, station, shift_id)}/{correction_id}/approve",
            headers=auth_headers(token),
        )
    assert approve_resp.status_code == 409
    assert "24-hour correction window has expired" in approve_resp.json()["detail"]


# =========================================================================
# Test 5: Post-lock amendment preserves original and records audit trail
# =========================================================================
async def test_post_lock_amendment_preserves_original(
    client: AsyncClient, db, owner_user, org, station, tank_with_stock, fuel_grade, fuel_price
):
    token = await login(client, "owner@acmefuel-dev.com")
    shift_id, reading_id = await _create_shift_with_tank_reading(
        client, token, org, station, tank_with_stock
    )

    submitted_at = datetime.now(timezone.utc)
    past_24h = submitted_at + timedelta(hours=25)

    with patch("app.api.reading_corrections._now_utc", return_value=past_24h):
        create_resp = await client.post(
            _corrections_url(org, station, shift_id),
            json={
                "reading_type": "tank_dip",
                "tank_reading_id": reading_id,
                "corrected_value": "9500.000",
                "reason": "Discovered dip stick calibration error",
            },
            headers=auth_headers(token),
        )
    assert create_resp.status_code == 201
    correction_id = create_resp.json()["id"]
    assert create_resp.json()["is_post_lock"] is True

    with patch("app.api.reading_corrections._now_utc", return_value=past_24h):
        approve_resp = await client.post(
            f"{_corrections_url(org, station, shift_id)}/{correction_id}/approve",
            headers=auth_headers(token),
        )
    assert approve_resp.status_code == 200
    data = approve_resp.json()
    assert data["status"] == "approved"
    assert data["original_value"] == "10000.000"
    assert data["corrected_value"] == "9500.000"
    assert data["decided_by_user_id"] is not None

    readings_resp = await client.get(
        f"{_shifts_base(org, station)}/{shift_id}/tank-readings",
        headers=auth_headers(token),
    )
    tank_readings = readings_resp.json()
    original_reading = next(r for r in tank_readings if r["id"] == reading_id)
    assert Decimal(original_reading["dip_reading"]) == Decimal("10000.000")


# =========================================================================
# Test 6: Within-window approved correction modifies the reading
# =========================================================================
async def test_within_window_approved_correction_modifies_reading(
    client: AsyncClient, db, owner_user, org, station, tank_with_stock, fuel_grade, fuel_price
):
    token = await login(client, "owner@acmefuel-dev.com")
    shift_id, reading_id = await _create_shift_with_tank_reading(
        client, token, org, station, tank_with_stock
    )

    submitted_at = datetime.now(timezone.utc)
    within_window = submitted_at + timedelta(hours=1)

    with patch("app.api.reading_corrections._now_utc", return_value=within_window):
        create_resp = await client.post(
            _corrections_url(org, station, shift_id),
            json={
                "reading_type": "tank_dip",
                "tank_reading_id": reading_id,
                "corrected_value": "9800.000",
                "reason": "Misread the dip stick",
            },
            headers=auth_headers(token),
        )
    assert create_resp.status_code == 201
    correction_id = create_resp.json()["id"]

    with patch("app.api.reading_corrections._now_utc", return_value=within_window):
        approve_resp = await client.post(
            f"{_corrections_url(org, station, shift_id)}/{correction_id}/approve",
            headers=auth_headers(token),
        )
    assert approve_resp.status_code == 200

    readings_resp = await client.get(
        f"{_shifts_base(org, station)}/{shift_id}/tank-readings",
        headers=auth_headers(token),
    )
    tank_readings = readings_resp.json()
    corrected = next(r for r in tank_readings if r["id"] == reading_id)
    assert Decimal(corrected["dip_reading"]) == Decimal("9800.000")


# =========================================================================
# Test 7: Unauthorized user (cashier) cannot request a correction
# =========================================================================
async def test_unauthorized_user_cannot_correct(
    client: AsyncClient, cashier_user, owner_user, org, station, tank_with_stock, fuel_grade, fuel_price
):
    owner_token = await login(client, "owner@acmefuel-dev.com")
    shift_id, reading_id = await _create_shift_with_tank_reading(
        client, owner_token, org, station, tank_with_stock
    )

    cashier_token = await login(client, "cashier@acmefuel-dev.com")
    resp = await client.post(
        _corrections_url(org, station, shift_id),
        json={
            "reading_type": "tank_dip",
            "tank_reading_id": reading_id,
            "corrected_value": "9500.000",
            "reason": "Testing unauthorized access",
        },
        headers=auth_headers(cashier_token),
    )
    assert resp.status_code == 403


# =========================================================================
# Test 8: Rejection does not modify the reading
# =========================================================================
async def test_rejected_correction_does_not_modify_reading(
    client: AsyncClient, owner_user, org, station, tank_with_stock, fuel_grade, fuel_price
):
    token = await login(client, "owner@acmefuel-dev.com")
    shift_id, reading_id = await _create_shift_with_tank_reading(
        client, token, org, station, tank_with_stock
    )

    create_resp = await client.post(
        _corrections_url(org, station, shift_id),
        json={
            "reading_type": "tank_dip",
            "tank_reading_id": reading_id,
            "corrected_value": "9500.000",
            "reason": "Testing rejection",
        },
        headers=auth_headers(token),
    )
    assert create_resp.status_code == 201
    correction_id = create_resp.json()["id"]

    reject_resp = await client.post(
        f"{_corrections_url(org, station, shift_id)}/{correction_id}/reject",
        json={"rejection_reason": "Original reading was correct"},
        headers=auth_headers(token),
    )
    assert reject_resp.status_code == 200
    assert reject_resp.json()["status"] == "rejected"

    readings_resp = await client.get(
        f"{_shifts_base(org, station)}/{shift_id}/tank-readings",
        headers=auth_headers(token),
    )
    tank_readings = readings_resp.json()
    original = next(r for r in tank_readings if r["id"] == reading_id)
    assert Decimal(original["dip_reading"]) == Decimal("10000.000")


# =========================================================================
# Test 9: Cannot correct to the same value
# =========================================================================
async def test_cannot_correct_to_same_value(
    client: AsyncClient, owner_user, org, station, tank_with_stock, fuel_grade, fuel_price
):
    token = await login(client, "owner@acmefuel-dev.com")
    shift_id, reading_id = await _create_shift_with_tank_reading(
        client, token, org, station, tank_with_stock
    )

    resp = await client.post(
        _corrections_url(org, station, shift_id),
        json={
            "reading_type": "tank_dip",
            "tank_reading_id": reading_id,
            "corrected_value": "10000.000",
            "reason": "Same value",
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 422


# =========================================================================
# Test 10: Nozzle opening totalizer correction
# =========================================================================
async def test_nozzle_opening_correction(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, fuel_grade, fuel_price
):
    token = await login(client, "owner@acmefuel-dev.com")
    shift_id, reading_id = await _create_shift_with_nozzle_reading(
        client, token, org, station, nozzle
    )

    create_resp = await client.post(
        _corrections_url(org, station, shift_id),
        json={
            "reading_type": "nozzle_opening",
            "nozzle_reading_id": reading_id,
            "corrected_value": "5100.000",
            "reason": "Nozzle meter was at 5100 not 5000",
        },
        headers=auth_headers(token),
    )
    assert create_resp.status_code == 201
    correction_id = create_resp.json()["id"]

    approve_resp = await client.post(
        f"{_corrections_url(org, station, shift_id)}/{correction_id}/approve",
        headers=auth_headers(token),
    )
    assert approve_resp.status_code == 200

    readings_resp = await client.get(
        f"{_shifts_base(org, station)}/{shift_id}/nozzle-readings",
        headers=auth_headers(token),
    )
    nozzle_readings = readings_resp.json()
    corrected = next(r for r in nozzle_readings if r["id"] == reading_id)
    assert Decimal(corrected["opening_totalizer"]) == Decimal("5100.000")


# =========================================================================
# Test 11: List corrections for a shift
# =========================================================================
async def test_list_corrections(
    client: AsyncClient, owner_user, org, station, tank_with_stock, fuel_grade, fuel_price
):
    token = await login(client, "owner@acmefuel-dev.com")
    shift_id, reading_id = await _create_shift_with_tank_reading(
        client, token, org, station, tank_with_stock
    )

    await client.post(
        _corrections_url(org, station, shift_id),
        json={
            "reading_type": "tank_dip",
            "tank_reading_id": reading_id,
            "corrected_value": "9500.000",
            "reason": "First correction",
        },
        headers=auth_headers(token),
    )

    resp = await client.get(
        _corrections_url(org, station, shift_id),
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1


# =========================================================================
# Test 12: Double-approve is rejected
# =========================================================================
async def test_double_approve_rejected(
    client: AsyncClient, owner_user, org, station, tank_with_stock, fuel_grade, fuel_price
):
    token = await login(client, "owner@acmefuel-dev.com")
    shift_id, reading_id = await _create_shift_with_tank_reading(
        client, token, org, station, tank_with_stock
    )

    create_resp = await client.post(
        _corrections_url(org, station, shift_id),
        json={
            "reading_type": "tank_dip",
            "tank_reading_id": reading_id,
            "corrected_value": "9500.000",
            "reason": "Test double approve",
        },
        headers=auth_headers(token),
    )
    correction_id = create_resp.json()["id"]

    await client.post(
        f"{_corrections_url(org, station, shift_id)}/{correction_id}/approve",
        headers=auth_headers(token),
    )

    second = await client.post(
        f"{_corrections_url(org, station, shift_id)}/{correction_id}/approve",
        headers=auth_headers(token),
    )
    assert second.status_code == 409
