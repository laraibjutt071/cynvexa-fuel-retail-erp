import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_organization_or_404
from app.api.deps import get_db, require_permission
from app.core.audit import write_audit_log
from app.core.permission_codes import USER_ASSIGN_ROLE, USER_CREATE, USER_READ, USER_UPDATE
from app.core.permissions import actor_can_grant_scope
from app.core.security import hash_password
from app.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationFailedError
from app.models.role import Role
from app.models.station import Station
from app.models.user import User
from app.models.user_station_role import UserStationRole
from app.schemas.user import RoleAssignmentCreate, RoleAssignmentRead, UserCreate, UserRead, UserUpdate

router = APIRouter(prefix="/organizations/{organization_id}/users", tags=["users"])


async def _get_org_user_or_404(db: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID) -> User:
    """A user is only visible through an organization's endpoint if they hold at
    least one role (active or not) within that organization — otherwise this
    organization has no business knowing the account exists."""
    stmt = (
        select(User)
        .join(UserStationRole, UserStationRole.user_id == User.id)
        .where(User.id == user_id, UserStationRole.organization_id == organization_id)
        .distinct()
    )
    user = (await db.execute(stmt)).scalar_one_or_none()
    if user is None:
        raise NotFoundError("User not found in this organization.")
    return user


@router.post("", response_model=UserRead, status_code=201)
async def create_user(
    organization_id: uuid.UUID,
    payload: UserCreate,
    request: Request,
    current_user: User = Depends(require_permission(USER_CREATE)),
    db: AsyncSession = Depends(get_db),
) -> User:
    await get_organization_or_404(db, organization_id)

    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        employee_code=payload.employee_code,
        job_title=payload.job_title,
        phone=payload.phone,
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ConflictError("A user with this email already exists.")

    await write_audit_log(
        db,
        action="user.create",
        entity_type="User",
        entity_id=str(user.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        after={"email": user.email, "full_name": user.full_name},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return user


@router.get("", response_model=list[UserRead])
async def list_users(
    organization_id: uuid.UUID,
    q: str | None = Query(default=None, max_length=200, description="Search by name, email, or employee code"),
    status: str | None = Query(default=None, pattern="^(active|inactive)$"),
    station_id: uuid.UUID | None = Query(default=None, description="Only users with a role assignment at this station"),
    current_user: User = Depends(require_permission(USER_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[User]:
    stmt = (
        select(User)
        .join(UserStationRole, UserStationRole.user_id == User.id)
        .where(UserStationRole.organization_id == organization_id)
        .distinct()
    )
    if q:
        stmt = stmt.where(
            or_(User.full_name.ilike(f"%{q}%"), User.email.ilike(f"%{q}%"), User.employee_code.ilike(f"%{q}%"))
        )
    if status == "active":
        stmt = stmt.where(User.is_active.is_(True))
    elif status == "inactive":
        stmt = stmt.where(User.is_active.is_(False))
    if station_id is not None:
        stmt = stmt.where(UserStationRole.station_id == station_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: User = Depends(require_permission(USER_READ)),
    db: AsyncSession = Depends(get_db),
) -> User:
    return await _get_org_user_or_404(db, organization_id, user_id)


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: UserUpdate,
    request: Request,
    current_user: User = Depends(require_permission(USER_UPDATE)),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await _get_org_user_or_404(db, organization_id, user_id)
    update_data = payload.model_dump(exclude_unset=True)
    before = {field: getattr(user, field) for field in update_data}

    for field, value in update_data.items():
        setattr(user, field, value)
    await db.flush()

    after = {field: getattr(user, field) for field in update_data}
    await write_audit_log(
        db,
        action="user.update",
        entity_type="User",
        entity_id=str(user.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        before=before,
        after=after,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return user


@router.get("/{user_id}/roles", response_model=list[RoleAssignmentRead])
async def list_user_roles(
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: User = Depends(require_permission(USER_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[UserStationRole]:
    """Active role assignments for one user in this organization. There was no
    read endpoint for this before - only the POST/DELETE below existed - which
    meant a Users & Settings screen had no way to show who already holds what
    role. This is purely additive and read-only."""
    await _get_org_user_or_404(db, organization_id, user_id)
    stmt = select(UserStationRole).where(
        UserStationRole.user_id == user_id,
        UserStationRole.organization_id == organization_id,
        UserStationRole.is_active.is_(True),
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("/{user_id}/roles", response_model=RoleAssignmentRead, status_code=201)
async def assign_role(
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: RoleAssignmentCreate,
    request: Request,
    current_user: User = Depends(require_permission(USER_ASSIGN_ROLE)),
    db: AsyncSession = Depends(get_db),
) -> UserStationRole:
    await get_organization_or_404(db, organization_id)

    # require_permission already confirmed current_user holds USER_ASSIGN_ROLE
    # SOMEWHERE in this org, which is necessary but not sufficient: a role
    # scoped to one station must not be able to grant an org-wide (or a
    # different station's) role to someone else. See actor_can_grant_scope's
    # docstring for why this can't just reuse require_permission's check.
    # No support-session path here (Phase 5b): a superuser with no real
    # tenant role in this org cannot grant/revoke roles at all - role
    # assignment is one of the actions deliberately excluded from support
    # sessions, which are read-only.
    if not await actor_can_grant_scope(
        db,
        user_id=current_user.id,
        organization_id=organization_id,
        target_station_id=payload.station_id,
        permission_code=USER_ASSIGN_ROLE,
    ):
        raise PermissionDeniedError(
            "You cannot grant a role at a wider scope than your own."
        )

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise NotFoundError("User not found.")

    role = (await db.execute(select(Role).where(Role.id == payload.role_id))).scalar_one_or_none()
    if role is None:
        raise NotFoundError("Role not found.")

    if payload.station_id is not None:
        station = (
            await db.execute(
                select(Station).where(
                    Station.id == payload.station_id, Station.organization_id == organization_id
                )
            )
        ).scalar_one_or_none()
        if station is None:
            raise ValidationFailedError("Station does not belong to this organization.")

    assignment = UserStationRole(
        user_id=user_id,
        organization_id=organization_id,
        station_id=payload.station_id,
        role_id=payload.role_id,
    )
    db.add(assignment)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ConflictError("This role is already assigned to the user at this scope.")

    await write_audit_log(
        db,
        action="user.assign_role",
        entity_type="UserStationRole",
        entity_id=str(assignment.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=payload.station_id,
        after={
            "user_id": str(user_id),
            "role_id": str(payload.role_id),
            "station_id": str(payload.station_id) if payload.station_id else None,
        },
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return assignment


@router.delete("/{user_id}/roles/{assignment_id}", status_code=204)
async def revoke_role(
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    assignment_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_permission(USER_ASSIGN_ROLE)),
    db: AsyncSession = Depends(get_db),
) -> None:
    assignment = (
        await db.execute(
            select(UserStationRole).where(
                UserStationRole.id == assignment_id,
                UserStationRole.user_id == user_id,
                UserStationRole.organization_id == organization_id,
            )
        )
    ).scalar_one_or_none()
    if assignment is None:
        raise NotFoundError("Role assignment not found.")

    # No support-session path here either, same reasoning as assign_role above.
    if not await actor_can_grant_scope(
        db,
        user_id=current_user.id,
        organization_id=organization_id,
        target_station_id=assignment.station_id,
        permission_code=USER_ASSIGN_ROLE,
    ):
        raise PermissionDeniedError(
            "You cannot revoke a role assignment at a wider scope than your own."
        )

    assignment.is_active = False
    await db.flush()
    await write_audit_log(
        db,
        action="user.revoke_role",
        entity_type="UserStationRole",
        entity_id=str(assignment.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=assignment.station_id,
        before={"is_active": True},
        after={"is_active": False},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
