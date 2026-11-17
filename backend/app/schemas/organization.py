import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    legal_name: str | None = Field(default=None, max_length=300)


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    legal_name: str | None = Field(default=None, max_length=300)
    is_active: bool | None = None
    currency_code: str | None = Field(default=None, min_length=3, max_length=3)
    phone: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=300)
    city: str | None = Field(default=None, max_length=100)
    province: str | None = Field(default=None, max_length=100)
    country: str | None = Field(default=None, max_length=100)


class OrganizationRead(BaseModel):
    id: uuid.UUID
    name: str
    legal_name: str | None
    is_active: bool
    currency_code: str | None
    phone: str | None
    address: str | None
    city: str | None
    province: str | None
    country: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TenantOnboardingRequest(BaseModel):
    """Super Admin's 'Create Petrol Pump' workflow - one call provisions the
    organization, its first station, the owner account, and the Owner role
    assignment. Reuses the exact same provisioning logic as public
    self-service registration (app/core/tenant_provisioning.py) - this is
    not a parallel/duplicated path, just a different caller and response
    shape (no auto-login, since the caller is the platform admin, not the
    new owner)."""

    company_name: str = Field(min_length=1, max_length=200)
    station_name: str = Field(default="Main Station", min_length=1, max_length=200)
    owner_full_name: str = Field(min_length=1, max_length=200)
    owner_email: EmailStr
    owner_password: str = Field(min_length=10, max_length=200)
    plan_code: str | None = None
    phone: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=300)
    city: str | None = Field(default=None, max_length=100)
    province: str | None = Field(default=None, max_length=100)
    country: str | None = Field(default=None, max_length=100)


class TenantOnboardingResponse(BaseModel):
    organization_id: uuid.UUID
    organization_name: str
    station_id: uuid.UUID
    owner_user_id: uuid.UUID
    owner_email: str
