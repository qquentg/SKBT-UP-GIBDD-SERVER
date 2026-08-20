from peewee import DateTimeField, ForeignKeyField

from app.models.base import BaseModel
from app.models.message import Message


class LiveLocationSession(BaseModel):
    message = ForeignKeyField(Message, backref="live_location_session", primary_key=True)
    ends_at = DateTimeField()

    class Meta:
        table_name = "live_location_sessions"
