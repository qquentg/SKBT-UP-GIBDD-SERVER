import uuid

from peewee import CharField, DateTimeField, ForeignKeyField, UUIDField

from app.models.base import BaseModel
from app.models.device import Device, utc_now


class RoleEvent(BaseModel):
    id = UUIDField(primary_key=True, default=uuid.uuid4)
    actor_device = ForeignKeyField(Device, backref="role_events_as_actor", null=True)
    target_device = ForeignKeyField(Device, backref="role_events_as_target")
    action = CharField(max_length=32)
    role = CharField(max_length=16)
    created_at = DateTimeField(default=utc_now)

    class Meta:
        table_name = "role_events"
