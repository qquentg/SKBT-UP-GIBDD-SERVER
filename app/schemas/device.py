from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field


class ClientApp(StrEnum):
    EYEWITNESS = "eyewitness"
    EMPLOYEE = "employee"


class DeviceRole(StrEnum):
    INSPECTOR = "INSPECTOR"
    ADMIN = "ADMIN"
    CHIEF = "CHIEF"


class RoleAction(StrEnum):
    AUTO_ASSIGNED = "AUTO_ASSIGNED"
    ASSIGNED = "ASSIGNED"
    REPLACED = "REPLACED"
    REMOVED = "REMOVED"


class DeviceRegisterRequest(BaseModel):
    fingerprint_hash: Annotated[str, Field(min_length=32, max_length=128)]
    push_token: Annotated[str | None, Field(max_length=512)] = None


class DeviceRegisterResponse(BaseModel):
    device_id: UUID
    role: DeviceRole | None
    access_token: str
