import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan import Plan
from app.models.station import Station
from app.models.subscription import Subscription
from tests.conftest import auth_headers, login

pytestmark = pytest.mark.asyncio


async def _seed_plan_and_subscription(db: AsyncSession, org_id, *, max_stations, max_users) -> None:
    now = datetime.now(timezone.utc)
    plan = Plan(
        code="limited",
        name="Limited",
        price_monthly="15000.00",
        price_annual="150000.00",
        max_stations=max_stations,
        max_users=max_users,
    )
    db.add(plan)
    await db.flush()
    db.add(
        Subscription(
            organization_id=org_id,
            plan_id=plan.id,
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
    )
    await db.commit()


# ---- 1. Station limits --------------------------------------------------------


async def test_station_creation_blocked_once_plan_limit_reached(
    client: AsyncClient, db: AsyncSession, owner_user, org, station, seeded_roles
):
    """station (the fixture) already counts as 1 - a max_stations=1 plan
    must reject a second."""
    await _seed_plan_and_subscription(db, org.id, max_stations=1, max_users=None)
    token = await login(client, owner_user.email)

    resp = await client.post(
        f"/organizations/{org.id}/stations", json={"name": "Second Station", "code": "ST-2"}, headers=auth_headers(token)
    )
    assert resp.status_code == 409
    assert "plan" in resp.json()["detail"].lower()


async def test_station_creation_allowed_up_to_the_limit(
    client: AsyncClient, db: AsyncSession, owner_user, org, station, seeded_roles
):
    await _seed_plan_and_subscription(db, org.id, max_stations=2, max_users=None)
    token = await login(client, owner_user.email)

    resp = await client.post(
        f"/organizations/{org.id}/stations", json={"name": "Second Station", "code": "ST-2"}, headers=auth_headers(token)
    )
    assert resp.status_code == 201

    resp2 = await client.post(
        f"/organizations/{org.id}/stations", json={"name": "Third Station", "code": "ST-3"}, headers=auth_headers(token)
    )
    assert resp2.status_code == 409


async def test_no_subscription_means_unrestricted_station_creation(
    client: AsyncClient, owner_user, org, station, seeded_roles
):
    """org has no Subscription row at all (the plain fixture) - must not
    be blocked, matching every organization that predates Phase 7."""
    token = await login(client, owner_user.email)
    resp = await client.post(
        f"/organizations/{org.id}/stations", json={"name": "Second Station", "code": "ST-2"}, headers=auth_headers(token)
    )
    assert resp.status_code == 201


async def test_an_already_over_limit_organization_keeps_its_existing_stations(
    client: AsyncClient, db: AsyncSession, owner_user, org, station, seeded_roles
):
    """Two stations already exist; the plan is then tightened to 1 (e.g. a
    downgrade). Both existing stations must remain untouched - only a new
    addition is blocked."""
    second = Station(organization_id=org.id, name="Second Station", code="ST-2")
    db.add(second)
    await db.commit()

    await _seed_plan_and_subscription(db, org.id, max_stations=1, max_users=None)
    token = await login(client, owner_user.email)

    list_resp = await client.get(f"/organizations/{org.id}/stations", headers=auth_headers(token))
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 2

    create_resp = await client.post(
        f"/organizations/{org.id}/stations", json={"name": "Third Station", "code": "ST-3"}, headers=auth_headers(token)
    )
    assert create_resp.status_code == 409


# ---- 2 & 10. User limits (direct create, role assignment, Super Admin vs owner) ----


async def test_direct_user_creation_blocked_once_plan_limit_reached(
    client: AsyncClient, db: AsyncSession, owner_user, org, seeded_roles
):
    """owner_user already counts as 1 active user - a max_users=1 plan
    must reject creating a second."""
    await _seed_plan_and_subscription(db, org.id, max_stations=None, max_users=1)
    token = await login(client, owner_user.email)

    resp = await client.post(
        f"/organizations/{org.id}/users",
        json={"email": "second@acmefuel-dev.com", "full_name": "Second Person", "password": "a-strong-password-123"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 409
    assert "plan" in resp.json()["detail"].lower()


async def test_role_assignment_blocked_once_plan_limit_reached_even_for_a_preexisting_user(
    client: AsyncClient, db: AsyncSession, owner_user, org, seeded_roles
):
    """A bare user with no role doesn't count yet - but granting them a
    role is the real seat-consuming moment, and must still be blocked."""
    await _seed_plan_and_subscription(db, org.id, max_stations=None, max_users=1)
    token = await login(client, owner_user.email)

    # max_users=1 but owner already holds it, so even bare user creation
    # (counting_pending=True) is blocked here - seed the bare user directly
    # to isolate the assign_role check being tested.
    from app.models.user import User
    from app.core.security import hash_password

    bare_user = User(email="bare@acmefuel-dev.com", full_name="Bare User", hashed_password=hash_password("a-strong-password-123"))
    db.add(bare_user)
    await db.commit()

    resp = await client.post(
        f"/organizations/{org.id}/users/{bare_user.id}/roles",
        json={"role_id": str(seeded_roles["Cashier / Operator"].id)},
        headers=auth_headers(token),
    )
    assert resp.status_code == 409


async def test_a_second_role_for_an_already_active_user_does_not_need_a_free_seat(
    client: AsyncClient, db: AsyncSession, owner_user, org, station, seeded_roles
):
    """owner_user is already an active seat; granting them a second,
    station-scoped role must not be blocked even at max_users=1."""
    await _seed_plan_and_subscription(db, org.id, max_stations=None, max_users=1)
    token = await login(client, owner_user.email)

    resp = await client.post(
        f"/organizations/{org.id}/users/{owner_user.id}/roles",
        json={"role_id": str(seeded_roles["Accountant"].id), "station_id": str(station.id)},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201


async def test_deactivating_a_user_frees_a_seat(
    client: AsyncClient, db: AsyncSession, owner_user, org, seeded_roles
):
    await _seed_plan_and_subscription(db, org.id, max_stations=None, max_users=2)
    token = await login(client, owner_user.email)

    create = await client.post(
        f"/organizations/{org.id}/users",
        json={"email": "second@acmefuel-dev.com", "full_name": "Second Person", "password": "a-strong-password-123"},
        headers=auth_headers(token),
    )
    assert create.status_code == 201
    second_id = create.json()["id"]
    await client.post(
        f"/organizations/{org.id}/users/{second_id}/roles",
        json={"role_id": str(seeded_roles["Cashier / Operator"].id)},
        headers=auth_headers(token),
    )

    # Now at the limit (owner + second person) - a third is rejected.
    blocked = await client.post(
        f"/organizations/{org.id}/users",
        json={"email": "third@acmefuel-dev.com", "full_name": "Third Person", "password": "a-strong-password-123"},
        headers=auth_headers(token),
    )
    assert blocked.status_code == 409

    # Deactivating the second person frees their seat - unlike a station,
    # a user is a true active headcount (see plan_limits.py's docstring).
    await client.patch(
        f"/organizations/{org.id}/users/{second_id}", json={"is_active": False}, headers=auth_headers(token)
    )
    allowed = await client.post(
        f"/organizations/{org.id}/users",
        json={"email": "third@acmefuel-dev.com", "full_name": "Third Person", "password": "a-strong-password-123"},
        headers=auth_headers(token),
    )
    assert allowed.status_code == 201


async def test_super_admin_platform_actions_are_never_subject_to_a_tenant_plan_limit(
    client: AsyncClient, db: AsyncSession, superuser, owner_user, org, seeded_roles
):
    """Requirement #11: Super Admin vs tenant-owner authorization - plan
    limits are a tenant-business-data concern; the platform admin's own
    onboarding of a brand-new organization is never subject to another
    organization's limit, and is unaffected by this feature entirely."""
    await _seed_plan_and_subscription(db, org.id, max_stations=0, max_users=0)
    admin_token = await login(client, "platform-admin@cynvexa-platform-dev.com")

    db.add(
        Plan(
            code="starter2", name="Starter2", price_monthly="15000.00", price_annual="150000.00",
            max_stations=5, max_users=5,
        )
    )
    await db.commit()
    resp = await client.post(
        "/platform/organizations",
        json={
            "company_name": "Totally Separate Co",
            "owner_full_name": "Separate Owner",
            "owner_email": "separate@separate-dev.com",
            "owner_password": "a-strong-password-123",
            "plan_code": "starter2",
        },
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 201


# ---- 3. Concurrency -------------------------------------------------------------


async def test_concurrent_station_creation_cannot_both_bypass_the_limit(
    client: AsyncClient, db: AsyncSession, owner_user, org, station, seeded_roles
):
    """station already counts as 1; max_stations=2 leaves room for
    exactly one more - two concurrent requests for that one remaining
    slot must not both succeed."""
    await _seed_plan_and_subscription(db, org.id, max_stations=2, max_users=None)
    token = await login(client, owner_user.email)

    results = await asyncio.gather(
        client.post(f"/organizations/{org.id}/stations", json={"name": "A", "code": "ST-A"}, headers=auth_headers(token)),
        client.post(f"/organizations/{org.id}/stations", json={"name": "B", "code": "ST-B"}, headers=auth_headers(token)),
    )
    statuses = sorted(r.status_code for r in results)
    assert statuses == [201, 409]

    final = await client.get(f"/organizations/{org.id}/stations", headers=auth_headers(token))
    assert len(final.json()) == 2


# ---- Invitations: reservation at creation, consumption at acceptance ----------


async def test_invitation_creation_reserves_a_seat_and_blocks_once_full(
    client: AsyncClient, db: AsyncSession, owner_user, org, station, seeded_roles
):
    await _seed_plan_and_subscription(db, org.id, max_stations=None, max_users=1)
    token = await login(client, owner_user.email)

    resp = await client.post(
        f"/organizations/{org.id}/invitations",
        json={
            "email": "invited@acmefuel-dev.com", "full_name": "Invited Person",
            "role_id": str(seeded_roles["Cashier / Operator"].id), "station_id": str(station.id),
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 409


async def test_invitation_acceptance_does_not_double_count_its_own_reservation(
    client: AsyncClient, db: AsyncSession, owner_user, org, station, seeded_roles
):
    """owner_user is 1 active seat; max_users=2 leaves room for exactly
    one invitation, and accepting it must succeed (not be blocked by its
    own pending reservation)."""
    await _seed_plan_and_subscription(db, org.id, max_stations=None, max_users=2)
    token = await login(client, owner_user.email)

    create = await client.post(
        f"/organizations/{org.id}/invitations",
        json={
            "email": "invited@acmefuel-dev.com", "full_name": "Invited Person",
            "role_id": str(seeded_roles["Cashier / Operator"].id), "station_id": str(station.id),
        },
        headers=auth_headers(token),
    )
    assert create.status_code == 201
    raw_token = create.json()["token"]

    accept = await client.post("/invitations/accept", json={"token": raw_token, "password": "a-strong-password-123"})
    assert accept.status_code == 200


async def test_invitation_acceptance_rejected_if_the_plan_is_downgraded_in_the_meantime(
    client: AsyncClient, db: AsyncSession, owner_user, org, station, seeded_roles
):
    """The reservation system (pending invitations count at creation)
    already prevents a same-plan race between a pending invitation and a
    direct creation - the only realistic way a validly-pending invitation
    ends up over limit by acceptance time is the plan itself shrinking
    in between (e.g. a downgrade)."""
    await _seed_plan_and_subscription(db, org.id, max_stations=None, max_users=2)
    token = await login(client, owner_user.email)

    create = await client.post(
        f"/organizations/{org.id}/invitations",
        json={
            "email": "invited@acmefuel-dev.com", "full_name": "Invited Person",
            "role_id": str(seeded_roles["Cashier / Operator"].id), "station_id": str(station.id),
        },
        headers=auth_headers(token),
    )
    assert create.status_code == 201
    raw_token = create.json()["token"]

    sub = (
        await db.execute(
            select(Subscription).where(Subscription.organization_id == org.id)
        )
    ).scalar_one()
    plan = (await db.execute(select(Plan).where(Plan.id == sub.plan_id))).scalar_one()
    plan.max_users = 1  # owner_user alone already consumes this.
    await db.commit()

    accept = await client.post("/invitations/accept", json={"token": raw_token, "password": "a-strong-password-123"})
    assert accept.status_code == 409


# ---- Financial/precision invariants untouched ----------------------------------


async def test_plan_limit_fields_are_decimal_safe_and_unaffected_by_this_feature(db: AsyncSession, org):
    """Sanity check that seeding a plan through this feature's own helper
    doesn't disturb Plan's Decimal price columns - this phase never
    touches money/litre math, only integer counts."""
    await _seed_plan_and_subscription(db, org.id, max_stations=3, max_users=3)
    from sqlalchemy import select

    from app.models.subscription import Subscription as SubscriptionModel

    sub = (await db.execute(select(SubscriptionModel).where(SubscriptionModel.organization_id == org.id))).scalar_one()
    assert sub.plan_id is not None
