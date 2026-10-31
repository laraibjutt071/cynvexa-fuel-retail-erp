import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_organization_or_404
from app.api.deps import get_current_user, get_db, require_permission, require_superuser
from app.core.audit import write_audit_log
from app.core.permission_codes import ORGANIZATION_READ, ORGANIZATION_UPDATE
from app.models.organization import Organization
from app.models.user import User
from app.models.user_station_role import UserStationRole
from app.schemas.organization import OrganizationCreate, OrganizationRead, OrganizationUpdate

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.post("", response_model=OrganizationRead, status_code=201)
async def create_organization(
    payload: OrganizationCreate,
    request: Request,
    current_user: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    org = Organization(name=payload.name, legal_name=payload.legal_name)
    db.add(org)
    await db.flush()
    await write_audit_log(
        db,
        action="organization.create",
        entity_type="Organization",
        entity_id=str(org.id),
        actor_user_id=current_user.id,
        organization_id=org.id,
        after={"name": org.name, "legal_name": org.legal_name},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return org


@router.get("", response_model=list[OrganizationRead])
async def list_organizations(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[Organization]:
    if current_user.is_superuser:
        result = await db.execute(select(Organization))
        return list(result.scalars().all())

    stmt = (
        select(Organization)
        .join(UserStationRole, UserStationRole.organization_id == Organization.id)
        .where(UserStationRole.user_id == current_user.id, UserStationRole.is_active.is_(True))
        .distinct()
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{organization_id}", response_model=OrganizationRead)
async def get_organization(
    organization_id: uuid.UUID,
    current_user: User = Depends(require_permission(ORGANIZATION_READ)),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    return await get_organization_or_404(db, organization_id)


@router.patch("/{organization_id}", response_model=OrganizationRead)
async def update_organization(
    organization_id: uuid.UUID,
    payload: OrganizationUpdate,
    request: Request,
    current_user: User = Depends(require_permission(ORGANIZATION_UPDATE)),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    org = await get_organization_or_404(db, organization_id)
    update_data = payload.model_dump(exclude_unset=True)
    before = {field: getattr(org, field) for field in update_data}

    for field, value in update_data.items():
        setattr(org, field, value)
    await db.flush()

    after = {field: getattr(org, field) for field in update_data}
    await write_audit_log(
        db,
        action="organization.update",
        entity_type="Organization",
        entity_id=str(org.id),
        actor_user_id=current_user.id,
        organization_id=org.id,
        before=before,
        after=after,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return org
