import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_organization_or_404
from app.api.deps import get_db, require_permission
from app.core.audit import write_audit_log
from app.core.permission_codes import CREDIT_CUSTOMER_MANAGE, CREDIT_CUSTOMER_READ
from app.exceptions import NotFoundError
from app.models.credit_customer import CreditCustomer
from app.models.user import User
from app.schemas.credit_customer import CreditCustomerCreate, CreditCustomerRead, CreditCustomerUpdate

router = APIRouter(prefix="/organizations/{organization_id}/credit-customers", tags=["credit-customers"])


@router.post("", response_model=CreditCustomerRead, status_code=201)
async def create_credit_customer(
    organization_id: uuid.UUID,
    payload: CreditCustomerCreate,
    request: Request,
    current_user: User = Depends(require_permission(CREDIT_CUSTOMER_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> CreditCustomer:
    await get_organization_or_404(db, organization_id)

    customer = CreditCustomer(organization_id=organization_id, name=payload.name)
    db.add(customer)
    await db.flush()

    await write_audit_log(
        db,
        action="credit_customer.create",
        entity_type="CreditCustomer",
        entity_id=str(customer.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        after={"name": customer.name},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return customer


@router.get("", response_model=list[CreditCustomerRead])
async def list_credit_customers(
    organization_id: uuid.UUID,
    current_user: User = Depends(require_permission(CREDIT_CUSTOMER_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[CreditCustomer]:
    result = await db.execute(
        select(CreditCustomer).where(CreditCustomer.organization_id == organization_id)
    )
    return list(result.scalars().all())


@router.patch("/{credit_customer_id}", response_model=CreditCustomerRead)
async def update_credit_customer(
    organization_id: uuid.UUID,
    credit_customer_id: uuid.UUID,
    payload: CreditCustomerUpdate,
    request: Request,
    current_user: User = Depends(require_permission(CREDIT_CUSTOMER_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> CreditCustomer:
    customer = (
        await db.execute(
            select(CreditCustomer).where(
                CreditCustomer.id == credit_customer_id, CreditCustomer.organization_id == organization_id
            )
        )
    ).scalar_one_or_none()
    if customer is None:
        raise NotFoundError("Credit customer not found.")

    update_data = payload.model_dump(exclude_unset=True)
    before = {field: getattr(customer, field) for field in update_data}
    for field, value in update_data.items():
        setattr(customer, field, value)
    await db.flush()
    after = {field: getattr(customer, field) for field in update_data}

    await write_audit_log(
        db,
        action="credit_customer.update",
        entity_type="CreditCustomer",
        entity_id=str(customer.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        before=before,
        after=after,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return customer
