import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import get_station_or_404
from app.api.deps import get_db, require_permission
from app.core.audit import write_audit_log
from app.core.cache import cache_delete, cache_get, cache_set
from app.core.permission_codes import STATION_UPDATE
from app.exceptions import ConflictError, NotFoundError
from app.models.shift_template import ShiftTemplate
from app.models.user import User
from app.schemas.shift_template import ShiftTemplateCreate, ShiftTemplateRead, ShiftTemplateUpdate

router = APIRouter(
    prefix="/organizations/{organization_id}/stations/{station_id}/shift-templates",
    tags=["shift-templates"],
)

_LIST_CACHE_TTL_SECONDS = 30


def _list_cache_key(station_id: uuid.UUID) -> str:
    return f"shift_templates:list:{station_id}"


@router.post("", response_model=ShiftTemplateRead, status_code=201)
async def create_shift_template(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    payload: ShiftTemplateCreate,
    request: Request,
    current_user: User = Depends(require_permission(STATION_UPDATE)),
    db: AsyncSession = Depends(get_db),
) -> ShiftTemplate:
    await get_station_or_404(db, organization_id, station_id)
    tmpl = ShiftTemplate(
        organization_id=organization_id,
        station_id=station_id,
        **payload.model_dump(),
    )
    db.add(tmpl)
    try:
        await db.flush()
    except Exception:
        await db.rollback()
        raise ConflictError(f"A shift template named '{payload.name}' already exists at this station.")

    await write_audit_log(
        db,
        action="shift_template.create",
        entity_type="ShiftTemplate",
        entity_id=str(tmpl.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        after={"name": tmpl.name, "start_time": str(tmpl.start_time), "end_time": str(tmpl.end_time)},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await cache_delete(_list_cache_key(station_id))
    return tmpl


@router.get("", response_model=list[ShiftTemplateRead])
async def list_shift_templates(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    current_user: User = Depends(require_permission(STATION_UPDATE)),
    db: AsyncSession = Depends(get_db),
) -> list[ShiftTemplate]:
    await get_station_or_404(db, organization_id, station_id)

    cache_key = _list_cache_key(station_id)
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    result = await db.execute(
        select(ShiftTemplate)
        .where(ShiftTemplate.station_id == station_id)
        .order_by(ShiftTemplate.start_time)
    )
    templates = list(result.scalars().all())

    payload = [ShiftTemplateRead.model_validate(t).model_dump(mode="json") for t in templates]
    await cache_set(cache_key, payload, ttl_seconds=_LIST_CACHE_TTL_SECONDS)
    return templates


@router.patch("/{template_id}", response_model=ShiftTemplateRead)
async def update_shift_template(
    organization_id: uuid.UUID,
    station_id: uuid.UUID,
    template_id: uuid.UUID,
    payload: ShiftTemplateUpdate,
    request: Request,
    current_user: User = Depends(require_permission(STATION_UPDATE)),
    db: AsyncSession = Depends(get_db),
) -> ShiftTemplate:
    tmpl = (
        await db.execute(
            select(ShiftTemplate).where(
                ShiftTemplate.id == template_id,
                ShiftTemplate.station_id == station_id,
            )
        )
    ).scalar_one_or_none()
    if tmpl is None:
        raise NotFoundError("Shift template not found.")

    before = {"name": tmpl.name, "is_active": tmpl.is_active}
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(tmpl, field, value)
    await db.flush()

    await write_audit_log(
        db,
        action="shift_template.update",
        entity_type="ShiftTemplate",
        entity_id=str(tmpl.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        station_id=station_id,
        before=before,
        after=payload.model_dump(exclude_unset=True, mode="json"),
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await cache_delete(_list_cache_key(station_id))
    return tmpl
