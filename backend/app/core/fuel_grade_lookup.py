import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fuel_grade import FuelGrade


async def get_fuel_grades_by_id(
    db: AsyncSession, grade_ids: set[uuid.UUID]
) -> dict[uuid.UUID, FuelGrade]:
    """Small shared lookup for report endpoints that need a fuel grade's
    code/name after aggregating by fuel_grade_id."""
    if not grade_ids:
        return {}
    grades = (
        await db.execute(select(FuelGrade).where(FuelGrade.id.in_(grade_ids)))
    ).scalars().all()
    return {g.id: g for g in grades}
