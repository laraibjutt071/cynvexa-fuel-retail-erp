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
from app.models.role import Permission, Role
from app.models.user import User


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

    su = sub.add_parser("superuser")
    su.add_argument("--email", required=True)
    su.add_argument("--password", required=True)
    su.add_argument("--full-name", required=True)

    args = parser.parse_args()

    if args.command == "permissions-roles":
        asyncio.run(seed_permissions_and_roles())
    elif args.command == "superuser":
        if len(args.password) < 10:
            print("Password must be at least 10 characters.", file=sys.stderr)
            sys.exit(1)
        asyncio.run(bootstrap_superuser(args.email, args.password, args.full_name))


if __name__ == "__main__":
    main()
    