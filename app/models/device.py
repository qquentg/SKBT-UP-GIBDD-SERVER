import uuid
from datetime import UTC, datetime

from peewee import CharField, DateTimeField, UUIDField

from app.models.base import BaseModel


def utc_now() -> datetime:
    return datetime.now(UTC)


class Device(BaseModel):
    id = UUIDField(primary_key=True, default=uuid.uuid4)
    fingerprint_hash = CharField(unique=True, index=True, max_length=128)
    access_token_hash = CharField(null=True, max_length=128)
    current_role = CharField(null=True, index=True, max_length=16)
    push_token = CharField(null=True, max_length=512)
    last_activity_at = DateTimeField(default=utc_now)

    class Meta:
        table_name = "devices"
