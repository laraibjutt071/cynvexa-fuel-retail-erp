import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


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
