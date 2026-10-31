import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_organization_or_404
from app.api.deps import get_db, require_permission
from app.core.audit import write_audit_log
from app.core.permission_codes import SUPPLIER_MANAGE, SUPPLIER_READ
from app.exceptions import NotFoundError
from app.models.supplier import Supplier
from app.models.user import User
from app.schemas.supplier import SupplierCreate, SupplierRead, SupplierUpdate

router = APIRouter(prefix="/organizations/{organization_id}/suppliers", tags=["suppliers"])


@router.post("", response_model=SupplierRead, status_code=201)
async def create_supplier(
    organization_id: uuid.UUID,
    payload: SupplierCreate,
    request: Request,
    current_user: User = Depends(require_permission(SUPPLIER_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> Supplier:
    await get_organization_or_404(db, organization_id)

    supplier = Supplier(organization_id=organization_id, **payload.model_dump())
    db.add(supplier)
    await db.flush()

    await write_audit_log(
        db,
        action="supplier.create",
        entity_type="Supplier",
        entity_id=str(supplier.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        after={"name": supplier.name},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return supplier


@router.get("", response_model=list[SupplierRead])
async def list_suppliers(
    organization_id: uuid.UUID,
    current_user: User = Depends(require_permission(SUPPLIER_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[Supplier]:
    result = await db.execute(select(Supplier).where(Supplier.organization_id == organization_id))
    return list(result.scalars().all())


@router.get("/{supplier_id}", response_model=SupplierRead)
async def get_supplier(
    organization_id: uuid.UUID,
    supplier_id: uuid.UUID,
    current_user: User = Depends(require_permission(SUPPLIER_READ)),
    db: AsyncSession = Depends(get_db),
) -> Supplier:
    supplier = (
        await db.execute(
            select(Supplier).where(Supplier.id == supplier_id, Supplier.organization_id == organization_id)
        )
    ).scalar_one_or_none()
    if supplier is None:
        raise NotFoundError("Supplier not found.")
    return supplier


@router.patch("/{supplier_id}", response_model=SupplierRead)
async def update_supplier(
    organization_id: uuid.UUID,
    supplier_id: uuid.UUID,
    payload: SupplierUpdate,
    request: Request,
    current_user: User = Depends(require_permission(SUPPLIER_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> Supplier:
    supplier = (
        await db.execute(
            select(Supplier).where(Supplier.id == supplier_id, Supplier.organization_id == organization_id)
        )
    ).scalar_one_or_none()
    if supplier is None:
        raise NotFoundError("Supplier not found.")

    before = {
        "name": supplier.name,
        "contact_phone": supplier.contact_phone,
        "contact_email": supplier.contact_email,
        "is_active": supplier.is_active,
    }
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(supplier, field, value)
    await db.flush()
    after = {
        "name": supplier.name,
        "contact_phone": supplier.contact_phone,
        "contact_email": supplier.contact_email,
        "is_active": supplier.is_active,
    }

    await write_audit_log(
        db,
        action="supplier.update",
        entity_type="Supplier",
        entity_id=str(supplier.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        before=before,
        after=after,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return supplier
