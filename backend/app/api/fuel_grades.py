import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_organization_or_404
from app.api.deps import get_db, require_permission
from app.core.audit import write_audit_log
from app.core.cache import cache_delete, cache_get, cache_set
from app.core.permission_codes import FUEL_GRADE_MANAGE, FUEL_GRADE_READ
from app.exceptions import ConflictError, NotFoundError
from app.models.fuel_grade import FuelGrade
from app.models.user import User
from app.schemas.fuel_grade import FuelGradeCreate, FuelGradeRead, FuelGradeUpdate

router = APIRouter(prefix="/organizations/{organization_id}/fuel-grades", tags=["fuel-grades"])

# Config data, not stock or money - a few seconds of staleness on "did this
# org's fuel-grade list just change" is harmless, unlike caching a price or a
# balance would be. Short TTL is a second line of defense behind the
# explicit invalidation below, not a substitute for it.
_LIST_CACHE_TTL_SECONDS = 30


def _list_cache_key(organization_id: uuid.UUID) -> str:
    return f"fuel_grades:list:{organization_id}"


@router.post("", response_model=FuelGradeRead, status_code=201)
async def create_fuel_grade(
    organization_id: uuid.UUID,
    payload: FuelGradeCreate,
    request: Request,
    current_user: User = Depends(require_permission(FUEL_GRADE_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> FuelGrade:
    await get_organization_or_404(db, organization_id)

    grade = FuelGrade(organization_id=organization_id, **payload.model_dump())
    db.add(grade)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ConflictError(f"A fuel grade with code '{payload.code}' already exists in this organization.")

    await write_audit_log(
        db,
        action="fuel_grade.create",
        entity_type="FuelGrade",
        entity_id=str(grade.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        after={"name": grade.name, "code": grade.code},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await cache_delete(_list_cache_key(organization_id))
    return grade


@router.get("", response_model=list[FuelGradeRead])
async def list_fuel_grades(
    organization_id: uuid.UUID,
    current_user: User = Depends(require_permission(FUEL_GRADE_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[FuelGrade]:
    cache_key = _list_cache_key(organization_id)
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    result = await db.execute(select(FuelGrade).where(FuelGrade.organization_id == organization_id))
    grades = list(result.scalars().all())

    payload = [FuelGradeRead.model_validate(g).model_dump(mode="json") for g in grades]
    await cache_set(cache_key, payload, ttl_seconds=_LIST_CACHE_TTL_SECONDS)
    return grades


@router.get("/{fuel_grade_id}", response_model=FuelGradeRead)
async def get_fuel_grade(
    organization_id: uuid.UUID,
    fuel_grade_id: uuid.UUID,
    current_user: User = Depends(require_permission(FUEL_GRADE_READ)),
    db: AsyncSession = Depends(get_db),
) -> FuelGrade:
    grade = (
        await db.execute(
            select(FuelGrade).where(
                FuelGrade.id == fuel_grade_id, FuelGrade.organization_id == organization_id
            )
        )
    ).scalar_one_or_none()
    if grade is None:
        raise NotFoundError("Fuel grade not found.")
    return grade


@router.patch("/{fuel_grade_id}", response_model=FuelGradeRead)
async def update_fuel_grade(
    organization_id: uuid.UUID,
    fuel_grade_id: uuid.UUID,
    payload: FuelGradeUpdate,
    request: Request,
    current_user: User = Depends(require_permission(FUEL_GRADE_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> FuelGrade:
    grade = (
        await db.execute(
            select(FuelGrade).where(
                FuelGrade.id == fuel_grade_id, FuelGrade.organization_id == organization_id
            )
        )
    ).scalar_one_or_none()
    if grade is None:
        raise NotFoundError("Fuel grade not found.")

    before = {"name": grade.name, "is_active": grade.is_active}
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(grade, field, value)
    await db.flush()
    after = {"name": grade.name, "is_active": grade.is_active}

    await write_audit_log(
        db,
        action="fuel_grade.update",
        entity_type="FuelGrade",
        entity_id=str(grade.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        before=before,
        after=after,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await cache_delete(_list_cache_key(organization_id))
    return grade
