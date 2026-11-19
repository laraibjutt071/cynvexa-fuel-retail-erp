import uuid
from collections.abc import Callable

import jwt
from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit_log
from app.core.permission_codes import ORGANIZATION_READ, ORGANIZATION_UPDATE
from app.core.permissions import user_has_permission
from app.core.security import decode_access_token
from app.core.support_sessions import support_session_grants
from app.database import get_db
from app.exceptions import AuthenticationError, PermissionDeniedError, ValidationFailedError
from app.models.organization import Organization
from app.models.user import User

# Organization profile read/update is the Super Admin's own directory data
# (city, legal name, is_active, ...) - the same information
# /platform/organizations already exposes freely - not a tenant's business
# records. It keeps today's unconditional superuser access; every other
# permission code requires either a real role or an active support
# session. See docs/PHASE_5B_SUPER_ADMIN_SUPPORT_SESSIONS_AUDIT.md §3.
_PLATFORM_DIRECT_PERMISSIONS = {ORGANIZATION_READ, ORGANIZATION_UPDATE}

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

        # A suspended tenant cannot transact at all, regardless of what
        # permission the caller otherwise holds - the platform admin's
        # suspend action (Organization.is_active = False) must actually
        # block access, not just sit unread in the database. A superuser
        # is exempt so a platform admin can still inspect/reactivate a
        # suspended organization. A nonexistent organization_id is left to
        # whatever 404 the endpoint itself would raise - this check only
        # ever turns an otherwise-allowed request into a 403, never
        # changes 404 behavior.
        if not current_user.is_superuser:
            org = (
                await db.execute(select(Organization.is_active).where(Organization.id == organization_id))
            ).scalar_one_or_none()
            if org is False:
                raise PermissionDeniedError(
                    "This organization has been suspended. Contact the platform administrator."
                )

        is_platform_direct = permission_code in _PLATFORM_DIRECT_PERMISSIONS
        allowed = (current_user.is_superuser and is_platform_direct) or await user_has_permission(
            db,
            user_id=current_user.id,
            organization_id=organization_id,
            station_id=station_id,
            permission_code=permission_code,
        )
        if not allowed and current_user.is_superuser and not is_platform_direct:
            # No real role grants this - the only other legitimate path is
            # an active, scope-matching, read-only support session (Phase
            # 5b). This never grants a write: support_session_grants
            # rejects any permission_code that isn't a ':read' code.
            session = await support_session_grants(
                db,
                current_user=current_user,
                organization_id=organization_id,
                station_id=station_id,
                permission_code=permission_code,
            )
            allowed = session is not None
        if not allowed:
            if current_user.is_superuser and not is_platform_direct:
                # Committed immediately, on its own - there is no
                # mutation for this denial to share a transaction with.
                await write_audit_log(
                    db,
                    action="support_session.access_denied",
                    entity_type="Organization",
                    entity_id=str(organization_id),
                    actor_user_id=current_user.id,
                    organization_id=organization_id,
                    station_id=station_id,
                    after={"permission_code": permission_code},
                )
                await db.commit()
            raise PermissionDeniedError()
        return current_user

    return dependency
