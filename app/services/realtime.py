import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.models.ban import Ban
from app.models.device import Device
from app.models.location_point import LocationPoint
from app.models.message import Message
from app.schemas.device import ClientApp, DeviceRole
from app.services.message_payloads import location_point_payload, message_payload

EMPLOYEE_REALTIME_ROLES = {
    DeviceRole.INSPECTOR.value,
    DeviceRole.ADMIN.value,
    DeviceRole.CHIEF.value,
}


@dataclass(frozen=True)
class RealtimeConnection:
    device_id: str
    client_app: ClientApp
    role: str | None
    queue: asyncio.Queue
    loop: asyncio.AbstractEventLoop


class RealtimeManager:
    def __init__(self) -> None:
        self._connections: set[RealtimeConnection] = set()

    def connect(self, *, device: Device, client_app: ClientApp) -> RealtimeConnection:
        connection = RealtimeConnection(
            device_id=str(device.id),
            client_app=client_app,
            role=device.current_role,
            queue=asyncio.Queue(maxsize=100),
            loop=asyncio.get_running_loop(),
        )
        self._connections.add(connection)
        return connection

    def disconnect(self, connection: RealtimeConnection) -> None:
        self._connections.discard(connection)

    def publish_to_devices(self, device_ids: set[str], event: dict) -> None:
        for connection in list(self._connections):
            if connection.device_id in device_ids:
                self._enqueue(connection, event)

    def publish_to_employee_roles(self, roles: set[str], event: dict) -> None:
        for connection in list(self._connections):
            if connection.client_app != ClientApp.EMPLOYEE:
                continue
            current_role = _current_role(connection.device_id)
            if current_role in roles:
                self._enqueue(connection, event)

    def _enqueue(self, connection: RealtimeConnection, event: dict) -> None:
        def put_event() -> None:
            if connection.queue.full():
                try:
                    connection.queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            connection.queue.put_nowait(event)

        connection.loop.call_soon_threadsafe(put_event)


manager = RealtimeManager()


def publish_message_created(message: Message) -> None:
    event = {
        "event": "message_created",
        "message": message_payload(message),
    }
    if str(message.sender_device_id) == str(message.observer_device_id):
        manager.publish_to_employee_roles(_employee_roles_for_message(message), event)
        return

    manager.publish_to_devices({str(message.observer_device_id)}, event)


def publish_message_delivered(message: Message) -> None:
    event = {
        "event": "message_delivered",
        "message": message_payload(message),
    }
    manager.publish_to_devices({str(message.observer_device_id)}, event)
    manager.publish_to_employee_roles(_employee_roles_for_message(message), event)


def publish_live_location_point(message: Message, point: LocationPoint) -> None:
    event = {
        "event": "live_location_point",
        "message_id": str(message.id),
        "observer_device_id": str(message.observer_device_id),
        "sender_device_id": str(message.sender_device_id),
        "point": location_point_payload(point),
    }
    manager.publish_to_devices({str(message.observer_device_id)}, event)
    manager.publish_to_employee_roles(_employee_roles_for_message(message), event)


def publish_live_location_stopped(message: Message) -> None:
    event = {
        "event": "live_location_stopped",
        "message": message_payload(message),
    }
    manager.publish_to_devices({str(message.observer_device_id)}, event)
    manager.publish_to_employee_roles(_employee_roles_for_message(message), event)


def publish_observer_banned(ban: Ban, *, actor_device_id: UUID) -> None:
    event = {
        "event": "observer_banned",
        "ban": {
            "ban_id": str(ban.id),
            "observer_device_id": str(ban.observer_device_id),
            "issued_by_device_id": str(ban.issued_by_device_id),
            "started_at": ban.started_at.isoformat(),
            "ends_at": ban.ends_at.isoformat() if ban.ends_at is not None else None,
        },
    }
    manager.publish_to_devices({str(ban.observer_device_id)}, event)
    manager.publish_to_employee_roles({DeviceRole.CHIEF.value}, event)


def publish_role_changed(
    *,
    actor_device_id: UUID,
    target_device_id: UUID,
    action: str,
    role: str | None,
) -> None:
    event = {
        "event": "role_changed",
        "actor_device_id": str(actor_device_id),
        "target_device_id": str(target_device_id),
        "action": action,
        "role": role,
    }
    manager.publish_to_devices({str(target_device_id)}, event)
    manager.publish_to_employee_roles({DeviceRole.CHIEF.value}, event)


def _get_active_ban(observer_device_id: UUID) -> Ban | None:
    from app.models.device import utc_now

    now = utc_now()
    for ban in (
        Ban.select()
        .where(Ban.observer_device == observer_device_id)
        .order_by(Ban.started_at.desc(), Ban.id.desc())
    ):
        if _as_utc_aware(ban.started_at) <= now and (
            ban.ends_at is None or _as_utc_aware(ban.ends_at) > now
        ):
            return ban
    return None


def _employee_roles_for_message(message: Message) -> set[str]:
    if _get_active_ban(message.observer_device_id) is not None:
        return {DeviceRole.CHIEF.value}
    if _get_ban_at(message.observer_device_id, message.created_at) is not None:
        return {DeviceRole.CHIEF.value}
    return EMPLOYEE_REALTIME_ROLES


def _get_ban_at(observer_device_id: UUID, moment: datetime) -> Ban | None:
    target = _as_utc_aware(moment)
    for ban in (
        Ban.select()
        .where(Ban.observer_device == observer_device_id)
        .order_by(Ban.started_at.desc(), Ban.id.desc())
    ):
        if _as_utc_aware(ban.started_at) <= target and (
            ban.ends_at is None or _as_utc_aware(ban.ends_at) > target
        ):
            return ban
    return None


def _current_role(device_id: str) -> str | None:
    device = Device.get_or_none(Device.id == device_id)
    return device.current_role if device is not None else None


def _as_utc_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=_local_timezone()).astimezone(UTC)
    return value.astimezone(UTC)


def _local_timezone():
    return datetime.now().astimezone().tzinfo
