"""
Per-tank dip chart (calibration / strapping table): maps a physical
dip-stick reading (mm) to the litres it represents for that specific tank's
geometry. Purely a reference/lookup tool for the operator - never
consulted by shift readings, reconciliation, or the stock ledger, all of
which keep taking a reading as a direct litres value exactly as before
(see ShiftTankReading and app/core/stock.py). Nothing in the existing,
already-tested daily-entry flow changes.
"""

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_organization_or_404, get_station_or_404
from app.api.deps import get_db, require_permission
from app.core.audit import write_audit_log
from app.core.permission_codes import TANK_MANAGE, TANK_READ
from app.exceptions import ConflictError, NotFoundError, ValidationFailedError
from app.models.tank import Tank
from app.models.tank_dip_chart import TankDipChartEntry
from app.models.user import User
from app.schemas.tank_dip_chart import TankDipChartEntryCreate, TankDipChartEntryRead, TankDipChartLookupResult

router = APIRouter(
    prefix="/organizations/{organization_id}/stations/{station_id}/tanks/{tank_id}/dip-chart",
    tags=["tank-dip-charts"],
)


async def _get_tank_or_404(db: AsyncSession, station_id: uuid.UUID, tank_id: uuid.UUID) -> Tank:
    tank = (await db.execute(select(Tank).where(Tank.id == tank_id, Tank.station_id == station_id))).scalar_one_or_none()
    if tank is None:
        raise NotFoundError("Tank not found.")
    return tank


@router.post("", response_model=TankDipChartEntryRead, status_code=201)
async def add_dip_chart_entry(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    tank_id: uuid.UUID,
    payload: TankDipChartEntryCreate,
    request: Request,
    current_user: User = Depends(require_permission(TANK_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> TankDipChartEntry:
    await get_station_or_404(db, organization_id, station_id)
    await _get_tank_or_404(db, station_id, tank_id)

    entry = TankDipChartEntry(
        tank_id=tank_id, created_by_user_id=current_user.id, **payload.model_dump()
    )
    db.add(entry)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ConflictError(f"A calibration point already exists at {payload.dip_mm}mm for this tank.")

    await write_audit_log(
        db,
        action="tank_dip_chart.create",
        entity_type="TankDipChartEntry",
        entity_id=str(entry.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={"tank_id": str(tank_id), "dip_mm": str(entry.dip_mm), "volume_litres": str(entry.volume_litres)},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return entry


@router.get("", response_model=list[TankDipChartEntryRead])
async def list_dip_chart_entries(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    tank_id: uuid.UUID,
    current_user: User = Depends(require_permission(TANK_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[TankDipChartEntry]:
    await get_station_or_404(db, organization_id, station_id)
    await _get_tank_or_404(db, station_id, tank_id)
    result = await db.execute(
        select(TankDipChartEntry).where(TankDipChartEntry.tank_id == tank_id).order_by(TankDipChartEntry.dip_mm)
    )
    return list(result.scalars().all())


@router.delete("/{entry_id}", status_code=204)
async def delete_dip_chart_entry(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    tank_id: uuid.UUID,
    entry_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_permission(TANK_MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> None:
    await get_station_or_404(db, organization_id, station_id)
    await _get_tank_or_404(db, station_id, tank_id)
    entry = (
        await db.execute(
            select(TankDipChartEntry).where(TankDipChartEntry.id == entry_id, TankDipChartEntry.tank_id == tank_id)
        )
    ).scalar_one_or_none()
    if entry is None:
        raise NotFoundError("Calibration point not found.")

    await write_audit_log(
        db,
        action="tank_dip_chart.delete",
        entity_type="TankDipChartEntry",
        entity_id=str(entry.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        before={"dip_mm": str(entry.dip_mm), "volume_litres": str(entry.volume_litres)},
        ip_address=request.client.host if request.client else None,
    )
    await db.delete(entry)
    await db.commit()


@router.get("/lookup", response_model=TankDipChartLookupResult)
async def lookup_dip_chart_volume(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    tank_id: uuid.UUID,
    dip_mm: Decimal = Query(..., ge=0),
    current_user: User = Depends(require_permission(TANK_READ)),
    db: AsyncSession = Depends(get_db),
) -> TankDipChartLookupResult:
    await get_station_or_404(db, organization_id, station_id)
    await _get_tank_or_404(db, station_id, tank_id)

    entries = list(
        (
            await db.execute(
                select(TankDipChartEntry).where(TankDipChartEntry.tank_id == tank_id).order_by(TankDipChartEntry.dip_mm)
            )
        ).scalars().all()
    )
    if len(entries) < 2:
        raise ValidationFailedError(
            "This tank needs at least 2 calibration points before a dip reading can be converted to litres."
        )

    for e in entries:
        if e.dip_mm == dip_mm:
            return TankDipChartLookupResult(dip_mm=dip_mm, volume_litres=e.volume_litres, exact_match=True)

    if dip_mm < entries[0].dip_mm or dip_mm > entries[-1].dip_mm:
        raise ValidationFailedError(
            f"{dip_mm}mm is outside this tank's calibrated range "
            f"({entries[0].dip_mm}mm-{entries[-1].dip_mm}mm) - add a calibration point covering it first."
        )

    # Linear interpolation between the two bracketing calibration points -
    # the same thing a human does reading between two rows of a paper
    # strapping table.
    lower = max((e for e in entries if e.dip_mm < dip_mm), key=lambda e: e.dip_mm)
    upper = min((e for e in entries if e.dip_mm > dip_mm), key=lambda e: e.dip_mm)
    span = upper.dip_mm - lower.dip_mm
    fraction = (dip_mm - lower.dip_mm) / span
    volume = lower.volume_litres + fraction * (upper.volume_litres - lower.volume_litres)
    return TankDipChartLookupResult(dip_mm=dip_mm, volume_litres=volume.quantize(Decimal("0.001")), exact_match=False)
