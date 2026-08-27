import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Thread
from uuid import UUID

import httpx

from app.core.config import get_settings
from app.models.ban import Ban
from app.models.device import Device
from app.models.message import Message
from app.models.role_event import RoleEvent
from app.schemas.device import DeviceRole
from app.schemas.messages import MessageType

logger = logging.getLogger(__name__)

FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
EMPLOYEE_PUSH_ROLES = {
    DeviceRole.INSPECTOR.value,
    DeviceRole.ADMIN.value,
    DeviceRole.CHIEF.value,
}


@dataclass(frozen=True)
class PushNotification:
    device_id: str
    push_token: str
    title: str | None
    body: str | None
    data: dict[str, str]


def notify_message_created(message: Message) -> None:
    notifications = _message_notifications(message)
    send_push_notifications(notifications)


def notify_observer_banned(ban: Ban) -> None:
    notifications: list[PushNotification] = []
    data = {
        "event": "observer_banned",
        "ban_id": str(ban.id),
        "observer_device_id": str(ban.observer_device_id),
        "issued_by_device_id": str(ban.issued_by_device_id),
        "started_at": _datetime_data_value(ban.started_at),
        "ends_at": _optional_datetime_data_value(ban.ends_at),
        "ban_number": str(_ban_number(ban)),
    }
    observer = Device.get_or_none(Device.id == ban.observer_device_id)
    if observer is not None:
        notifications.extend(
            _notifications_for_devices(
                devices=[observer],
                title=None,
                body=None,
                data=data,
            )
        )

    chief_devices = _devices_with_push_token(
        Device.select().where(Device.current_role == DeviceRole.CHIEF.value)
    )
    notifications.extend(
        _notifications_for_devices(
            devices=chief_devices,
            title=None,
            body=None,
            data=data,
        )
    )
    send_push_notifications(notifications)


def notify_role_changed(
    role_event: RoleEvent,
    *,
    old_role: str | None,
    new_role: str | None,
) -> None:
    chief_devices = _devices_with_push_token(
        Device.select().where(Device.current_role == DeviceRole.CHIEF.value)
    )
    notifications = _notifications_for_devices(
        devices=chief_devices,
        title=None,
        body=None,
        data={
            "event": "role_changed",
            "event_id": str(role_event.id),
            "action": role_event.action,
            "issued_by_device_id": _optional_uuid_data_value(
                role_event.actor_device_id
            ),
            "target_device_id": str(role_event.target_device_id),
            "old_role": old_role or "",
            "new_role": new_role or "",
            "created_at": _datetime_data_value(role_event.created_at),
        },
    )
    send_push_notifications(notifications)


def send_push_notifications(notifications: list[PushNotification]) -> None:
    if not notifications:
        return

    settings = get_settings()
    if not settings.fcm_project_id or not settings.fcm_service_account_file:
        logger.info(
            "Push notifications skipped: FCM settings are not configured; push_count=%s",
            len(notifications),
        )
        return

    logger.info(
        "Push notifications queued: push_count=%s project_id=%s",
        len(notifications),
        settings.fcm_project_id,
    )

    Thread(
        target=_deliver_push_notifications,
        args=(
            notifications,
            settings.fcm_project_id,
            settings.fcm_service_account_file,
            settings.push_request_timeout_seconds,
        ),
        daemon=True,
    ).start()


def _deliver_push_notifications(
    notifications: list[PushNotification],
    fcm_project_id: str,
    fcm_service_account_file: str,
    timeout_seconds: float,
) -> None:
    try:
        access_token = _get_fcm_access_token(fcm_service_account_file)
    except Exception:
        logger.exception("Push notifications skipped: cannot get FCM access token")
        return

    url = (
        "https://fcm.googleapis.com/v1/projects/"
        f"{fcm_project_id}/messages:send"
    )
    headers = {"Authorization": f"Bearer {access_token}"}

    with httpx.Client(timeout=timeout_seconds) as client:
        for notification in notifications:
            message: dict = {
                "token": notification.push_token,
                "data": notification.data,
            }
            if notification.title is not None and notification.body is not None:
                message["notification"] = {
                    "title": notification.title,
                    "body": notification.body,
                }

            try:
                response = client.post(
                    url,
                    headers=headers,
                    json={"message": message},
                )
                if response.is_error:
                    logger.error(
                        "Push notification delivery failed: device_id=%s status=%s body=%s",
                        notification.device_id,
                        response.status_code,
                        response.text[:1000],
                    )
                    continue
                logger.info(
                    "Push notification delivered: device_id=%s status=%s body=%s",
                    notification.device_id,
                    response.status_code,
                    response.text[:500],
                )
            except httpx.HTTPError as exc:
                logger.exception(
                    "Push notification request failed: device_id=%s error=%s",
                    notification.device_id,
                    exc,
                )


def _message_notifications(message: Message) -> list[PushNotification]:
    common_data = {
        "event": "message_created",
        "message_id": str(message.id),
        "observer_device_id": str(message.observer_device_id),
        "sender_device_id": str(message.sender_device_id),
        "chat_message_type": message.message_type,
    }

    if str(message.sender_device_id) == str(message.observer_device_id):
        recipient_roles = (
            {DeviceRole.CHIEF.value}
            if _get_active_ban(message.observer_device_id) is not None
            else EMPLOYEE_PUSH_ROLES
        )
        recipients = _devices_with_push_token(
            Device.select().where(Device.current_role.in_(recipient_roles))
        )
        return _notifications_for_devices(
            devices=recipients,
            title="New eyewitness message",
            body=_message_body(message),
            data=common_data,
        )

    observer = Device.get_or_none(Device.id == message.observer_device_id)
    if observer is None:
        return []
    return _notifications_for_devices(
        devices=[observer],
        title="New employee message",
        body=_message_body(message),
        data=common_data,
    )


def _message_body(message: Message) -> str:
    if message.message_type == MessageType.TEXT.value:
        text = (message.text or "").strip()
        if text:
            return text[:120]
        return "Text message"
    if message.message_type == MessageType.MEDIA.value:
        return "Media message"
    if message.message_type == MessageType.STATIC_LOCATION.value:
        return "Static location"
    if message.message_type == MessageType.LIVE_LOCATION.value:
        return "Live location started"
    return "New message"


def _notifications_for_devices(
    *,
    devices,
    title: str | None,
    body: str | None,
    data: dict[str, str],
) -> list[PushNotification]:
    return [
        PushNotification(
            device_id=str(device.id),
            push_token=device.push_token,
            title=title,
            body=body,
            data=data,
        )
        for device in _devices_with_push_token(devices)
    ]


def _devices_with_push_token(devices) -> list[Device]:
    return [
        device
        for device in devices
        if device.push_token is not None and device.push_token.strip()
    ]


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


def _ban_number(ban: Ban) -> int:
    return (
        Ban.select()
        .where(
            (Ban.observer_device == ban.observer_device_id)
            & (Ban.started_at <= ban.started_at)
        )
        .count()
    )


def _datetime_data_value(value: datetime) -> str:
    return value.isoformat()


def _optional_datetime_data_value(value: datetime | None) -> str:
    return value.isoformat() if value is not None else ""


def _optional_uuid_data_value(value: UUID | None) -> str:
    return str(value) if value is not None else ""


def _as_utc_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=_local_timezone()).astimezone(UTC)
    return value.astimezone(UTC)


def _local_timezone():
    return datetime.now().astimezone().tzinfo


def _get_fcm_access_token(service_account_file: str) -> str:
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    credentials_path = Path(service_account_file)
    credentials = service_account.Credentials.from_service_account_file(
        credentials_path,
        scopes=[FCM_SCOPE],
    )
    credentials.refresh(Request())
    return credentials.token
