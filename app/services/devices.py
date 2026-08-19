from peewee import IntegrityError, PostgresqlDatabase

from app.db.database import database_proxy
from app.models.device import Device, utc_now
from app.models.role_event import RoleEvent
from app.schemas.device import ClientApp, DeviceRole, RoleAction

BOOTSTRAP_CHIEF_LOCK_KEY = 20260819


def register_device(
    *,
    fingerprint_hash: str,
    client_app: ClientApp,
    push_token: str | None = None,
) -> Device:
    with database_proxy.atomic():
        device, _ = Device.get_or_create(
            fingerprint_hash=fingerprint_hash,
            defaults={
                "push_token": push_token,
                "last_activity_at": utc_now(),
            },
        )

        changes: dict[str, object] = {"last_activity_at": utc_now()}
        if push_token is not None and device.push_token != push_token:
            changes["push_token"] = push_token

        if changes:
            Device.update(**changes).where(Device.id == device.id).execute()
            device = Device.get_by_id(device.id)

    if client_app == ClientApp.EMPLOYEE and device.current_role is None:
        _bootstrap_chief_if_needed(device)
        device = Device.get_by_id(device.id)

    return device


def _bootstrap_chief_if_needed(device: Device) -> None:
    try:
        with database_proxy.atomic():
            _lock_chief_bootstrap_for_transaction()

            chief_exists = (
                Device.select(Device.id)
                .where(Device.current_role == DeviceRole.CHIEF.value)
                .exists()
            )
            if chief_exists:
                return

            updated = (
                Device.update(
                    current_role=DeviceRole.CHIEF.value,
                    last_activity_at=utc_now(),
                )
                .where(
                    (Device.id == device.id)
                    & (Device.current_role.is_null(True))
                )
                .execute()
            )
            if updated != 1:
                return

            RoleEvent.create(
                actor_device=None,
                target_device=device.id,
                action=RoleAction.AUTO_ASSIGNED.value,
                role=DeviceRole.CHIEF.value,
            )
    except IntegrityError:
        return


def _lock_chief_bootstrap_for_transaction() -> None:
    if isinstance(database_proxy.obj, PostgresqlDatabase):
        database_proxy.execute_sql(
            "SELECT pg_advisory_xact_lock(%s)",
            (BOOTSTRAP_CHIEF_LOCK_KEY,),
        )
