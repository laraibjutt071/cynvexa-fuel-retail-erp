"""
Seeds the permission/role catalog and, optionally, bootstraps the first platform
superuser. Run manually, never exposed over HTTP:

    python -m app.seed permissions-roles
    python -m app.seed superuser --email owner@example.com --password "..." --full-name "Platform Admin"

Idempotent: re-running only fills in what's missing.
"""

import argparse
import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.permission_codes import ALL_PERMISSIONS, SEED_ROLES
from app.core.security import hash_password
from app.database import AsyncSessionLocal
from app.models.plan import Plan
from app.models.role import Permission, Role
from app.models.user import User

# Starting defaults for the three example tiers the master prompt names -
# a platform admin can edit every field (including price) via
# PATCH /platform/plans/{id}; these are not fixed prices, just a sane
# starting catalog so the platform isn't empty on day one.
DEFAULT_PLANS: list[dict] = [
    {
        "code": "starter",
        "name": "Starter",
        "description": "One station, core fuel and shift management, basic reports.",
        "price_monthly": "15000",
        "price_annual": "150000",
        "max_stations": 1,
        "max_users": 5,
    },
    {
        "code": "business",
        "name": "Business",
        "description": "Multiple stations, full reconciliation, supplier/customer ledgers.",
        "price_monthly": "35000",
        "price_annual": "350000",
        "max_stations": 5,
        "max_users": 25,
    },
    {
        "code": "enterprise",
        "name": "Enterprise",
        "description": "Unlimited stations, advanced analytics, priority support.",
        "price_monthly": "75000",
        "price_annual": "750000",
        "max_stations": None,
        "max_users": None,
    },
]


async def seed_permissions_and_roles() -> None:
    async with AsyncSessionLocal() as db:
        existing_permissions = {
            p.code: p for p in (await db.execute(select(Permission))).scalars().all()
        }
        for code, description in ALL_PERMISSIONS.items():
            if code not in existing_permissions:
                perm = Permission(code=code, description=description)
                db.add(perm)
                existing_permissions[code] = perm
        await db.flush()

        existing_roles = {
            r.name: r
            for r in (
                await db.execute(select(Role).options(selectinload(Role.permissions)))
            ).scalars().all()
        }
        for role_name, codes in SEED_ROLES.items():
            role = existing_roles.get(role_name)
            if role is None:
                role = Role(
                    name=role_name,
                    description=f"Seeded role: {role_name}",
                    is_system=True,
                    permissions=[],
                )
                db.add(role)
                await db.flush()
                existing_roles[role_name] = role

            current_codes = {p.code for p in role.permissions}
            for code in codes:
                if code not in current_codes:
                    role.permissions.append(existing_permissions[code])

        await db.commit()
    print("Permissions and seed roles are up to date.")


async def seed_default_plans() -> None:
    async with AsyncSessionLocal() as db:
        existing_codes = {p.code for p in (await db.execute(select(Plan))).scalars().all()}
        for plan in DEFAULT_PLANS:
            if plan["code"] not in existing_codes:
                db.add(Plan(**plan))
        await db.commit()
    print("Default plans are up to date.")


async def bootstrap_superuser(email: str, password: str, full_name: str) -> None:
    async with AsyncSessionLocal() as db:
        existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if existing is not None:
            print(f"User {email} already exists; not modifying.")
            return
        user = User(
            email=email,
            full_name=full_name,
            hashed_password=hash_password(password),
            is_superuser=True,
        )
        db.add(user)
        await db.commit()
    print(f"Created platform superuser {email}.")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("permissions-roles")
    sub.add_parser("plans")

    su = sub.add_parser("superuser")
    su.add_argument("--email", required=True)
    su.add_argument("--password", required=True)
    su.add_argument("--full-name", required=True)

    args = parser.parse_args()

    if args.command == "permissions-roles":
        asyncio.run(seed_permissions_and_roles())
    elif args.command == "plans":
        asyncio.run(seed_default_plans())
    elif args.command == "superuser":
        if len(args.password) < 10:
            print("Password must be at least 10 characters.", file=sys.stderr)
            sys.exit(1)
        asyncio.run(bootstrap_superuser(args.email, args.password, args.full_name))


if __name__ == "__main__":
    main()
    