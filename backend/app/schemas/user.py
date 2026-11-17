import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=10, max_length=200)
    employee_code: str | None = Field(default=None, max_length=50)
    job_title: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=30)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    is_active: bool | None = None
    employee_code: str | None = Field(default=None, max_length=50)
    job_title: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=30)


class UserRead(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    employee_code: str | None
    job_title: str | None
    phone: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class RoleAssignmentCreate(BaseModel):
    role_id: uuid.UUID
    station_id: uuid.UUID | None = Field(
        default=None, description="Leave null for an organization-wide role (e.g. Owner)."
    )


class RoleAssignmentRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    organization_id: uuid.UUID
    station_id: uuid.UUID | None
    role_id: uuid.UUID
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
