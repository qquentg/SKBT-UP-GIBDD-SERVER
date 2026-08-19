import pytest
from fastapi.testclient import TestClient
from peewee import SqliteDatabase

from app.db.database import create_tables, database_proxy
from app.main import create_app
from app.models.device import Device
from app.models.role_event import RoleEvent


@pytest.fixture
def client(tmp_path):
    test_database = SqliteDatabase(tmp_path / "test.db")
    database_proxy.initialize(test_database)
    test_database.bind([Device, RoleEvent], bind_refs=False, bind_backrefs=False)
    test_database.connect()
    create_tables()

    with TestClient(create_app(enable_lifespan=False)) as test_client:
        yield test_client

    test_database.drop_tables([RoleEvent, Device], safe=True)
    test_database.close()
