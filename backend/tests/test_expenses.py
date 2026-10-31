import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers, login

pytestmark = pytest.mark.asyncio


def _base(org) -> str:
    return f"/organizations/{org.id}/expenses"


async def test_create_approve_expense_lifecycle(client: AsyncClient, owner_user, org, station):
    token = await login(client, "owner@acmefuel-dev.com")
    create = await client.post(
        _base(org),
        json={
            "station_id": str(station.id),
            "category": "maintenance",
            "description": "Pump repair",
            "amount": "1500.00",
            "expense_date": "2026-01-01",
        },
        headers=auth_headers(token),
    )
    assert create.status_code == 201, create.text
    expense_id = create.json()["id"]
    assert create.json()["status"] == "pending"

    approve = await client.patch(f"{_base(org)}/{expense_id}/approve", headers=auth_headers(token))
    assert approve.status_code == 200, approve.text
    assert approve.json()["status"] == "approved"


async def test_approving_an_already_decided_expense_is_rejected(client: AsyncClient, owner_user, org):
    token = await login(client, "owner@acmefuel-dev.com")
    create = await client.post(
        _base(org),
        json={"category": "rent", "description": "Monthly rent", "amount": "5000", "expense_date": "2026-01-01"},
        headers=auth_headers(token),
    )
    expense_id = create.json()["id"]
    first = await client.patch(f"{_base(org)}/{expense_id}/approve", headers=auth_headers(token))
    assert first.status_code == 200
    second = await client.patch(f"{_base(org)}/{expense_id}/approve", headers=auth_headers(token))
    assert second.status_code == 409


async def test_reject_expense_requires_a_reason(client: AsyncClient, owner_user, org):
    token = await login(client, "owner@acmefuel-dev.com")
    create = await client.post(
        _base(org),
        json={"category": "misc", "description": "Questionable claim", "amount": "200", "expense_date": "2026-01-01"},
        headers=auth_headers(token),
    )
    expense_id = create.json()["id"]

    missing_reason = await client.patch(
        f"{_base(org)}/{expense_id}/reject", json={"rejection_reason": ""}, headers=auth_headers(token)
    )
    assert missing_reason.status_code == 422

    reject = await client.patch(
        f"{_base(org)}/{expense_id}/reject",
        json={"rejection_reason": "No receipt attached"},
        headers=auth_headers(token),
    )
    assert reject.status_code == 200, reject.text
    assert reject.json()["status"] == "rejected"


async def test_reverse_requires_approved_status_first(client: AsyncClient, owner_user, org):
    token = await login(client, "owner@acmefuel-dev.com")
    create = await client.post(
        _base(org),
        json={"category": "fuel_resale", "description": "test", "amount": "50", "expense_date": "2026-01-01"},
        headers=auth_headers(token),
    )
    expense_id = create.json()["id"]

    still_pending = await client.patch(
        f"{_base(org)}/{expense_id}/reverse", json={"reason": "mistake"}, headers=auth_headers(token)
    )
    assert still_pending.status_code == 409

    await client.patch(f"{_base(org)}/{expense_id}/approve", headers=auth_headers(token))
    reversed_ = await client.patch(
        f"{_base(org)}/{expense_id}/reverse", json={"reason": "duplicate entry"}, headers=auth_headers(token)
    )
    assert reversed_.status_code == 200, reversed_.text
    assert reversed_.json()["reversed_at"] is not None


async def test_invalid_amount_is_rejected(client: AsyncClient, owner_user, org):
    token = await login(client, "owner@acmefuel-dev.com")
    resp = await client.post(
        _base(org),
        json={"category": "misc", "description": "x", "amount": "0", "expense_date": "2026-01-01"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 422


async def test_cashier_cannot_approve_expenses(client: AsyncClient, owner_user, cashier_user, org):
    owner_token = await login(client, "owner@acmefuel-dev.com")
    create = await client.post(
        _base(org),
        json={"category": "misc", "description": "x", "amount": "10", "expense_date": "2026-01-01"},
        headers=auth_headers(owner_token),
    )
    expense_id = create.json()["id"]

    cashier_token = await login(client, "cashier@acmefuel-dev.com")
    approve = await client.patch(f"{_base(org)}/{expense_id}/approve", headers=auth_headers(cashier_token))
    assert approve.status_code == 403


async def test_station_scoped_role_cannot_see_other_stations_org_wide_expense_filter(
    client: AsyncClient, owner_user, station_manager_user, org, station, other_org
):
    """
    A station-scoped role still sees org-wide (station_id is NULL)
    expenses, mirroring the audit log's own visibility rule - but must not
    see another station's expense.
    """
    owner_token = await login(client, "owner@acmefuel-dev.com")
    await client.post(
        _base(org),
        json={"category": "head_office", "description": "org-wide", "amount": "100", "expense_date": "2026-01-01"},
        headers=auth_headers(owner_token),
    )
    manager_token = await login(client, "manager@acmefuel-dev.com")
    listing = await client.get(_base(org), headers=auth_headers(manager_token))
    assert listing.status_code == 200, listing.text
    assert any(e["category"] == "head_office" for e in listing.json())
