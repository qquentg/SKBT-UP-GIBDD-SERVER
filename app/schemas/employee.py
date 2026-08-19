from uuid import UUID

from pydantic import BaseModel

from app.schemas.device import DeviceRole


class DeviceProfileResponse(BaseModel):
    device_id: UUID
    role: DeviceRole | None


class AssignRoleRequest(BaseModel):
    role: DeviceRole


class RoleEventResponse(BaseModel):
    action: str | None


class RoleChangeResponse(BaseModel):
    device_id: UUID
    role: DeviceRole | None
    event: RoleEventResponse | None = None
