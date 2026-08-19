from peewee import DatabaseProxy, PostgresqlDatabase

from app.core.config import Settings, get_settings

database_proxy = DatabaseProxy()


def init_database(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    database = PostgresqlDatabase(
        settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
        host=settings.db_host,
        port=settings.db_port,
    )
    database_proxy.initialize(database)


def connect_database() -> None:
    database_proxy.connect(reuse_if_open=True)


def close_database() -> None:
    if not database_proxy.is_closed():
        database_proxy.close()


def create_tables() -> None:
    from app.models.device import Device
    from app.models.role_event import RoleEvent

    database_proxy.create_tables([Device, RoleEvent], safe=True)
    database_proxy.execute_sql("DROP INDEX IF EXISTS devices_single_chief_idx")
