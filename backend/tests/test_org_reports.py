from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dispenser import Dispenser
from app.models.fuel_price import FuelPrice
from app.models.nozzle import Nozzle
from app.models.station import Station
from app.models.stock_ledger_entry import StockLedgerEntry, StockMovementType
from app.models.tank import Tank
from tests.conftest import auth_headers, login
from tests.test_reports import _full_approved_shift

pytestmark = pytest.mark.asyncio

_DATE_FROM = (datetime.now(timezone.utc) - timedelta(days=2)).date().isoformat()
_DATE_TO = (datetime.now(timezone.utc) + timedelta(days=2)).date().isoformat()


def _org_reports_base(org) -> str:
    return f"/organizations/{org.id}/reports"


async def _second_station_with_tank(db: AsyncSession, org, fuel_grade, *, code="ST-2", stock="10000"):
    """A second station in the same organization, with its own tank
    (pre-stocked, like tank_with_stock), dispenser/nozzle and fuel price -
    everything test_reports.py's _full_approved_shift needs, built fresh
    since those fixtures are wired to the single `station` fixture."""
    station = Station(organization_id=org.id, name=f"Station {code}", code=code)
    db.add(station)
    await db.flush()

    tank = Tank(
        station_id=station.id, fuel_grade_id=fuel_grade.id, code="T1", name="Tank 1",
        capacity=Decimal("20000"), safe_fill_limit=Decimal("18000"),
    )
    db.add(tank)
    await db.flush()
    db.add(
        StockLedgerEntry(
            tank_id=tank.id, movement_type=StockMovementType.RECEIPT.value,
            quantity=Decimal(stock), reference_type="Test", reference_id=tank.id,
        )
    )
    dispenser = Dispenser(station_id=station.id, code="D1", name="Dispenser 1")
    db.add(dispenser)
    await db.flush()
    nozzle = Nozzle(dispenser_id=dispenser.id, tank_id=tank.id, code="N1")
    db.add(nozzle)
    db.add(
        FuelPrice(
            station_id=station.id, fuel_grade_id=fuel_grade.id,
            price_per_litre=Decimal("280.00"), effective_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )
    )
    await db.commit()
    await db.refresh(station)
    await db.refresh(tank)
    await db.refresh(nozzle)
    return station, tank, nozzle


# ---- 1/2/3. Single- and multi-station totals, combined == sum of parts ----


async def test_single_station_org_sales_matches_station_report(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, fuel_grade, fuel_price, cash_payment_method
):
    token = await login(client, "owner@acmefuel-dev.com")
    await _full_approved_shift(client, token, org, station, tank_with_stock, nozzle, cash_payment_method)

    resp = await client.get(
        f"{_org_reports_base(org)}/sales?date_from={_DATE_FROM}&date_to={_DATE_TO}", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["shift_count"] == 1
    assert body["total_litres_sold"] == "800.000"
    assert body["total_expected_revenue"] == "224000.00"
    assert len(body["by_station"]) == 1
    assert body["by_station"][0]["station_id"] == str(station.id)


async def test_multi_station_combined_sales_equals_sum_of_individual_stations(
    client: AsyncClient, db: AsyncSession, owner_user, org, station, tank_with_stock, nozzle, fuel_grade, fuel_price, cash_payment_method
):
    token = await login(client, "owner@acmefuel-dev.com")
    await _full_approved_shift(client, token, org, station, tank_with_stock, nozzle, cash_payment_method, litres="800")

    station2, tank2, nozzle2 = await _second_station_with_tank(db, org, fuel_grade)
    await _full_approved_shift(client, token, org, station2, tank2, nozzle2, cash_payment_method, litres="500")

    combined = await client.get(
        f"{_org_reports_base(org)}/sales?date_from={_DATE_FROM}&date_to={_DATE_TO}", headers=auth_headers(token)
    )
    assert combined.status_code == 200
    body = combined.json()
    assert body["shift_count"] == 2
    assert body["total_litres_sold"] == "1300.000"
    assert Decimal(body["total_expected_revenue"]) == Decimal("800") * Decimal("280.00") + Decimal("500") * Decimal("280.00")
    by_station = {r["station_id"]: r for r in body["by_station"]}
    assert by_station[str(station.id)]["litres_sold"] == "800.000"
    assert by_station[str(station2.id)]["litres_sold"] == "500.000"

    # Station-wise breakdown accuracy (requirement #4): each row matches
    # what that single station's own report shows for the same shifts.
    single1 = await client.get(
        f"/organizations/{org.id}/stations/{station.id}/reports/daily-fuel-sales?date_from={_DATE_FROM}&date_to={_DATE_TO}",
        headers=auth_headers(token),
    )
    single1_total = sum(Decimal(d["total_litres_sold"]) for d in single1.json())
    assert Decimal(by_station[str(station.id)]["litres_sold"]) == single1_total


# ---- 5/6. Cross-organization and unauthorized station filter denial ----


async def test_cross_organization_aggregation_is_denied(client: AsyncClient, owner_user, org, other_org, seeded_roles):
    token = await login(client, "owner@acmefuel-dev.com")
    resp = await client.get(
        f"{_org_reports_base(other_org)}/sales?date_from={_DATE_FROM}&date_to={_DATE_TO}", headers=auth_headers(token)
    )
    assert resp.status_code == 403


async def test_unauthorized_station_filter_is_denied(
    client: AsyncClient, db: AsyncSession, station_manager_user, org, station, fuel_grade, seeded_roles
):
    """station_manager_user holds report:read scoped to `station` only -
    filtering by a different, real station in the same org must be
    rejected, not silently widened or silently narrowed to nothing."""
    other_station, _, _ = await _second_station_with_tank(db, org, fuel_grade, code="ST-OTHER")
    token = await login(client, station_manager_user.email)
    resp = await client.get(
        f"{_org_reports_base(org)}/sales?date_from={_DATE_FROM}&date_to={_DATE_TO}&station_id={other_station.id}",
        headers=auth_headers(token),
    )
    assert resp.status_code == 403


async def test_requesting_a_station_from_a_different_organization_is_rejected(
    client: AsyncClient, owner_user, org, other_org, seeded_roles, db: AsyncSession
):
    foreign_station = Station(organization_id=other_org.id, name="Foreign", code="FOREIGN-1")
    db.add(foreign_station)
    await db.commit()
    await db.refresh(foreign_station)

    token = await login(client, "owner@acmefuel-dev.com")
    resp = await client.get(
        f"{_org_reports_base(org)}/sales?date_from={_DATE_FROM}&date_to={_DATE_TO}&station_id={foreign_station.id}",
        headers=auth_headers(token),
    )
    assert resp.status_code == 404


# ---- 7. Owner vs. station-level user permissions ----


async def test_station_scoped_user_sees_only_their_own_station_in_the_aggregate(
    client: AsyncClient, db: AsyncSession, owner_user, station_manager_user, org, station, tank_with_stock, nozzle, fuel_grade, fuel_price, cash_payment_method
):
    """station_manager_user holds report:read, but only scoped to
    `station` - a Cashier/Operator holds no report:read at all, so using
    one here would 403 regardless of station scoping and not test what
    this is actually about."""
    owner_token = await login(client, "owner@acmefuel-dev.com")
    await _full_approved_shift(client, owner_token, org, station, tank_with_stock, nozzle, cash_payment_method, litres="800")

    station2, tank2, nozzle2 = await _second_station_with_tank(db, org, fuel_grade)
    await _full_approved_shift(client, owner_token, org, station2, tank2, nozzle2, cash_payment_method, litres="500")

    manager_token = await login(client, station_manager_user.email)
    resp = await client.get(
        f"{_org_reports_base(org)}/sales?date_from={_DATE_FROM}&date_to={_DATE_TO}", headers=auth_headers(manager_token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_litres_sold"] == "800.000"
    assert len(body["by_station"]) == 1
    assert body["by_station"][0]["station_id"] == str(station.id)


# ---- 8. Revenue vs. cash collection separation ----


async def test_revenue_is_never_conflated_with_cash_collected(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, fuel_grade, fuel_price,
    cash_payment_method, credit_payment_method,
):
    token = await login(client, "owner@acmefuel-dev.com")
    shifts_base = f"/organizations/{org.id}/stations/{station.id}/shifts"
    shift = (await client.post(shifts_base, json={}, headers=auth_headers(token))).json()
    shift_id = shift["id"]
    await client.post(
        f"{shifts_base}/{shift_id}/tank-readings/opening",
        json={"tank_id": str(tank_with_stock.id), "dip_reading": "10000"}, headers=auth_headers(token),
    )
    nr = (
        await client.post(
            f"{shifts_base}/{shift_id}/nozzle-readings",
            json={"nozzle_id": str(nozzle.id), "opening_totalizer": "5000"}, headers=auth_headers(token),
        )
    ).json()
    await client.patch(
        f"{shifts_base}/{shift_id}/nozzle-readings/{nr['id']}/close",
        json={"closing_totalizer": "5800"}, headers=auth_headers(token),
    )
    await client.post(
        f"{shifts_base}/{shift_id}/tank-readings/closing",
        json={"tank_id": str(tank_with_stock.id), "dip_reading": "9200"}, headers=auth_headers(token),
    )
    await client.patch(f"{shifts_base}/{shift_id}/close", headers=auth_headers(token))

    # Half paid in cash, half on credit - total tender still equals
    # expected revenue, but cash collected is only half of it.
    await client.post(
        f"{shifts_base}/{shift_id}/tenders",
        json={"payment_method_id": str(cash_payment_method.id), "amount": "112000"}, headers=auth_headers(token),
    )
    await client.post(
        f"/organizations/{org.id}/credit-customers",
        json={"name": "Fleet Co"}, headers=auth_headers(token),
    )
    customer_id = (
        await client.get(f"/organizations/{org.id}/credit-customers", headers=auth_headers(token))
    ).json()[0]["id"]
    await client.post(
        f"{shifts_base}/{shift_id}/tenders",
        json={"payment_method_id": str(credit_payment_method.id), "amount": "112000", "credit_customer_id": customer_id},
        headers=auth_headers(token),
    )
    await client.post(
        f"{shifts_base}/{shift_id}/reconciliation",
        json={"actual_physical_cash": "112000"}, headers=auth_headers(token),
    )
    await client.patch(f"{shifts_base}/{shift_id}/approve", headers=auth_headers(token))

    resp = await client.get(
        f"{_org_reports_base(org)}/revenue?date_from={_DATE_FROM}&date_to={_DATE_TO}", headers=auth_headers(token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_recognized_revenue"] == "224000.00"
    assert body["total_tender_amount"] == "224000.00"
    assert body["cash_amount"] == "112000.00"
    assert body["credit_amount"] == "112000.00"
    # Revenue and cash collected are different numbers here by
    # construction (half the tender was credit, not cash) - the schema
    # never implies they're the same thing.
    assert Decimal(body["cash_amount"]) < Decimal(body["total_recognized_revenue"])


# ---- 9. Book stock vs. physical dip separation ----


async def test_stock_report_never_merges_book_stock_with_physical_dip(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, fuel_grade, fuel_price, cash_payment_method
):
    token = await login(client, "owner@acmefuel-dev.com")
    await _full_approved_shift(client, token, org, station, tank_with_stock, nozzle, cash_payment_method, litres="800")

    resp = await client.get(f"{_org_reports_base(org)}/stock", headers=auth_headers(token))
    assert resp.status_code == 200
    body = resp.json()
    tank_row = next(t for t in body["tanks"] if t["tank_id"] == str(tank_with_stock.id))
    # Book stock: 10000 receipt - 800 dispensed = 9200. The shift's own
    # closing dip was recorded as 9200 too, so they happen to agree here -
    # the point is they are reported as two distinct fields, not a sum.
    assert tank_row["book_stock"] == "9200.000"
    assert tank_row["last_physical_dip_reading"] == "9200.000"
    assert tank_row["last_physical_dip_at"] is not None


# ---- 10. Approved / pending / reversed / cancelled transaction handling ----


async def test_only_approved_shifts_count_toward_org_sales(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, fuel_grade, fuel_price, cash_payment_method
):
    token = await login(client, "owner@acmefuel-dev.com")
    shifts_base = f"/organizations/{org.id}/stations/{station.id}/shifts"
    # Open a shift and leave it open (never approved).
    await client.post(shifts_base, json={}, headers=auth_headers(token))

    resp = await client.get(
        f"{_org_reports_base(org)}/sales?date_from={_DATE_FROM}&date_to={_DATE_TO}", headers=auth_headers(token)
    )
    assert resp.status_code == 200
    assert resp.json()["shift_count"] == 0
    assert resp.json()["total_litres_sold"] == "0"


async def test_reversed_tender_excluded_from_org_revenue(
    client: AsyncClient, db: AsyncSession, owner_user, org, station, tank_with_stock, nozzle, fuel_grade, fuel_price, cash_payment_method
):
    token = await login(client, "owner@acmefuel-dev.com")
    shift_id = await _full_approved_shift(client, token, org, station, tank_with_stock, nozzle, cash_payment_method, litres="800")

    from app.models.shift_tender import ShiftTender

    tender = (
        await db.execute(select(ShiftTender).where(ShiftTender.shift_id == shift_id))
    ).scalars().first()
    tender.reversed_at = datetime.now(timezone.utc)
    await db.commit()

    resp = await client.get(
        f"{_org_reports_base(org)}/revenue?date_from={_DATE_FROM}&date_to={_DATE_TO}", headers=auth_headers(token)
    )
    assert resp.status_code == 200
    body = resp.json()
    # Expected (fuel) revenue is untouched - it never reads ShiftTender at
    # all - but the reversed tender must vanish from total_tender_amount.
    assert body["total_recognized_revenue"] == "224000.00"
    assert body["total_tender_amount"] == "0"


async def test_reversed_expense_excluded_from_approved_total_but_kept_in_grand_total(
    client: AsyncClient, db: AsyncSession, owner_user, org, seeded_roles
):
    token = await login(client, "owner@acmefuel-dev.com")
    today = datetime.now(timezone.utc).date().isoformat()
    create = await client.post(
        f"/organizations/{org.id}/expenses",
        json={"category": "fuel", "description": "Generator diesel", "amount": "5000", "expense_date": today},
        headers=auth_headers(token),
    )
    expense_id = create.json()["id"]
    await client.patch(f"/organizations/{org.id}/expenses/{expense_id}/approve", headers=auth_headers(token))
    await client.patch(
        f"/organizations/{org.id}/expenses/{expense_id}/reverse",
        json={"reason": "Entered twice by mistake"},
        headers=auth_headers(token),
    )

    resp = await client.get(
        f"{_org_reports_base(org)}/expenses?date_from={_DATE_FROM}&date_to={_DATE_TO}", headers=auth_headers(token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["grand_total"] == "5000.00"
    assert body["grand_approved"] == "0"


# ---- 11/12. Decimal precision, date boundaries ----


async def test_org_revenue_precision_matches_station_level_rounding(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, fuel_grade, fuel_price, cash_payment_method
):
    token = await login(client, "owner@acmefuel-dev.com")
    # An odd litre amount that doesn't round evenly at 280.00/litre.
    await _full_approved_shift(client, token, org, station, tank_with_stock, nozzle, cash_payment_method, litres="333")

    resp = await client.get(
        f"{_org_reports_base(org)}/sales?date_from={_DATE_FROM}&date_to={_DATE_TO}", headers=auth_headers(token)
    )
    body = resp.json()
    assert body["total_expected_revenue"] == str(Decimal("333") * Decimal("280.00"))


async def test_date_range_boundaries_are_inclusive_like_the_station_level_report(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, fuel_grade, fuel_price, cash_payment_method
):
    token = await login(client, "owner@acmefuel-dev.com")
    await _full_approved_shift(client, token, org, station, tank_with_stock, nozzle, cash_payment_method, litres="800")

    today = datetime.now(timezone.utc).date().isoformat()
    resp = await client.get(
        f"{_org_reports_base(org)}/sales?date_from={today}&date_to={today}", headers=auth_headers(token)
    )
    assert resp.status_code == 200
    assert resp.json()["shift_count"] == 1

    yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
    resp2 = await client.get(
        f"{_org_reports_base(org)}/sales?date_from={yesterday}&date_to={yesterday}", headers=auth_headers(token)
    )
    assert resp2.json()["shift_count"] == 0


async def test_invalid_date_range_is_rejected(client: AsyncClient, owner_user, org, seeded_roles):
    token = await login(client, "owner@acmefuel-dev.com")
    resp = await client.get(
        f"{_org_reports_base(org)}/sales?date_from={_DATE_TO}&date_to={_DATE_FROM}", headers=auth_headers(token)
    )
    assert resp.status_code == 422


# ---- 13. Attendance duplicate prevention ----


async def test_attendance_does_not_double_count_an_employee_present_at_two_stations_same_day(
    client: AsyncClient, db: AsyncSession, owner_user, org, station, fuel_grade, seeded_roles
):
    station2, _, _ = await _second_station_with_tank(db, org, fuel_grade)

    from app.models.attendance import AttendanceRecord

    today = datetime.now(timezone.utc).date()
    db.add(
        AttendanceRecord(
            organization_id=org.id, station_id=station.id, user_id=owner_user.id,
            attendance_date=today, status="present", recorded_by_user_id=owner_user.id,
        )
    )
    db.add(
        AttendanceRecord(
            organization_id=org.id, station_id=station2.id, user_id=owner_user.id,
            attendance_date=today, status="late", recorded_by_user_id=owner_user.id,
        )
    )
    await db.commit()

    token = await login(client, "owner@acmefuel-dev.com")
    resp = await client.get(
        f"{_org_reports_base(org)}/attendance?date_from={today.isoformat()}&date_to={today.isoformat()}",
        headers=auth_headers(token),
    )
    assert resp.status_code == 200
    body = resp.json()
    day = body["days"][0]
    # Present at station A, late at station B, same person, same day -
    # counted once overall, resolved toward "present" (the documented
    # priority rule), never twice.
    assert day["present_count"] + day["absent_count"] + day["late_count"] + day["half_day_count"] + day["leave_count"] == 1
    assert day["present_count"] == 1

    # Station-wise breakdown is NOT deduplicated - each station's own
    # attendance record still shows there.
    by_station = {r["station_id"]: r for r in body["by_station"]}
    assert by_station[str(station.id)]["present_count"] == 1
    assert by_station[str(station2.id)]["late_count"] == 1


# ---- 14. Empty station and empty organization responses ----


async def test_empty_organization_reports_return_zero_not_an_error(client: AsyncClient, superuser, seeded_roles, db: AsyncSession):
    from app.models.organization import Organization

    empty_org = Organization(name="Empty Fuel Co")
    db.add(empty_org)
    await db.commit()
    await db.refresh(empty_org)

    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    session_resp = await client.post(
        "/platform/support-sessions",
        json={"organization_id": str(empty_org.id), "reason": "Checking a brand-new organization with no stations yet.", "duration_minutes": 15},
        headers=auth_headers(admin_token),
    )
    assert session_resp.status_code == 201

    resp = await client.get(
        f"{_org_reports_base(empty_org)}/sales?date_from={_DATE_FROM}&date_to={_DATE_TO}", headers=auth_headers(admin_token)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["shift_count"] == 0
    assert body["total_litres_sold"] == "0"
    assert body["by_station"] == []

    stock_resp = await client.get(f"{_org_reports_base(empty_org)}/stock", headers=auth_headers(admin_token))
    assert stock_resp.status_code == 200
    assert stock_resp.json()["tanks"] == []


async def test_station_with_no_activity_reports_zero(client: AsyncClient, owner_user, org, station, seeded_roles):
    token = await login(client, "owner@acmefuel-dev.com")
    resp = await client.get(
        f"{_org_reports_base(org)}/sales?date_from={_DATE_FROM}&date_to={_DATE_TO}", headers=auth_headers(token)
    )
    assert resp.status_code == 200
    assert resp.json()["total_litres_sold"] == "0"


async def test_daily_sales_attributes_a_shift_to_its_own_day_and_zero_fills_the_rest(
    client: AsyncClient, owner_user, org, station, tank_with_stock, nozzle, fuel_grade, fuel_price, cash_payment_method
):
    token = await login(client, "owner@acmefuel-dev.com")
    await _full_approved_shift(client, token, org, station, tank_with_stock, nozzle, cash_payment_method, litres="800")

    resp = await client.get(
        f"{_org_reports_base(org)}/daily-sales?date_from={_DATE_FROM}&date_to={_DATE_TO}", headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    today = datetime.now(timezone.utc).date().isoformat()
    days_by_date = {d["sales_date"]: d for d in body["days"]}

    # Every day in the requested range appears, not just days with activity.
    assert days_by_date[today]["litres_sold"] == "800.000"
    assert days_by_date[today]["expected_revenue"] == "224000.00"
    other_days = [d for d in body["days"] if d["sales_date"] != today]
    assert len(other_days) == len(body["days"]) - 1
    for d in other_days:
        assert d["litres_sold"] == "0"
        assert d["expected_revenue"] == "0"


async def test_daily_sales_combines_same_day_shifts_across_authorized_stations(
    client: AsyncClient, db: AsyncSession, owner_user, org, station, tank_with_stock, nozzle, fuel_grade, fuel_price, cash_payment_method
):
    token = await login(client, "owner@acmefuel-dev.com")
    await _full_approved_shift(client, token, org, station, tank_with_stock, nozzle, cash_payment_method, litres="800")
    station2, tank2, nozzle2 = await _second_station_with_tank(db, org, fuel_grade)
    await _full_approved_shift(client, token, org, station2, tank2, nozzle2, cash_payment_method, litres="500")

    resp = await client.get(
        f"{_org_reports_base(org)}/daily-sales?date_from={_DATE_FROM}&date_to={_DATE_TO}", headers=auth_headers(token)
    )
    today = datetime.now(timezone.utc).date().isoformat()
    body = {d["sales_date"]: d for d in resp.json()["days"]}
    assert body[today]["litres_sold"] == "1300.000"
    assert body[today]["expected_revenue"] == str(Decimal("224000.00") + Decimal("500") * Decimal("280.00"))


async def test_daily_sales_rejects_an_unauthorized_station_filter(
    client: AsyncClient, db: AsyncSession, station_manager_user, org, station, fuel_grade, seeded_roles
):
    """station_manager_user holds report:read scoped to `station` only -
    same rule as the sibling /sales endpoint's own test."""
    other_station, _, _ = await _second_station_with_tank(db, org, fuel_grade, code="ST-OTHER-DS")
    token = await login(client, station_manager_user.email)
    resp = await client.get(
        f"{_org_reports_base(org)}/daily-sales?date_from={_DATE_FROM}&date_to={_DATE_TO}&station_id={other_station.id}",
        headers=auth_headers(token),
    )
    assert resp.status_code == 403


# ---- 15. Support-session read-only restrictions (Phase 5b preserved) ----


async def test_superuser_needs_an_active_support_session_to_read_org_wide_reports(
    client: AsyncClient, superuser, org, seeded_roles
):
    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    resp = await client.get(
        f"{_org_reports_base(org)}/sales?date_from={_DATE_FROM}&date_to={_DATE_TO}", headers=auth_headers(admin_token)
    )
    assert resp.status_code == 403


async def test_support_session_grants_read_only_access_to_org_wide_reports(
    client: AsyncClient, superuser, org, station, seeded_roles
):
    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")
    session_resp = await client.post(
        "/platform/support-sessions",
        json={"organization_id": str(org.id), "reason": "Investigating a client-reported reporting discrepancy.", "duration_minutes": 15},
        headers=auth_headers(admin_token),
    )
    assert session_resp.status_code == 201

    resp = await client.get(
        f"{_org_reports_base(org)}/sales?date_from={_DATE_FROM}&date_to={_DATE_TO}", headers=auth_headers(admin_token)
    )
    assert resp.status_code == 200


# ---- 16. Query efficiency / N+1 regression check ----


async def test_org_sales_litres_query_runs_once_regardless_of_station_count(
    client: AsyncClient, db: AsyncSession, owner_user, org, station, tank_with_stock, nozzle, fuel_grade, fuel_price, cash_payment_method
):
    """Not a strict N+1 ban across the whole endpoint
    (compute_expected_fuel_revenue_by_grade is already, deliberately,
    O(shifts) per the existing single-station report - see
    docs/PHASE_8B_ORGANIZATION_AGGREGATION_REPORT.md's performance
    section) - this guards the part that IS meant to be a single
    aggregate: the litres-sold ledger query must not re-run per station
    or per shift."""
    from sqlalchemy import event

    from tests.conftest import test_engine

    token = await login(client, "owner@acmefuel-dev.com")
    await _full_approved_shift(client, token, org, station, tank_with_stock, nozzle, cash_payment_method, litres="800")

    station2, tank2, nozzle2 = await _second_station_with_tank(db, org, fuel_grade)
    await _full_approved_shift(client, token, org, station2, tank2, nozzle2, cash_payment_method, litres="500")

    ledger_query_count = 0

    def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        nonlocal ledger_query_count
        if "stock_ledger_entries" in statement and "fuel_grade_id" in statement:
            ledger_query_count += 1

    event.listen(test_engine.sync_engine, "before_cursor_execute", _before_cursor_execute)
    try:
        resp = await client.get(
            f"{_org_reports_base(org)}/sales?date_from={_DATE_FROM}&date_to={_DATE_TO}", headers=auth_headers(token)
        )
    finally:
        event.remove(test_engine.sync_engine, "before_cursor_execute", _before_cursor_execute)

    assert resp.status_code == 200
    assert resp.json()["shift_count"] == 2
    assert ledger_query_count == 1, (
        f"Expected the litres-sold ledger query to run exactly once across both stations, ran {ledger_query_count} times"
    )
