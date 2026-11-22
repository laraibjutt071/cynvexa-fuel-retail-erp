import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_ev_charger_or_404, get_station_or_404
from app.api.deps import get_db, require_permission
from app.core.audit import write_audit_log
from app.core.permission_codes import EV_CHARGER_MANAGE, EV_CHARGER_READ
from app.exceptions import ConflictError, NotFoundError
from app.models.ev_tariff import EVTariff
from app.models.user import User
from app.schemas.ev_tariff import EVTariffCreate, EVTariffRead

router = APIRouter(
    prefix="/organizations/{organization_id}/stations/{station_id}/ev-tariffs", tags=["ev-tariffs"]
)


@router.post("", response_model=EVTariffRead, status_code=201)
async def create_ev_tariff(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    payload: EVTariffCreate,
    request: Request,
    current_user: User = Depends(require_permission(EV_CHARGER_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> EVTariff:
    """Append-only, same as fuel prices - no update/delete endpoint exists.
    A tariff change is always a new row; see EVTariff's own docstring."""
    await get_station_or_404(db, organization_id, station_id)
    if payload.charger_id is not None:
        await get_ev_charger_or_404(db, station_id, payload.charger_id)

    tariff = EVTariff(
        station_id=station_id,
        created_by_user_id=current_user.id,
        **payload.model_dump(exclude={"pricing_basis"}),
        pricing_basis=payload.pricing_basis.value,
    )
    db.add(tariff)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ConflictError(
            "A tariff for this charger (or station-wide default) is already effective from that exact timestamp."
        )

    await write_audit_log(
        db,
        action="ev_tariff.create",
        entity_type="EVTariff",
        entity_id=str(tariff.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={
            "charger_id": str(tariff.charger_id) if tariff.charger_id else None,
            "pricing_basis": tariff.pricing_basis,
            "rate": str(tariff.rate),
            "effective_from": tariff.effective_from.isoformat(),
        },
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return tariff


@router.get("", response_model=list[EVTariffRead])
async def list_ev_tariffs(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    charger_id: uuid.UUID | None = None,
    current_user: User = Depends(require_permission(EV_CHARGER_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[EVTariff]:
    stmt = select(EVTariff).where(EVTariff.station_id == station_id)
    if charger_id is not None:
        stmt = stmt.where(EVTariff.charger_id == charger_id)
    stmt = stmt.order_by(EVTariff.effective_from.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/current", response_model=EVTariffRead)
async def get_current_ev_tariff(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    charger_id: uuid.UUID | None = None,
    current_user: User = Depends(require_permission(EV_CHARGER_READ)),
    db: AsyncSession = Depends(get_db),
) -> EVTariff:
    """
    The tariff in effect now for `charger_id` is the row with the latest
    effective_from <= now scoped to that charger - falling back to the
    station-wide default (charger_id IS NULL) only if that specific
    charger has never had its own tariff set. Never silently assumes a
    rate if neither exists.
    """
    now = datetime.now(timezone.utc)
    if charger_id is not None:
        stmt = (
            select(EVTariff)
            .where(
                EVTariff.station_id == station_id,
                EVTariff.charger_id == charger_id,
                EVTariff.effective_from <= now,
            )
            .order_by(EVTariff.effective_from.desc())
            .limit(1)
        )
        tariff = (await db.execute(stmt)).scalar_one_or_none()
        if tariff is not None:
            return tariff

    stmt = (
        select(EVTariff)
        .where(EVTariff.station_id == station_id, EVTariff.charger_id.is_(None), EVTariff.effective_from <= now)
        .order_by(EVTariff.effective_from.desc())
        .limit(1)
    )
    tariff = (await db.execute(stmt)).scalar_one_or_none()
    if tariff is None:
        raise NotFoundError("No EV tariff has been set for this station/charger yet.")
    return tariff
