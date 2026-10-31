import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_organization_or_404
from app.api.deps import get_db, require_permission
from app.core.audit import write_audit_log
from app.core.permission_codes import PAYMENT_METHOD_MANAGE, PAYMENT_METHOD_READ
from app.exceptions import ConflictError, NotFoundError
from app.models.payment_method import PaymentMethod
from app.models.user import User
from app.schemas.payment_method import PaymentMethodCreate, PaymentMethodRead, PaymentMethodUpdate

router = APIRouter(prefix="/organizations/{organization_id}/payment-methods", tags=["payment-methods"])


@router.post("", response_model=PaymentMethodRead, status_code=201)
async def create_payment_method(
    organization_id: uuid.UUID,
    payload: PaymentMethodCreate,
    request: Request,
    current_user: User = Depends(require_permission(PAYMENT_METHOD_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> PaymentMethod:
    await get_organization_or_404(db, organization_id)

    method = PaymentMethod(
        organization_id=organization_id,
        code=payload.code,
        name=payload.name,
        category=payload.category.value,
    )
    db.add(method)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ConflictError(f"A payment method with code '{payload.code}' already exists in this organization.")

    await write_audit_log(
        db,
        action="payment_method.create",
        entity_type="PaymentMethod",
        entity_id=str(method.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        after={"code": method.code, "name": method.name, "category": method.category},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return method


@router.get("", response_model=list[PaymentMethodRead])
async def list_payment_methods(
    organization_id: uuid.UUID,
    current_user: User = Depends(require_permission(PAYMENT_METHOD_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[PaymentMethod]:
    result = await db.execute(select(PaymentMethod).where(PaymentMethod.organization_id == organization_id))
    return list(result.scalars().all())


@router.patch("/{payment_method_id}", response_model=PaymentMethodRead)
async def update_payment_method(
    organization_id: uuid.UUID,
    payment_method_id: uuid.UUID,
    payload: PaymentMethodUpdate,
    request: Request,
    current_user: User = Depends(require_permission(PAYMENT_METHOD_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> PaymentMethod:
    method = (
        await db.execute(
            select(PaymentMethod).where(
                PaymentMethod.id == payment_method_id, PaymentMethod.organization_id == organization_id
            )
        )
    ).scalar_one_or_none()
    if method is None:
        raise NotFoundError("Payment method not found.")

    update_data = payload.model_dump(exclude_unset=True)
    before = {field: getattr(method, field) for field in update_data}
    for field, value in update_data.items():
        setattr(method, field, value)
    await db.flush()
    after = {field: getattr(method, field) for field in update_data}

    await write_audit_log(
        db,
        action="payment_method.update",
        entity_type="PaymentMethod",
        entity_id=str(method.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        before=before,
        after=after,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return method
