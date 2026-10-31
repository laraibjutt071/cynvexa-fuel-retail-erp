import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_station_or_404, get_tank_or_404
from app.api.deps import get_db, require_permission
from app.core.audit import write_audit_log
from app.core.permission_codes import NOZZLE_MANAGE, NOZZLE_READ
from app.exceptions import ConflictError, NotFoundError
from app.models.dispenser import Dispenser
from app.models.nozzle import Nozzle
from app.models.user import User
from app.schemas.nozzle import NozzleCreate, NozzleRead, NozzleUpdate

router = APIRouter(
    prefix="/organizations/{organization_id}/stations/{station_id}/dispensers/{dispenser_id}/nozzles",
    tags=["nozzles"],
)


async def _get_dispenser_in_station_or_404(
    db: AsyncSession, station_id: uuid.UUID, dispenser_id: uuid.UUID
) -> Dispenser:
    dispenser = (
        await db.execute(
            select(Dispenser).where(Dispenser.id == dispenser_id, Dispenser.station_id == station_id)
        )
    ).scalar_one_or_none()
    if dispenser is None:
        raise NotFoundError("Dispenser not found.")
    return dispenser


async def _get_nozzle_or_404(db: AsyncSession, dispenser_id: uuid.UUID, nozzle_id: uuid.UUID) -> Nozzle:
    nozzle = (
        await db.execute(
            select(Nozzle).where(Nozzle.id == nozzle_id, Nozzle.dispenser_id == dispenser_id)
        )
    ).scalar_one_or_none()
    if nozzle is None:
        raise NotFoundError("Nozzle not found.")
    return nozzle


@router.post("", response_model=NozzleRead, status_code=201)
async def create_nozzle(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    dispenser_id: uuid.UUID,
    payload: NozzleCreate,
    request: Request,
    current_user: User = Depends(require_permission(NOZZLE_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> Nozzle:
    await get_station_or_404(db, organization_id, station_id)
    await _get_dispenser_in_station_or_404(db, station_id, dispenser_id)
    # A nozzle's tank must be at the SAME station as its dispenser - a nozzle
    # drawing from another station's tank would make book-stock and future
    # shift readings meaningless.
    await get_tank_or_404(db, station_id, payload.tank_id)

    nozzle = Nozzle(dispenser_id=dispenser_id, **payload.model_dump())
    db.add(nozzle)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ConflictError(f"A nozzle with code '{payload.code}' already exists on this dispenser.")

    await write_audit_log(
        db,
        action="nozzle.create",
        entity_type="Nozzle",
        entity_id=str(nozzle.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={"code": nozzle.code, "tank_id": str(nozzle.tank_id)},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return nozzle


@router.get("", response_model=list[NozzleRead])
async def list_nozzles(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    dispenser_id: uuid.UUID,
    current_user: User = Depends(require_permission(NOZZLE_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[Nozzle]:
    result = await db.execute(select(Nozzle).where(Nozzle.dispenser_id == dispenser_id))
    return list(result.scalars().all())


@router.get("/{nozzle_id}", response_model=NozzleRead)
async def get_nozzle(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    dispenser_id: uuid.UUID,
    nozzle_id: uuid.UUID,
    current_user: User = Depends(require_permission(NOZZLE_READ)),
    db: AsyncSession = Depends(get_db),
) -> Nozzle:
    return await _get_nozzle_or_404(db, dispenser_id, nozzle_id)


@router.patch("/{nozzle_id}", response_model=NozzleRead)
async def update_nozzle(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    dispenser_id: uuid.UUID,
    nozzle_id: uuid.UUID,
    payload: NozzleUpdate,
    request: Request,
    current_user: User = Depends(require_permission(NOZZLE_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> Nozzle:
    nozzle = await _get_nozzle_or_404(db, dispenser_id, nozzle_id)

    before = {"is_active": nozzle.is_active}
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(nozzle, field, value)
    await db.flush()
    after = {"is_active": nozzle.is_active}

    await write_audit_log(
        db,
        action="nozzle.update",
        entity_type="Nozzle",
        entity_id=str(nozzle.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        before=before,
        after=after,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return nozzle
