from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class BanResponse(BaseModel):
    ban_id: UUID
    observer_device_id: UUID
    issued_by_device_id: UUID
    started_at: datetime
    ends_at: datetime | None
    ban_number: int
    is_active: bool


class BansResponse(BaseModel):
    bans: list[BanResponse]


class ActiveBanResponse(BaseModel):
    ban: BanResponse | None
