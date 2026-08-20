from peewee import CompositeKey, DateTimeField, DoubleField, ForeignKeyField

from app.models.base import BaseModel
from app.models.device import utc_now
from app.models.message import Message


class LocationPoint(BaseModel):
    message = ForeignKeyField(Message, backref="location_points")
    recorded_at = DateTimeField(default=utc_now)
    latitude = DoubleField()
    longitude = DoubleField()

    class Meta:
        table_name = "location_points"
        primary_key = CompositeKey("message", "recorded_at")
