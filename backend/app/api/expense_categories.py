import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_organization_or_404
from app.api.deps import get_db, require_permission
from app.core.audit import write_audit_log
from app.core.cache import cache_delete, cache_get, cache_set
from app.core.permission_codes import EXPENSE_APPROVE
from app.exceptions import ConflictError, NotFoundError
from app.models.expense_category import ExpenseCategory
from app.models.user import User
from app.schemas.expense_category import ExpenseCategoryCreate, ExpenseCategoryRead, ExpenseCategoryUpdate

router = APIRouter(
    prefix="/organizations/{organization_id}/expense-categories",
    tags=["expense-categories"],
)

_LIST_CACHE_TTL_SECONDS = 30


def _list_cache_key(organization_id: uuid.UUID) -> str:
    return f"expense_categories:list:{organization_id}"


@router.post("", response_model=ExpenseCategoryRead, status_code=201)
async def create_expense_category(
    organization_id: uuid.UUID,
    payload: ExpenseCategoryCreate,
    request: Request,
    current_user: User = Depends(require_permission(EXPENSE_APPROVE)),
    db: AsyncSession = Depends(get_db),
) -> ExpenseCategory:
    await get_organization_or_404(db, organization_id)
    cat = ExpenseCategory(organization_id=organization_id, **payload.model_dump())
    db.add(cat)
    try:
        await db.flush()
    except Exception:
        await db.rollback()
        raise ConflictError(f"An expense category named '{payload.name}' already exists.")

    await write_audit_log(
        db,
        action="expense_category.create",
        entity_type="ExpenseCategory",
        entity_id=str(cat.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        after={"name": cat.name},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await cache_delete(_list_cache_key(organization_id))
    return cat


@router.get("", response_model=list[ExpenseCategoryRead])
async def list_expense_categories(
    organization_id: uuid.UUID,
    current_user: User = Depends(require_permission(EXPENSE_APPROVE)),
    db: AsyncSession = Depends(get_db),
) -> list[ExpenseCategory]:
    cache_key = _list_cache_key(organization_id)
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    result = await db.execute(
        select(ExpenseCategory)
        .where(ExpenseCategory.organization_id == organization_id)
        .order_by(ExpenseCategory.name)
    )
    cats = list(result.scalars().all())

    payload = [ExpenseCategoryRead.model_validate(c).model_dump(mode="json") for c in cats]
    await cache_set(cache_key, payload, ttl_seconds=_LIST_CACHE_TTL_SECONDS)
    return cats


@router.patch("/{category_id}", response_model=ExpenseCategoryRead)
async def update_expense_category(
    organization_id: uuid.UUID,
    category_id: uuid.UUID,
    payload: ExpenseCategoryUpdate,
    request: Request,
    current_user: User = Depends(require_permission(EXPENSE_APPROVE)),
    db: AsyncSession = Depends(get_db),
) -> ExpenseCategory:
    cat = (
        await db.execute(
            select(ExpenseCategory).where(
                ExpenseCategory.id == category_id,
                ExpenseCategory.organization_id == organization_id,
            )
        )
    ).scalar_one_or_none()
    if cat is None:
        raise NotFoundError("Expense category not found.")

    before = {"name": cat.name, "is_active": cat.is_active}
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(cat, field, value)
    await db.flush()

    await write_audit_log(
        db,
        action="expense_category.update",
        entity_type="ExpenseCategory",
        entity_id=str(cat.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        before=before,
        after=payload.model_dump(exclude_unset=True),
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await cache_delete(_list_cache_key(organization_id))
    return cat
