import os
import uuid
from collections.abc import AsyncGenerator
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production-use-only")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://cynvexa:cynvexa@localhost:5432/cynvexa_test"
)
os.environ.setdefault("ENV", "test")

from app import models  # noqa: E402,F401
from app.config import get_settings  # noqa: E402
from app.core.permission_codes import ALL_PERMISSIONS, SEED_ROLES  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.organization import Organization  # noqa: E402
from app.models.role import Permission, Role  # noqa: E402
from app.models.station import Station  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.user_station_role import UserStationRole  # noqa: E402

settings = get_settings()
# NullPool: no pooled connections are kept alive across awaits/event-loop boundaries,
# which avoids pytest-asyncio's per-test event loops corrupting a pooled connection's
# loop-bound internals (manifests as asyncpg "another operation is in progress").
test_engine = create_async_engine(settings.database_url, poolclass=NullPool)
TestSessionLocal = async_sessionmaker(bind=test_engine, expire_on_commit=False, autoflush=False)


@pytest_asyncio.fixture(scope="session", autouse=True, loop_scope="session")
async def _create_schema():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await test_engine.dispose()


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        yield session


@pytest.fixture(autouse=True)
def _reset_login_limiter():
    """The login rate limiter (app/core/rate_limit.py) is a module-level
    singleton shared by the whole test process - without this, a handful
    of deliberate failed-login tests sharing the same test-client "IP"
    could accumulate across the suite and start tripping 429 on later,
    unrelated tests. Same isolation principle as _clean_tables, for
    in-memory state instead of DB state."""
    from app.core.rate_limit import login_limiter

    login_limiter._attempts.clear()
    yield
    login_limiter._attempts.clear()


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables():
    """Each test starts from a fully empty database (including the permission/role
    catalog, which the `seeded_roles` fixture recreates per-test) so tests never
    depend on ordering or leak state into one another."""
    yield
    async with test_engine.begin() as conn:
        for table in (
            "inventory_movements",
            "inventory_items",
            "supplier_invoices",
            "supplier_payments",
            "credit_customer_payments",
            "expenses",
            "shift_reconciliation_amendments",
            "shift_reconciliations",
            "shift_tenders",
            "shift_cash_movements",
            "payment_methods",
            "credit_customers",
            "shift_price_change_readings",
            "shift_price_changes",
            "shift_exceptional_events",
            "shift_nozzle_readings",
            "shift_tank_readings",
            "shifts",
            "stock_ledger_entries",
            "attachments",
            "tanker_receipts",
            "nozzles",
            "tanks",
            "dispensers",
            "fuel_prices",
            "fuel_grades",
            "suppliers",
            "user_station_roles",
            "audit_logs",
            "refresh_tokens",
            "role_permissions",
            "roles",
            "permissions",
            "stations",
            "organizations",
            "users",
        ):
            await conn.execute(__import__("sqlalchemy").text(f'TRUNCATE TABLE "{table}" CASCADE'))


@pytest_asyncio.fixture
async def seeded_roles(db: AsyncSession) -> dict[str, Role]:
    permissions = {}
    for code, description in ALL_PERMISSIONS.items():
        perm = Permission(code=code, description=description)
        db.add(perm)
        permissions[code] = perm
    await db.flush()

    roles: dict[str, Role] = {}
    for role_name, codes in SEED_ROLES.items():
        role = Role(name=role_name, description=f"Seeded: {role_name}", is_system=True)
        role.permissions = [permissions[c] for c in codes]
        db.add(role)
        roles[role_name] = role
    await db.commit()

    for role in roles.values():
        await db.refresh(role)
    return roles


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async def _override_get_db():
        async with TestSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def _create_user(db: AsyncSession, email: str, password: str = "a-strong-password-123") -> User:
    user = User(email=email, full_name="Test User", hashed_password=hash_password(password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def org(db: AsyncSession) -> Organization:
    organization = Organization(name="Acme Fuel Co")
    db.add(organization)
    await db.commit()
    await db.refresh(organization)
    return organization


@pytest_asyncio.fixture
async def other_org(db: AsyncSession) -> Organization:
    organization = Organization(name="Other Fuel Co")
    db.add(organization)
    await db.commit()
    await db.refresh(organization)
    return organization


@pytest_asyncio.fixture
async def station(db: AsyncSession, org: Organization) -> Station:
    s = Station(organization_id=org.id, name="Main Station", code="STN-1")
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


@pytest_asyncio.fixture
async def owner_user(db: AsyncSession, org: Organization, seeded_roles: dict[str, Role]) -> User:
    user = await _create_user(db, "owner@acmefuel-dev.com")
    assignment = UserStationRole(
        user_id=user.id,
        organization_id=org.id,
        station_id=None,
        role_id=seeded_roles["Owner"].id,
    )
    db.add(assignment)
    await db.commit()
    return user


@pytest_asyncio.fixture
async def cashier_user(
    db: AsyncSession, org: Organization, station: Station, seeded_roles: dict[str, Role]
) -> User:
    user = await _create_user(db, "cashier@acmefuel-dev.com")
    assignment = UserStationRole(
        user_id=user.id,
        organization_id=org.id,
        station_id=station.id,
        role_id=seeded_roles["Cashier / Operator"].id,
    )
    db.add(assignment)
    await db.commit()
    return user


@pytest_asyncio.fixture
async def station_manager_user(
    db: AsyncSession, org: Organization, station: Station, seeded_roles: dict[str, Role]
) -> User:
    user = await _create_user(db, "manager@acmefuel-dev.com")
    assignment = UserStationRole(
        user_id=user.id,
        organization_id=org.id,
        station_id=station.id,
        role_id=seeded_roles["Station Manager"].id,
    )
    db.add(assignment)
    await db.commit()
    return user


@pytest_asyncio.fixture
async def fuel_grade(db: AsyncSession, org: Organization):
    from app.models.fuel_grade import FuelGrade

    grade = FuelGrade(organization_id=org.id, name="Petrol 92", code="P92")
    db.add(grade)
    await db.commit()
    await db.refresh(grade)
    return grade


@pytest_asyncio.fixture
async def supplier(db: AsyncSession, org: Organization):
    from app.models.supplier import Supplier

    s = Supplier(organization_id=org.id, name="Acme Fuel Supply")
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


@pytest_asyncio.fixture
async def tank(db: AsyncSession, station: Station, fuel_grade):
    from decimal import Decimal

    from app.models.tank import Tank

    t = Tank(
        station_id=station.id,
        fuel_grade_id=fuel_grade.id,
        code="T1",
        name="Tank 1",
        capacity=Decimal("20000"),
        safe_fill_limit=Decimal("18000"),
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


@pytest_asyncio.fixture
async def tank_with_stock(db: AsyncSession, tank):
    """A tank that already has 10,000L of book stock, posted via a direct
    ledger entry (bypassing the receipt workflow, which Phase C's tests
    don't need to re-exercise) - shift tests need a tank that isn't empty."""
    from decimal import Decimal

    from app.models.stock_ledger_entry import StockLedgerEntry, StockMovementType

    db.add(
        StockLedgerEntry(
            tank_id=tank.id,
            movement_type=StockMovementType.RECEIPT.value,
            quantity=Decimal("10000"),
            reference_type="Test",
            reference_id=tank.id,
        )
    )
    await db.commit()
    return tank


@pytest_asyncio.fixture
async def dispenser(db: AsyncSession, station: Station):
    from app.models.dispenser import Dispenser

    d = Dispenser(station_id=station.id, code="D1", name="Dispenser 1")
    db.add(d)
    await db.commit()
    await db.refresh(d)
    return d


@pytest_asyncio.fixture
async def nozzle(db: AsyncSession, dispenser, tank_with_stock):
    from app.models.nozzle import Nozzle

    n = Nozzle(dispenser_id=dispenser.id, tank_id=tank_with_stock.id, code="N1")
    db.add(n)
    await db.commit()
    await db.refresh(n)
    return n


@pytest_asyncio.fixture
async def fuel_price(db: AsyncSession, station: Station, fuel_grade):
    from datetime import datetime, timezone
    from decimal import Decimal

    from app.models.fuel_price import FuelPrice

    p = FuelPrice(
        station_id=station.id,
        fuel_grade_id=fuel_grade.id,
        price_per_litre=Decimal("280.00"),
        effective_from=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


@pytest_asyncio.fixture
async def cash_payment_method(db: AsyncSession, org: Organization):
    from app.models.payment_method import PaymentMethod

    m = PaymentMethod(organization_id=org.id, code="CASH", name="Cash", category="cash")
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return m


@pytest_asyncio.fixture
async def card_payment_method(db: AsyncSession, org: Organization):
    from app.models.payment_method import PaymentMethod

    m = PaymentMethod(organization_id=org.id, code="CARD", name="Visa Card", category="card")
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return m


@pytest_asyncio.fixture
async def credit_payment_method(db: AsyncSession, org: Organization):
    from app.models.payment_method import PaymentMethod

    m = PaymentMethod(organization_id=org.id, code="CREDIT", name="Fleet Credit", category="credit")
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return m


@pytest_asyncio.fixture
async def credit_customer(db: AsyncSession, org: Organization):
    from app.models.credit_customer import CreditCustomer

    c = CreditCustomer(organization_id=org.id, name="Acme Logistics")
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


@pytest_asyncio.fixture
async def inventory_item(db: AsyncSession, org: Organization, station: Station):
    from app.models.inventory_item import InventoryItem

    item = InventoryItem(
        organization_id=org.id,
        station_id=station.id,
        sku="OIL-5W30",
        name="Engine Oil 5W-30 (1L)",
        unit="bottle",
        reorder_level=Decimal("10"),
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@pytest_asyncio.fixture
async def superuser(db: AsyncSession) -> User:
    user = User(
        email="platform-admin@cynvexa-platform-dev.com",
        full_name="Platform Admin",
        hashed_password=hash_password("a-strong-password-123"),
        is_superuser=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def login(client: AsyncClient, email: str, password: str = "a-strong-password-123") -> str:
    resp = await client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
