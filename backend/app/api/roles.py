from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.core.cache import cache_get, cache_set
from app.models.role import Role
from app.models.user import User
from app.schemas.role import RoleRead

router = APIRouter(prefix="/roles", tags=["roles"])

# The role/permission catalog is seeded once (app.seed permissions-roles) and
# has no create/update/delete endpoint anywhere in this API - there is
# nothing for this cache to ever need to invalidate against, so a longer TTL
# than the per-organization config caches below is safe.
_ROLES_CACHE_KEY = "roles:catalog"
_ROLES_CACHE_TTL_SECONDS = 300


@router.get("", response_model=list[RoleRead])
async def list_roles(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[Role]:
    cached = await cache_get(_ROLES_CACHE_KEY)
    if cached is not None:
        return cached

    result = await db.execute(select(Role).options(selectinload(Role.permissions)))
    roles = list(result.scalars().all())

    payload = [RoleRead.model_validate(r).model_dump(mode="json") for r in roles]
    await cache_set(_ROLES_CACHE_KEY, payload, ttl_seconds=_ROLES_CACHE_TTL_SECONDS)
    return roles
