import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Cookie, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.config import get_settings
from app.core.audit import write_audit_log
from app.core.rate_limit import login_limiter
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.exceptions import AuthenticationError
from app.models.refresh_token import RefreshToken
from app.models.role import Role
from app.models.user import User
from app.models.user_station_role import UserStationRole
from app.schemas.auth import (
    AccessTokenResponse,
    ChangePasswordRequest,
    LoginRequest,
    MeResponse,
    SessionRead,
    StationRoleSummary,
)

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/auth"


def _set_refresh_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=raw_token,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        max_age=settings.refresh_token_expire_days * 86400,
        path=REFRESH_COOKIE_PATH,
    )


async def _revoke_all_sessions(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Revokes every refresh token for the user that isn't already revoked.
    Does not commit - callers decide the transaction boundary."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
    )
    for row in result.scalars():
        row.revoked_at = now


async def _issue_tokens(db: AsyncSession, user: User, response: Response) -> AccessTokenResponse:
    raw_refresh, token_hash, expires_at = generate_refresh_token()
    db.add(RefreshToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at))
    await db.commit()
    _set_refresh_cookie(response, raw_refresh)
    return AccessTokenResponse(
        access_token=create_access_token(user.id),
        expires_in_minutes=settings.access_token_expire_minutes,
    )


@router.post("/login", response_model=AccessTokenResponse)
async def login(
    payload: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)
) -> AccessTokenResponse:
    # Keyed by email+IP, not IP alone, so one attacker IP hammering many
    # accounts and many attacker IPs hammering one account are both
    # throttled - see login_limiter's own docstring for what this does and
    # does not protect against (single-process only).
    client_ip = request.client.host if request.client else "unknown"
    login_limiter.check(f"{payload.email}:{client_ip}")

    user = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    # Constant-shape response whether the email exists or not, to avoid leaking account existence.
    if user is None or not user.is_active or not verify_password(payload.password, user.hashed_password):
        raise AuthenticationError("Incorrect email or password.")
    login_limiter.reset(f"{payload.email}:{client_ip}")
    return await _issue_tokens(db, user, response)


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh(
    response: Response,
    db: AsyncSession = Depends(get_db),
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
) -> AccessTokenResponse:
    if not refresh_token:
        raise AuthenticationError("Missing refresh token.")

    token_hash = hash_refresh_token(refresh_token)
    stored = (
        await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    ).scalar_one_or_none()

    if stored is None:
        raise AuthenticationError("Invalid refresh token.")

    if stored.revoked_at is not None:
        # Reuse of an already-rotated token: treat as a possible theft and revoke
        # every active refresh token for this user as a precaution.
        await _revoke_all_sessions(db, stored.user_id)
        await db.commit()
        raise AuthenticationError("Refresh token has already been used. Please log in again.")

    if stored.expires_at < datetime.now(timezone.utc):
        raise AuthenticationError("Refresh token has expired. Please log in again.")

    user = (await db.execute(select(User).where(User.id == stored.user_id))).scalar_one_or_none()
    if user is None or not user.is_active:
        raise AuthenticationError("Account is inactive or no longer exists.")

    raw_refresh, token_hash, expires_at = generate_refresh_token()
    new_token = RefreshToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at)
    db.add(new_token)
    await db.flush()
    stored.revoked_at = datetime.now(timezone.utc)
    stored.replaced_by_id = new_token.id
    await db.commit()

    _set_refresh_cookie(response, raw_refresh)
    return AccessTokenResponse(
        access_token=create_access_token(user.id),
        expires_in_minutes=settings.access_token_expire_minutes,
    )


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    db: AsyncSession = Depends(get_db),
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
) -> None:
    if refresh_token:
        token_hash = hash_refresh_token(refresh_token)
        stored = (
            await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
        ).scalar_one_or_none()
        if stored is not None and stored.revoked_at is None:
            stored.revoked_at = datetime.now(timezone.utc)
            await db.commit()
    response.delete_cookie(REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)


@router.get("/me", response_model=MeResponse)
async def me(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> MeResponse:
    stmt = (
        select(UserStationRole)
        .options(selectinload(UserStationRole.role).selectinload(Role.permissions))
        .where(UserStationRole.user_id == current_user.id, UserStationRole.is_active.is_(True))
    )
    rows = (await db.execute(stmt)).scalars().all()
    return MeResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        is_superuser=current_user.is_superuser,
        station_roles=[
            StationRoleSummary(
                organization_id=r.organization_id,
                station_id=r.station_id,
                role_name=r.role.name,
                permissions=[p.code for p in r.role.permissions],
            )
            for r in rows
        ],
    )


@router.patch("/password", status_code=204)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise AuthenticationError("Current password is incorrect.")

    current_user.hashed_password = hash_password(payload.new_password)
    # Changing a password is a signal that every other session should be
    # forced to re-authenticate - a leaked credential being replaced should
    # not leave a previously-issued session usable.
    await _revoke_all_sessions(db, current_user.id)
    await write_audit_log(
        db,
        action="user.change_password",
        entity_type="User",
        entity_id=str(current_user.id),
        actor_user_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()


@router.get("/sessions", response_model=list[SessionRead])
async def list_sessions(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[RefreshToken]:
    """Active (non-revoked, non-expired) sessions for the signed-in user.
    Never exposes the token itself - only enough to recognize and revoke one."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == current_user.id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > now,
        )
    )
    return list(result.scalars().all())


@router.post("/logout-all", status_code=204)
async def logout_all(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Revokes every active session for the signed-in user - e.g. after a
    lost device. The caller's own current refresh token is revoked too; its
    access token remains valid only until it naturally expires."""
    await _revoke_all_sessions(db, current_user.id)
    await write_audit_log(
        db,
        action="user.logout_all_sessions",
        entity_type="User",
        entity_id=str(current_user.id),
        actor_user_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
