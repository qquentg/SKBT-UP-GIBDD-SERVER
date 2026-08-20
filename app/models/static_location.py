from peewee import DoubleField, ForeignKeyField

from app.models.base import BaseModel
from app.models.message import Message


class StaticLocation(BaseModel):
    message = ForeignKeyField(Message, backref="static_location", primary_key=True)
    latitude = DoubleField()
    longitude = DoubleField()

    class Meta:
        table_name = "static_locations"
