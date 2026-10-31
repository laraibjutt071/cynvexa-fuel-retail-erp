from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.exceptions import ServiceUnavailableError

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Liveness: process is up. Intentionally does not touch the database."""
    return {"status": "ok"}


@router.get("/ready")
async def ready(db: AsyncSession = Depends(get_db)) -> dict:
    """Readiness: the database is actually reachable."""
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - deliberately broad: any DB failure means not-ready
        raise ServiceUnavailableError("Database is not reachable.") from exc
    return {"status": "ready"}
