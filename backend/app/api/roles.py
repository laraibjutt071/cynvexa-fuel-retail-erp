from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.models.role import Role
from app.models.user import User
from app.schemas.role import RoleRead

router = APIRouter(prefix="/roles", tags=["roles"])


@router.get("", response_model=list[RoleRead])
async def list_roles(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[Role]:
    result = await db.execute(select(Role).options(selectinload(Role.permissions)))
    return list(result.scalars().all())
