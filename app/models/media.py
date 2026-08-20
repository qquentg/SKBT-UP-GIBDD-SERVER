from peewee import CharField, DateTimeField, ForeignKeyField

from app.models.base import BaseModel
from app.models.message import Message


class Media(BaseModel):
    message = ForeignKeyField(Message, backref="media", primary_key=True)
    storage_key = CharField(max_length=512)
    mime_type = CharField(max_length=128)
    last_viewed_at = DateTimeField(null=True)

    class Meta:
        table_name = "media"
