import uuid

from peewee import CharField, DateTimeField, ForeignKeyField, TextField, UUIDField

from app.models.base import BaseModel
from app.models.device import Device, utc_now


class Message(BaseModel):
    id = UUIDField(primary_key=True, default=uuid.uuid4)
    observer_device = ForeignKeyField(Device, backref="observed_messages", index=True)
    sender_device = ForeignKeyField(Device, backref="sent_messages", index=True)
    message_type = CharField(index=True, max_length=32)
    text = TextField(null=True)
    created_at = DateTimeField(default=utc_now, index=True)
    delivered_at = DateTimeField(null=True)

    class Meta:
        table_name = "messages"
