import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class InvitationCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    role_id: uuid.UUID
    station_id: uuid.UUID | None = Field(default=None, description="Leave null for an organization-wide role.")


class InvitationCreateResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    expires_at: datetime
    # The raw token - returned exactly once, here, at creation. Never
    # stored in plaintext, never re-displayed, never logged. The inviter
    # copies this into the accept-invite link and sends it themselves -
    # no email infrastructure exists in this project (see the model's
    # own docstring and docs/PHASE_5_MARKET_READINESS_AUDIT.md).
    token: str


class InvitationRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    email: str
    full_name: str
    role_id: uuid.UUID
    station_id: uuid.UUID | None
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None
    invited_by_user_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class InvitationPreview(BaseModel):
    """What the public accept-invite page shows before the person sets a
    password - confirms which organization/role they're joining without
    requiring auth, and without leaking anything beyond that."""

    organization_name: str
    email: str
    full_name: str
    role_name: str
    station_name: str | None
    valid: bool
    reason: str | None = None


class InvitationAccept(BaseModel):
    token: str
    password: str = Field(min_length=10, max_length=200)
