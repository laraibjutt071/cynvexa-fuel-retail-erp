import uuid

from pydantic import BaseModel


class PermissionRead(BaseModel):
    id: uuid.UUID
    code: str
    description: str

    model_config = {"from_attributes": True}


class RoleRead(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    is_system: bool
    permissions: list[PermissionRead]

    model_config = {"from_attributes": True}
