import uuid
from datetime import datetime

from pydantic import BaseModel


class AuditLogRead(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID | None
    station_id: uuid.UUID | None
    actor_user_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: str
    before: dict | None
    after: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}
