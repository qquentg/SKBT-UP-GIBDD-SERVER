from datetime import datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, status

from app.db.database import database_proxy
from app.models.device import Device, utc_now
from app.models.live_location_session import LiveLocationSession
from app.models.location_point import LocationPoint
from app.models.media import Media
from app.models.message import Message
from app.models.static_location import StaticLocation
from app.schemas.device import ClientApp
from app.schemas.messages import MessageType

EMPLOYEE_CHAT_ROLES = {"INSPECTOR", "ADMIN", "CHIEF"}
LIVE_LOCATION_DURATION = timedelta(minutes=15)


def require_employee_chat_access(device: Device) -> None:
    if device.current_role not in EMPLOYEE_CHAT_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chat access is not allowed for this device",
        )


def create_text_message(
    *,
    sender: Device,
    client_app: ClientApp,
    text: str | None,
    observer_device_id: UUID | None,
) -> Message:
    if text is None or not text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Text message cannot be empty",
        )

    observer = _resolve_observer_device(
        sender=sender,
        client_app=client_app,
        observer_device_id=observer_device_id,
    )

    with database_proxy.atomic():
        message = Message.create(
            observer_device=observer.id,
            sender_device=sender.id,
            message_type=MessageType.TEXT.value,
            text=text.strip(),
        )
        Device.update(last_activity_at=utc_now()).where(Device.id == sender.id).execute()

    return message


def create_static_location_message(
    *,
    sender: Device,
    client_app: ClientApp,
    latitude: float,
    longitude: float,
    observer_device_id: UUID | None,
) -> Message:
    observer = _resolve_observer_device(
        sender=sender,
        client_app=client_app,
        observer_device_id=observer_device_id,
    )

    with database_proxy.atomic():
        message = Message.create(
            observer_device=observer.id,
            sender_device=sender.id,
            message_type=MessageType.STATIC_LOCATION.value,
        )
        StaticLocation.create(
            message=message.id,
            latitude=latitude,
            longitude=longitude,
        )
        Device.update(last_activity_at=utc_now()).where(Device.id == sender.id).execute()

    return message


def create_media_message(
    *,
    sender: Device,
    client_app: ClientApp,
    storage_key: str,
    mime_type: str,
    observer_device_id: UUID | None,
) -> Message:
    if not storage_key.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="storage_key cannot be empty",
        )
    if not mime_type.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="mime_type cannot be empty",
        )

    observer = _resolve_observer_device(
        sender=sender,
        client_app=client_app,
        observer_device_id=observer_device_id,
    )

    with database_proxy.atomic():
        message = Message.create(
            observer_device=observer.id,
            sender_device=sender.id,
            message_type=MessageType.MEDIA.value,
        )
        Media.create(
            message=message.id,
            storage_key=storage_key.strip(),
            mime_type=mime_type.strip(),
        )
        Device.update(last_activity_at=utc_now()).where(Device.id == sender.id).execute()

    return message


def create_live_location_message(
    *,
    sender: Device,
    client_app: ClientApp,
    observer_device_id: UUID | None,
) -> Message:
    observer = _resolve_observer_device(
        sender=sender,
        client_app=client_app,
        observer_device_id=observer_device_id,
    )

    with database_proxy.atomic():
        now = utc_now()
        message = Message.create(
            observer_device=observer.id,
            sender_device=sender.id,
            message_type=MessageType.LIVE_LOCATION.value,
            created_at=now,
        )
        LiveLocationSession.create(
            message=message.id,
            ends_at=now + LIVE_LOCATION_DURATION,
        )
        Device.update(last_activity_at=now).where(Device.id == sender.id).execute()

    return message


def add_live_location_point(
    *,
    actor: Device,
    client_app: ClientApp,
    message_id: UUID,
    latitude: float,
    longitude: float,
) -> LocationPoint:
    message = _get_live_location_message_or_404(message_id)
    _require_live_location_sender(actor=actor, message=message)
    _require_chat_participant(
        actor=actor,
        client_app=client_app,
        observer_device_id=message.observer_device_id,
    )

    session = get_live_location_session_for_message(message)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Live location session not found",
        )

    now = utc_now()
    if session.ends_at <= now:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Live location session has ended",
        )

    with database_proxy.atomic():
        point = LocationPoint.create(
            message=message.id,
            recorded_at=now,
            latitude=latitude,
            longitude=longitude,
        )
        Device.update(last_activity_at=now).where(Device.id == actor.id).execute()

    return point


def stop_live_location(
    *,
    actor: Device,
    client_app: ClientApp,
    message_id: UUID,
) -> Message:
    message = _get_live_location_message_or_404(message_id)
    _require_live_location_sender(actor=actor, message=message)
    _require_chat_participant(
        actor=actor,
        client_app=client_app,
        observer_device_id=message.observer_device_id,
    )

    session = get_live_location_session_for_message(message)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Live location session not found",
        )

    now = utc_now()
    if session.ends_at > now:
        LiveLocationSession.update(ends_at=now).where(
            LiveLocationSession.message == message.id
        ).execute()

    return Message.get_by_id(message.id)


def list_live_location_points(
    *,
    actor: Device,
    client_app: ClientApp,
    message_id: UUID,
    after_recorded_at: datetime | None = None,
    limit: int = 100,
) -> list[LocationPoint]:
    message = _get_live_location_message_or_404(message_id)
    _require_chat_participant(
        actor=actor,
        client_app=client_app,
        observer_device_id=message.observer_device_id,
    )

    query = LocationPoint.select().where(LocationPoint.message == message.id)
    if after_recorded_at is not None:
        query = query.where(LocationPoint.recorded_at > after_recorded_at)

    return list(query.order_by(LocationPoint.recorded_at.asc()).limit(limit))


def list_chats(actor: Device) -> list[Message]:
    require_employee_chat_access(actor)
    latest_by_observer: dict[str, Message] = {}

    for message in Message.select().order_by(Message.created_at.desc(), Message.id.desc()):
        observer_id = str(message.observer_device_id)
        if observer_id not in latest_by_observer:
            latest_by_observer[observer_id] = message

    return list(latest_by_observer.values())


def list_chat_messages(
    *,
    actor: Device,
    client_app: ClientApp,
    observer_device_id: UUID,
    after_message_id: UUID | None = None,
    limit: int = 50,
) -> list[Message]:
    _require_chat_participant(
        actor=actor,
        client_app=client_app,
        observer_device_id=observer_device_id,
    )

    query = Message.select().where(Message.observer_device == observer_device_id)
    if after_message_id is not None:
        after_message = get_message_or_404(after_message_id)
        if str(after_message.observer_device_id) != str(observer_device_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="after_message_id belongs to another chat",
            )
        query = query.where(Message.created_at > after_message.created_at)

    return list(query.order_by(Message.created_at.asc(), Message.id.asc()).limit(limit))


def mark_message_delivered(
    *,
    actor: Device,
    client_app: ClientApp,
    message_id: UUID,
) -> Message:
    message = get_message_or_404(message_id)
    _require_chat_participant(
        actor=actor,
        client_app=client_app,
        observer_device_id=message.observer_device_id,
    )

    if message.delivered_at is None:
        Message.update(delivered_at=utc_now()).where(Message.id == message.id).execute()
        message = Message.get_by_id(message.id)

    return message


def get_message_or_404(message_id: UUID) -> Message:
    message = Message.get_or_none(Message.id == message_id)
    if message is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )
    return message


def get_static_location_for_message(message: Message) -> StaticLocation | None:
    if message.message_type != MessageType.STATIC_LOCATION.value:
        return None
    return StaticLocation.get_or_none(StaticLocation.message == message.id)


def get_media_for_message(message: Message) -> Media | None:
    if message.message_type != MessageType.MEDIA.value:
        return None
    return Media.get_or_none(Media.message == message.id)


def get_live_location_session_for_message(
    message: Message,
) -> LiveLocationSession | None:
    if message.message_type != MessageType.LIVE_LOCATION.value:
        return None
    return LiveLocationSession.get_or_none(LiveLocationSession.message == message.id)


def _resolve_observer_device(
    *,
    sender: Device,
    client_app: ClientApp,
    observer_device_id: UUID | None,
) -> Device:
    if client_app == ClientApp.EYEWITNESS:
        if observer_device_id is not None and str(observer_device_id) != str(sender.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Eyewitness can only write to own chat",
            )
        return sender

    require_employee_chat_access(sender)
    if observer_device_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="observer_device_id is required for employee messages",
        )

    observer = Device.get_or_none(Device.id == observer_device_id)
    if observer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Observer device not found",
        )
    return observer


def _require_chat_participant(
    *,
    actor: Device,
    client_app: ClientApp,
    observer_device_id: UUID,
) -> None:
    observer_exists = Device.select(Device.id).where(Device.id == observer_device_id).exists()
    if not observer_exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Observer device not found",
        )

    if client_app == ClientApp.EYEWITNESS:
        if str(actor.id) != str(observer_device_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Eyewitness can only access own chat",
            )
        return

    require_employee_chat_access(actor)


def _get_live_location_message_or_404(message_id: UUID) -> Message:
    message = get_message_or_404(message_id)
    if message.message_type != MessageType.LIVE_LOCATION.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message is not a live location",
        )
    return message


def _require_live_location_sender(*, actor: Device, message: Message) -> None:
    if str(actor.id) != str(message.sender_device_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only live location sender can update this session",
        )
