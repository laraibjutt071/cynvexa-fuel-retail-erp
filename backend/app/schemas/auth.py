import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    """Self-service sign-up: one call creates the company (Organization),
    its first station, the caller as that organization's Owner, and a
    trial Subscription - see app/api/auth.py::register for the exact
    sequence and docs/ASSUMPTIONS.md for what's still a default, not a
    verified business rule (no email verification step exists yet)."""

    company_name: str = Field(min_length=1, max_length=200)
    station_name: str = Field(default="Main Station", min_length=1, max_length=200)
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(min_length=10, max_length=200)
    plan_code: str | None = Field(default=None, description="Defaults to the 'starter' plan if omitted.")


class RegisterResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    organization_id: uuid.UUID
    station_id: uuid.UUID


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=200)


class SessionRead(BaseModel):
    id: uuid.UUID
    created_at: datetime
    expires_at: datetime

    model_config = {"from_attributes": True}


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


class StationRoleSummary(BaseModel):
    organization_id: uuid.UUID
    station_id: uuid.UUID | None
    role_name: str
    permissions: list[str]


class MeResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_superuser: bool
    station_roles: list[StationRoleSummary]
