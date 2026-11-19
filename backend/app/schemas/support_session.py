import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.support_sessions import SUPPORT_SESSION_ALLOWED_DURATIONS_MINUTES

SupportSessionStatus = Literal["active", "ended", "expired"]


class SupportSessionCreate(BaseModel):
    organization_id: uuid.UUID
    station_id: uuid.UUID | None = Field(default=None, description="Leave null for an organization-wide session.")
    reason: str = Field(min_length=10, max_length=500)
    duration_minutes: int

    @field_validator("duration_minutes")
    @classmethod
    def _validate_duration(cls, value: int) -> int:
        # Never trust a client-supplied expiry - only one of these fixed,
        # server-defined durations may be requested at all.
        if value not in SUPPORT_SESSION_ALLOWED_DURATIONS_MINUTES:
            allowed = ", ".join(str(m) for m in SUPPORT_SESSION_ALLOWED_DURATIONS_MINUTES)
            raise ValueError(f"duration_minutes must be one of: {allowed}")
        return value


class SupportSessionRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    organization_name: str
    station_id: uuid.UUID | None
    station_name: str | None
    reason: str
    created_at: datetime
    expires_at: datetime
    ended_at: datetime | None
    status: SupportSessionStatus
