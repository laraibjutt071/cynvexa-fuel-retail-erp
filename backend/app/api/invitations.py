"""
Phase 5a: secure, token-based staff onboarding - replaces "the Owner
types a password for someone else" with a single-use, time-limited
link the invited person uses to set their own password. Mirrors the
refresh-token pattern exactly: only the token's SHA-256 hash is ever
stored, the raw value is returned exactly once at creation.

Two routers:
- `router` (org-scoped, authenticated) - create/list/revoke invitations.
- `public_router` (no auth, same pattern as platform.py's public_router)
  - preview and accept, reachable by someone who isn't a user yet.
"""

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import _issue_tokens
from app.api.common import get_organization_or_404
from app.api.deps import get_db, require_permission
from app.core.audit import write_audit_log
from app.core.permission_codes import USER_ASSIGN_ROLE, USER_CREATE, USER_READ
from app.core.permissions import actor_can_grant_scope
from app.core.rate_limit import registration_limiter
from app.core.security import hash_password, hash_refresh_token
from app.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationFailedError
from app.models.invitation import Invitation
from app.models.organization import Organization
from app.models.role import Role
from app.models.station import Station
from app.models.user import User
from app.models.user_station_role import UserStationRole
from app.schemas.auth import AccessTokenResponse
from app.schemas.invitation import (
    InvitationAccept,
    InvitationCreate,
    InvitationCreateResponse,
    InvitationPreview,
    InvitationRead,
)

router = APIRouter(prefix="/organizations/{organization_id}/invitations", tags=["invitations"])
public_router = APIRouter(prefix="/invitations", tags=["invitations"])

INVITATION_EXPIRE_HOURS = 72


@router.post("", response_model=InvitationCreateResponse, status_code=201)
async def create_invitation(
    organization_id: uuid.UUID,
    payload: InvitationCreate,
    request: Request,
    current_user: User = Depends(require_permission(USER_CREATE)),
    db: AsyncSession = Depends(get_db),
) -> InvitationCreateResponse:
    await get_organization_or_404(db, organization_id)

    # Same scope check assign_role already uses (app/api/users.py) - an
    # inviter cannot pre-grant a role at a wider scope than their own. No
    # support-session path here (Phase 5b): invitations are a write, and
    # support sessions are read-only, same as role assignment.
    if not await actor_can_grant_scope(
        db, user_id=current_user.id, organization_id=organization_id, target_station_id=payload.station_id,
        permission_code=USER_ASSIGN_ROLE,
    ):
        raise PermissionDeniedError("You cannot invite someone to a wider scope than your own access.")

    existing_user = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if existing_user is not None:
        raise ConflictError("An account with this email already exists. Assign them a role directly instead.")

    role = (await db.execute(select(Role).where(Role.id == payload.role_id))).scalar_one_or_none()
    if role is None:
        raise NotFoundError("Role not found.")
    if payload.station_id is not None:
        station = (
            await db.execute(
                select(Station).where(Station.id == payload.station_id, Station.organization_id == organization_id)
            )
        ).scalar_one_or_none()
        if station is None:
            raise ValidationFailedError("Station does not belong to this organization.")

    raw_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=INVITATION_EXPIRE_HOURS)
    invitation = Invitation(
        organization_id=organization_id,
        email=payload.email,
        full_name=payload.full_name,
        role_id=payload.role_id,
        station_id=payload.station_id,
        token_hash=hash_refresh_token(raw_token),
        expires_at=expires_at,
        invited_by_user_id=current_user.id,
    )
    db.add(invitation)
    await db.flush()

    await write_audit_log(
        db,
        action="invitation.create",
        entity_type="Invitation",
        entity_id=str(invitation.id),
        actor_user_id=current_user.id,
        organization_id=organization_id,
        after={"email": payload.email, "role_id": str(payload.role_id)},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()

    return InvitationCreateResponse(
        id=invitation.id, email=invitation.email, full_name=invitation.full_name,
        expires_at=invitation.expires_at, token=raw_token,
    )


@router.get("", response_model=list[InvitationRead])
async def list_invitations(
    organization_id: uuid.UUID,
    current_user: User = Depends(require_permission(USER_READ)),
    db: AsyncSession = Depends(get_db),
) -> list[Invitation]:
    stmt = (
        select(Invitation)
        .where(Invitation.organization_id == organization_id)
        .order_by(Invitation.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


@router.delete("/{invitation_id}", status_code=204)
async def revoke_invitation(
    organization_id: uuid.UUID,
    invitation_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_permission(USER_CREATE)),
    db: AsyncSession = Depends(get_db),
) -> None:
    invitation = (
        await db.execute(
            select(Invitation).where(Invitation.id == invitation_id, Invitation.organization_id == organization_id)
        )
    ).scalar_one_or_none()
    if invitation is None:
        raise NotFoundError("Invitation not found.")
    if invitation.accepted_at is not None:
        raise ValidationFailedError("This invitation has already been accepted and cannot be revoked.")

    invitation.revoked_at = datetime.now(timezone.utc)
    await write_audit_log(
        db, action="invitation.revoke", entity_type="Invitation", entity_id=str(invitation.id),
        actor_user_id=current_user.id, organization_id=organization_id,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()


async def _get_valid_invitation(db: AsyncSession, token: str) -> Invitation:
    token_hash = hash_refresh_token(token)
    invitation = (await db.execute(select(Invitation).where(Invitation.token_hash == token_hash))).scalar_one_or_none()
    if invitation is None:
        raise NotFoundError("This invitation link is invalid.")
    return invitation


def _invitation_status(invitation: Invitation) -> str | None:
    if invitation.revoked_at is not None:
        return "This invitation has been revoked."
    if invitation.accepted_at is not None:
        return "This invitation has already been used."
    if invitation.expires_at < datetime.now(timezone.utc):
        return "This invitation link has expired. Ask your organization to send a new one."
    return None


@public_router.get("/{token}/preview", response_model=InvitationPreview)
async def preview_invitation(token: str, db: AsyncSession = Depends(get_db)) -> InvitationPreview:
    """Public, no auth - lets someone who isn't a user yet see which
    organization/role they're about to join before they set a password.
    Reveals nothing beyond that (no org financial/operational data)."""
    try:
        invitation = await _get_valid_invitation(db, token)
    except NotFoundError:
        return InvitationPreview(
            organization_name="", email="", full_name="", role_name="", station_name=None,
            valid=False, reason="This invitation link is invalid.",
        )

    reason = _invitation_status(invitation)
    org = await db.get(Organization, invitation.organization_id)
    role = await db.get(Role, invitation.role_id)
    station = await db.get(Station, invitation.station_id) if invitation.station_id else None

    return InvitationPreview(
        organization_name=org.name if org else "—",
        email=invitation.email,
        full_name=invitation.full_name,
        role_name=role.name if role else "—",
        station_name=station.name if station else None,
        valid=reason is None,
        reason=reason,
    )


@public_router.post("/accept", response_model=AccessTokenResponse)
async def accept_invitation(
    payload: InvitationAccept, request: Request, response: Response, db: AsyncSession = Depends(get_db)
) -> AccessTokenResponse:
    client_ip = request.client.host if request.client else "unknown"
    registration_limiter.check(client_ip)

    invitation = await _get_valid_invitation(db, payload.token)
    reason = _invitation_status(invitation)
    if reason is not None:
        raise ValidationFailedError(reason)

    existing_user = (await db.execute(select(User).where(User.email == invitation.email))).scalar_one_or_none()
    if existing_user is not None:
        raise ConflictError("An account with this email already exists. Try logging in instead.")

    user = User(
        email=invitation.email, full_name=invitation.full_name, hashed_password=hash_password(payload.password)
    )
    db.add(user)
    await db.flush()

    db.add(
        UserStationRole(
            user_id=user.id, organization_id=invitation.organization_id,
            station_id=invitation.station_id, role_id=invitation.role_id,
        )
    )
    invitation.accepted_at = datetime.now(timezone.utc)
    invitation.created_user_id = user.id
    await db.flush()

    await write_audit_log(
        db, action="invitation.accept", entity_type="User", entity_id=str(user.id),
        actor_user_id=user.id, organization_id=invitation.organization_id,
        after={"email": user.email, "invitation_id": str(invitation.id)}, ip_address=client_ip,
    )

    return await _issue_tokens(db, user, response)
