"""
Comprehensive tests for the attendance and payroll module (Day 4).

Coverage:
 1. Attendance CRUD (create, list, update)
 2. Duplicate attendance prevention (unique per station+user+date)
 3. Station isolation — records at station A invisible from station B
 4. Permission checks — cashier cannot create/read attendance
 5. All status types (present, absent, late, half_day, leave)
 6. Invalid status rejected
 7. Check-in/check-out times stored correctly
 8. Attendance update and audit trail
 9. Date range filtering
10. Payroll rule CRUD
11. Duplicate payroll rule name rejected
12. Payroll rule update (deactivate, change amounts)
13. Salary generation with deductions
14. Salary with multiple late arrivals
15. Salary with no deduction rule (zero deductions)
16. Salary period validation (end before start)
17. Salary duplicate period rejected
18. Salary finalization
19. Double-finalize rejected
20. Cashier cannot access payroll
21. Organization isolation — different org cannot see attendance
"""
import uuid
from datetime import date, time
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.organization import Organization
from app.models.station import Station
from app.models.user import User
from app.models.user_station_role import UserStationRole
from tests.conftest import auth_headers, login

pytestmark = pytest.mark.asyncio


def _att_url(org, station) -> str:
    return f"/organizations/{org.id}/stations/{station.id}/attendance"


def _payroll_url(org, station) -> str:
    return f"/organizations/{org.id}/stations/{station.id}/payroll"


# =========================================================================
# 1. Create and retrieve attendance record
# =========================================================================
async def test_create_and_list_attendance(
    client: AsyncClient, owner_user, org, station, db: AsyncSession, seeded_roles
):
    token = await login(client, "owner@acmefuel-dev.com")
    emp = User(email="emp1@test.com", full_name="Employee 1", hashed_password=hash_password("pw"))
    db.add(emp)
    await db.commit()
    await db.refresh(emp)

    resp = await client.post(
        _att_url(org, station),
        json={
            "user_id": str(emp.id),
            "attendance_date": "2026-11-01",
            "status": "present",
            "check_in_time": "08:00:00",
            "check_out_time": "17:00:00",
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "present"
    assert data["user_id"] == str(emp.id)
    assert data["source"] == "manual"
    assert data["attendance_date"] == "2026-11-01"

    list_resp = await client.get(_att_url(org, station), headers=auth_headers(token))
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


# =========================================================================
# 2. Duplicate attendance for same user+date+station is rejected
# =========================================================================
async def test_duplicate_attendance_rejected(
    client: AsyncClient, owner_user, org, station, db: AsyncSession, seeded_roles
):
    token = await login(client, "owner@acmefuel-dev.com")
    emp = User(email="emp2@test.com", full_name="Employee 2", hashed_password=hash_password("pw"))
    db.add(emp)
    await db.commit()
    await db.refresh(emp)

    payload = {"user_id": str(emp.id), "attendance_date": "2026-11-01", "status": "present"}

    first = await client.post(_att_url(org, station), json=payload, headers=auth_headers(token))
    assert first.status_code == 201

    second = await client.post(_att_url(org, station), json=payload, headers=auth_headers(token))
    assert second.status_code == 409


# =========================================================================
# 3. Station isolation — records at station A invisible from station B
# =========================================================================
async def test_attendance_station_isolation(
    client: AsyncClient, owner_user, org, station, db: AsyncSession, seeded_roles
):
    token = await login(client, "owner@acmefuel-dev.com")

    station_b = Station(organization_id=org.id, name="Station B", code="STN-B")
    db.add(station_b)
    await db.commit()
    await db.refresh(station_b)

    emp = User(email="emp3@test.com", full_name="Employee 3", hashed_password=hash_password("pw"))
    db.add(emp)
    await db.commit()
    await db.refresh(emp)

    await client.post(
        _att_url(org, station),
        json={"user_id": str(emp.id), "attendance_date": "2026-11-01", "status": "present"},
        headers=auth_headers(token),
    )

    resp_b = await client.get(
        f"/organizations/{org.id}/stations/{station_b.id}/attendance",
        headers=auth_headers(token),
    )
    assert resp_b.status_code == 200
    assert len(resp_b.json()) == 0


# =========================================================================
# 4. Cashier cannot create or read attendance
# =========================================================================
async def test_cashier_cannot_access_attendance(
    client: AsyncClient, cashier_user, owner_user, org, station, db: AsyncSession, seeded_roles
):
    cashier_token = await login(client, "cashier@acmefuel-dev.com")
    owner_token = await login(client, "owner@acmefuel-dev.com")

    emp = User(email="emp4@test.com", full_name="Employee 4", hashed_password=hash_password("pw"))
    db.add(emp)
    await db.commit()
    await db.refresh(emp)

    create_resp = await client.post(
        _att_url(org, station),
        json={"user_id": str(emp.id), "attendance_date": "2026-11-01", "status": "present"},
        headers=auth_headers(cashier_token),
    )
    assert create_resp.status_code == 403

    list_resp = await client.get(_att_url(org, station), headers=auth_headers(cashier_token))
    assert list_resp.status_code == 403


# =========================================================================
# 5. All status types accepted
# =========================================================================
@pytest.mark.parametrize("status", ["present", "absent", "late", "half_day", "leave"])
async def test_all_attendance_statuses(
    client: AsyncClient, owner_user, org, station, db: AsyncSession, seeded_roles, status: str
):
    token = await login(client, "owner@acmefuel-dev.com")
    emp = User(
        email=f"emp-status-{status}@test.com",
        full_name=f"Emp {status}",
        hashed_password=hash_password("pw"),
    )
    db.add(emp)
    await db.commit()
    await db.refresh(emp)

    resp = await client.post(
        _att_url(org, station),
        json={"user_id": str(emp.id), "attendance_date": "2026-11-01", "status": status},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == status


# =========================================================================
# 6. Invalid status rejected
# =========================================================================
async def test_invalid_status_rejected(
    client: AsyncClient, owner_user, org, station, db: AsyncSession, seeded_roles
):
    token = await login(client, "owner@acmefuel-dev.com")
    emp = User(email="emp6@test.com", full_name="Employee 6", hashed_password=hash_password("pw"))
    db.add(emp)
    await db.commit()
    await db.refresh(emp)

    resp = await client.post(
        _att_url(org, station),
        json={"user_id": str(emp.id), "attendance_date": "2026-11-01", "status": "vacation"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 422


# =========================================================================
# 7. Check-in/check-out times stored correctly
# =========================================================================
async def test_checkin_checkout_times(
    client: AsyncClient, owner_user, org, station, db: AsyncSession, seeded_roles
):
    token = await login(client, "owner@acmefuel-dev.com")
    emp = User(email="emp7@test.com", full_name="Employee 7", hashed_password=hash_password("pw"))
    db.add(emp)
    await db.commit()
    await db.refresh(emp)

    resp = await client.post(
        _att_url(org, station),
        json={
            "user_id": str(emp.id),
            "attendance_date": "2026-11-01",
            "status": "present",
            "check_in_time": "07:55:00",
            "check_out_time": "18:10:00",
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["check_in_time"] == "07:55:00"
    assert data["check_out_time"] == "18:10:00"


# =========================================================================
# 8. Update attendance record and verify audit trail
# =========================================================================
async def test_update_attendance_record(
    client: AsyncClient, owner_user, org, station, db: AsyncSession, seeded_roles
):
    token = await login(client, "owner@acmefuel-dev.com")
    emp = User(email="emp8@test.com", full_name="Employee 8", hashed_password=hash_password("pw"))
    db.add(emp)
    await db.commit()
    await db.refresh(emp)

    create_resp = await client.post(
        _att_url(org, station),
        json={"user_id": str(emp.id), "attendance_date": "2026-11-01", "status": "present"},
        headers=auth_headers(token),
    )
    record_id = create_resp.json()["id"]

    patch_resp = await client.patch(
        f"{_att_url(org, station)}/{record_id}",
        json={"status": "late", "notes": "Arrived 30min late"},
        headers=auth_headers(token),
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "late"
    assert patch_resp.json()["notes"] == "Arrived 30min late"

    audit_resp = await client.get(
        f"/organizations/{org.id}/audit-log?entity_type=AttendanceRecord",
        headers=auth_headers(token),
    )
    assert audit_resp.status_code == 200
    logs = audit_resp.json()
    if isinstance(logs, dict):
        logs = logs.get("items", [])
    actions = [l["action"] for l in logs]
    assert "attendance.create" in actions
    assert "attendance.update" in actions


# =========================================================================
# 9. Date range filtering
# =========================================================================
async def test_attendance_date_filtering(
    client: AsyncClient, owner_user, org, station, db: AsyncSession, seeded_roles
):
    token = await login(client, "owner@acmefuel-dev.com")
    emp = User(email="emp9@test.com", full_name="Employee 9", hashed_password=hash_password("pw"))
    db.add(emp)
    await db.commit()
    await db.refresh(emp)

    for day in ("2026-11-01", "2026-11-02", "2026-11-03"):
        await client.post(
            _att_url(org, station),
            json={"user_id": str(emp.id), "attendance_date": day, "status": "present"},
            headers=auth_headers(token),
        )

    resp = await client.get(
        f"{_att_url(org, station)}?date_from=2026-11-02&date_to=2026-11-02",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["attendance_date"] == "2026-11-02"


# =========================================================================
# 10. Payroll rule creation
# =========================================================================
async def test_create_payroll_rule(
    client: AsyncClient, owner_user, org, station, db: AsyncSession, seeded_roles
):
    token = await login(client, "owner@acmefuel-dev.com")

    resp = await client.post(
        f"{_payroll_url(org, station)}/rules",
        json={
            "rule_name": "Default",
            "shift_start_time": "08:00:00",
            "late_threshold_minutes": 15,
            "half_day_threshold_minutes": 120,
            "late_deduction_amount": "200.00",
            "absent_deduction_amount": "1000.00",
            "half_day_deduction_amount": "500.00",
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["rule_name"] == "Default"
    assert Decimal(data["late_deduction_amount"]) == Decimal("200.00")
    assert data["is_active"] is True

    list_resp = await client.get(
        f"{_payroll_url(org, station)}/rules", headers=auth_headers(token)
    )
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


# =========================================================================
# 11. Duplicate payroll rule name rejected
# =========================================================================
async def test_duplicate_payroll_rule_name_rejected(
    client: AsyncClient, owner_user, org, station, db: AsyncSession, seeded_roles
):
    token = await login(client, "owner@acmefuel-dev.com")
    payload = {"rule_name": "Standard", "shift_start_time": "08:00:00"}

    first = await client.post(
        f"{_payroll_url(org, station)}/rules", json=payload, headers=auth_headers(token)
    )
    assert first.status_code == 201

    second = await client.post(
        f"{_payroll_url(org, station)}/rules", json=payload, headers=auth_headers(token)
    )
    assert second.status_code == 409


# =========================================================================
# 12. Update payroll rule — deactivate and change amounts
# =========================================================================
async def test_update_payroll_rule(
    client: AsyncClient, owner_user, org, station, db: AsyncSession, seeded_roles
):
    token = await login(client, "owner@acmefuel-dev.com")

    create_resp = await client.post(
        f"{_payroll_url(org, station)}/rules",
        json={
            "rule_name": "Updatable",
            "shift_start_time": "08:00:00",
            "late_deduction_amount": "100.00",
        },
        headers=auth_headers(token),
    )
    rule_id = create_resp.json()["id"]

    patch_resp = await client.patch(
        f"{_payroll_url(org, station)}/rules/{rule_id}",
        json={"late_deduction_amount": "300.00", "is_active": False},
        headers=auth_headers(token),
    )
    assert patch_resp.status_code == 200
    assert Decimal(patch_resp.json()["late_deduction_amount"]) == Decimal("300.00")
    assert patch_resp.json()["is_active"] is False


# =========================================================================
# 13. Salary generation with deductions
# =========================================================================
async def test_salary_generation_with_deductions(
    client: AsyncClient, owner_user, org, station, db: AsyncSession, seeded_roles
):
    token = await login(client, "owner@acmefuel-dev.com")
    emp = User(email="emp13@test.com", full_name="Employee 13", hashed_password=hash_password("pw"))
    db.add(emp)
    await db.commit()
    await db.refresh(emp)

    await client.post(
        f"{_payroll_url(org, station)}/rules",
        json={
            "rule_name": "Standard",
            "shift_start_time": "08:00:00",
            "late_deduction_amount": "200.00",
            "absent_deduction_amount": "1000.00",
            "half_day_deduction_amount": "500.00",
        },
        headers=auth_headers(token),
    )

    attendance_data = [
        ("2026-11-01", "present"),
        ("2026-11-02", "present"),
        ("2026-11-03", "late"),
        ("2026-11-04", "absent"),
        ("2026-11-05", "half_day"),
    ]
    for att_date, status in attendance_data:
        await client.post(
            _att_url(org, station),
            json={"user_id": str(emp.id), "attendance_date": att_date, "status": status},
            headers=auth_headers(token),
        )

    resp = await client.post(
        f"{_payroll_url(org, station)}/salary/generate",
        json={
            "user_id": str(emp.id),
            "period_start": "2026-11-01",
            "period_end": "2026-11-05",
            "base_salary": "30000.00",
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["days_present"] == 2
    assert data["days_late"] == 1
    assert data["days_absent"] == 1
    assert data["days_half_day"] == 1
    assert data["days_leave"] == 0
    expected_deductions = Decimal("200.00") + Decimal("1000.00") + Decimal("500.00")
    assert Decimal(data["total_deductions"]) == expected_deductions
    assert Decimal(data["net_salary"]) == Decimal("30000.00") - expected_deductions


# =========================================================================
# 14. Salary with multiple late arrivals
# =========================================================================
async def test_salary_multiple_lates(
    client: AsyncClient, owner_user, org, station, db: AsyncSession, seeded_roles
):
    token = await login(client, "owner@acmefuel-dev.com")
    emp = User(email="emp14@test.com", full_name="Employee 14", hashed_password=hash_password("pw"))
    db.add(emp)
    await db.commit()
    await db.refresh(emp)

    await client.post(
        f"{_payroll_url(org, station)}/rules",
        json={
            "rule_name": "Standard14",
            "shift_start_time": "08:00:00",
            "late_deduction_amount": "150.00",
            "absent_deduction_amount": "0.00",
            "half_day_deduction_amount": "0.00",
        },
        headers=auth_headers(token),
    )

    for day in range(1, 6):
        await client.post(
            _att_url(org, station),
            json={
                "user_id": str(emp.id),
                "attendance_date": f"2026-11-{day:02d}",
                "status": "late",
            },
            headers=auth_headers(token),
        )

    resp = await client.post(
        f"{_payroll_url(org, station)}/salary/generate",
        json={
            "user_id": str(emp.id),
            "period_start": "2026-11-01",
            "period_end": "2026-11-05",
            "base_salary": "25000.00",
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    assert resp.json()["days_late"] == 5
    assert Decimal(resp.json()["total_deductions"]) == Decimal("750.00")
    assert Decimal(resp.json()["net_salary"]) == Decimal("24250.00")


# =========================================================================
# 15. Salary with no active deduction rule — zero deductions
# =========================================================================
async def test_salary_no_active_rule_zero_deductions(
    client: AsyncClient, owner_user, org, station, db: AsyncSession, seeded_roles
):
    token = await login(client, "owner@acmefuel-dev.com")
    emp = User(email="emp15@test.com", full_name="Employee 15", hashed_password=hash_password("pw"))
    db.add(emp)
    await db.commit()
    await db.refresh(emp)

    for day in range(1, 4):
        await client.post(
            _att_url(org, station),
            json={
                "user_id": str(emp.id),
                "attendance_date": f"2026-11-{day:02d}",
                "status": "late",
            },
            headers=auth_headers(token),
        )

    resp = await client.post(
        f"{_payroll_url(org, station)}/salary/generate",
        json={
            "user_id": str(emp.id),
            "period_start": "2026-11-01",
            "period_end": "2026-11-03",
            "base_salary": "20000.00",
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    assert Decimal(resp.json()["total_deductions"]) == Decimal("0.00")
    assert Decimal(resp.json()["net_salary"]) == Decimal("20000.00")


# =========================================================================
# 16. Salary period validation — end before start rejected
# =========================================================================
async def test_salary_period_end_before_start(
    client: AsyncClient, owner_user, org, station, db: AsyncSession, seeded_roles
):
    token = await login(client, "owner@acmefuel-dev.com")
    emp = User(email="emp16@test.com", full_name="Employee 16", hashed_password=hash_password("pw"))
    db.add(emp)
    await db.commit()
    await db.refresh(emp)

    resp = await client.post(
        f"{_payroll_url(org, station)}/salary/generate",
        json={
            "user_id": str(emp.id),
            "period_start": "2026-11-30",
            "period_end": "2026-11-01",
            "base_salary": "20000.00",
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 422


# =========================================================================
# 17. Duplicate salary for same user+period rejected
# =========================================================================
async def test_duplicate_salary_rejected(
    client: AsyncClient, owner_user, org, station, db: AsyncSession, seeded_roles
):
    token = await login(client, "owner@acmefuel-dev.com")
    emp = User(email="emp17@test.com", full_name="Employee 17", hashed_password=hash_password("pw"))
    db.add(emp)
    await db.commit()
    await db.refresh(emp)

    payload = {
        "user_id": str(emp.id),
        "period_start": "2026-11-01",
        "period_end": "2026-11-30",
        "base_salary": "20000.00",
    }

    first = await client.post(
        f"{_payroll_url(org, station)}/salary/generate", json=payload, headers=auth_headers(token)
    )
    assert first.status_code == 201

    second = await client.post(
        f"{_payroll_url(org, station)}/salary/generate", json=payload, headers=auth_headers(token)
    )
    assert second.status_code == 409


# =========================================================================
# 18. Salary finalization
# =========================================================================
async def test_salary_finalization(
    client: AsyncClient, owner_user, org, station, db: AsyncSession, seeded_roles
):
    token = await login(client, "owner@acmefuel-dev.com")
    emp = User(email="emp18@test.com", full_name="Employee 18", hashed_password=hash_password("pw"))
    db.add(emp)
    await db.commit()
    await db.refresh(emp)

    gen_resp = await client.post(
        f"{_payroll_url(org, station)}/salary/generate",
        json={
            "user_id": str(emp.id),
            "period_start": "2026-11-01",
            "period_end": "2026-11-30",
            "base_salary": "25000.00",
        },
        headers=auth_headers(token),
    )
    salary_id = gen_resp.json()["id"]
    assert gen_resp.json()["is_finalized"] is False

    fin_resp = await client.patch(
        f"{_payroll_url(org, station)}/salary/{salary_id}/finalize",
        headers=auth_headers(token),
    )
    assert fin_resp.status_code == 200
    assert fin_resp.json()["is_finalized"] is True


# =========================================================================
# 19. Double-finalize rejected
# =========================================================================
async def test_double_finalize_rejected(
    client: AsyncClient, owner_user, org, station, db: AsyncSession, seeded_roles
):
    token = await login(client, "owner@acmefuel-dev.com")
    emp = User(email="emp19@test.com", full_name="Employee 19", hashed_password=hash_password("pw"))
    db.add(emp)
    await db.commit()
    await db.refresh(emp)

    gen_resp = await client.post(
        f"{_payroll_url(org, station)}/salary/generate",
        json={
            "user_id": str(emp.id),
            "period_start": "2026-11-01",
            "period_end": "2026-11-30",
            "base_salary": "25000.00",
        },
        headers=auth_headers(token),
    )
    salary_id = gen_resp.json()["id"]

    await client.patch(
        f"{_payroll_url(org, station)}/salary/{salary_id}/finalize",
        headers=auth_headers(token),
    )

    second = await client.patch(
        f"{_payroll_url(org, station)}/salary/{salary_id}/finalize",
        headers=auth_headers(token),
    )
    assert second.status_code == 409


# =========================================================================
# 20. Cashier cannot access payroll
# =========================================================================
async def test_cashier_cannot_access_payroll(
    client: AsyncClient, cashier_user, owner_user, org, station, db: AsyncSession, seeded_roles
):
    cashier_token = await login(client, "cashier@acmefuel-dev.com")

    rules_resp = await client.get(
        f"{_payroll_url(org, station)}/rules", headers=auth_headers(cashier_token)
    )
    assert rules_resp.status_code == 403

    salary_resp = await client.get(
        f"{_payroll_url(org, station)}/salary", headers=auth_headers(cashier_token)
    )
    assert salary_resp.status_code == 403


# =========================================================================
# 21. Organization isolation — other org cannot see attendance
# =========================================================================
async def test_attendance_organization_isolation(
    client: AsyncClient, owner_user, org, station, other_org, db: AsyncSession, seeded_roles
):
    token = await login(client, "owner@acmefuel-dev.com")

    other_station = Station(organization_id=other_org.id, name="Other Org Station", code="OTH-1")
    db.add(other_station)
    await db.commit()
    await db.refresh(other_station)

    emp = User(email="emp21@test.com", full_name="Employee 21", hashed_password=hash_password("pw"))
    db.add(emp)
    await db.commit()
    await db.refresh(emp)

    await client.post(
        _att_url(org, station),
        json={"user_id": str(emp.id), "attendance_date": "2026-11-01", "status": "present"},
        headers=auth_headers(token),
    )

    resp = await client.get(
        f"/organizations/{other_org.id}/stations/{other_station.id}/attendance",
        headers=auth_headers(token),
    )
    assert resp.status_code == 403
