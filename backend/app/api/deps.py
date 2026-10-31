import uuid
from collections.abc import Callable

import jwt
from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import user_has_permission
from app.core.security import decode_access_token
from app.database import get_db
from app.exceptions import AuthenticationError, PermissionDeniedError, ValidationFailedError
from app.models.user import User

__all__ = ["get_db", "get_current_user", "require_permission", "require_superuser"]


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthenticationError("Missing or malformed Authorization header.")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        raise AuthenticationError("Invalid or expired access token.")

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        raise AuthenticationError("Invalid access token.")

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None or not user.is_active:
        raise AuthenticationError("Account is inactive or no longer exists.")
    return user


async def require_superuser(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_superuser:
        raise PermissionDeniedError("This action is restricted to platform administrators.")
    return current_user


def require_permission(permission_code: str) -> Callable:
    """
    Resolves organization_id / station_id from the request's own path parameters
    (never from a request body or query string a client could forge) and checks
    the caller's UserStationRole grants against them. Every mutating or
    organization/station-scoped endpoint must depend on this rather than
    re-implementing its own check.
    """

    async def dependency(
        request: Request,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        org_id_raw = request.path_params.get("organization_id")
        if org_id_raw is None:
            raise PermissionDeniedError("This action requires an organization context.")
        try:
            organization_id = uuid.UUID(org_id_raw)
        except ValueError:
            # Malformed input, not a permission decision - 422, not 403.
            raise ValidationFailedError("Invalid organization reference.")

        station_id: uuid.UUID | None = None
        station_id_raw = request.path_params.get("station_id")
        if station_id_raw is not None:
            try:
                station_id = uuid.UUID(station_id_raw)
            except ValueError:
                raise ValidationFailedError("Invalid station reference.")

        allowed = current_user.is_superuser or await user_has_permission(
            db,
            user_id=current_user.id,
            organization_id=organization_id,
            station_id=station_id,
            permission_code=permission_code,
        )
        if not allowed:
            raise PermissionDeniedError()
        return current_user

    return dependency
