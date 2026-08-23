from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.device import DeviceRole


class DeviceProfileResponse(BaseModel):
    device_id: UUID
    role: DeviceRole | None


class EmployeeDeviceResponse(BaseModel):
    device_id: UUID
    role: DeviceRole
    last_activity_at: datetime


class EmployeeDevicesResponse(BaseModel):
    devices: list[EmployeeDeviceResponse]


class AssignRoleRequest(BaseModel):
    role: DeviceRole


class RoleEventResponse(BaseModel):
    action: str | None


class RoleChangeResponse(BaseModel):
    device_id: UUID
    role: DeviceRole | None
    event: RoleEventResponse | None = None
