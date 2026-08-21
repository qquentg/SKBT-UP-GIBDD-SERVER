import uuid

from peewee import DateTimeField, ForeignKeyField, UUIDField

from app.models.base import BaseModel
from app.models.device import Device, utc_now


class Ban(BaseModel):
    id = UUIDField(primary_key=True, default=uuid.uuid4)
    observer_device = ForeignKeyField(Device, backref="bans_as_observer", index=True)
    issued_by_device = ForeignKeyField(Device, backref="issued_bans")
    started_at = DateTimeField(default=utc_now)
    ends_at = DateTimeField(null=True)

    class Meta:
        table_name = "bans"
