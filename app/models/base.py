from peewee import Model

from app.db.database import database_proxy


class BaseModel(Model):
    class Meta:
        database = database_proxy

