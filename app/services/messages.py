from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID
from uuid import uuid4

from fastapi import HTTPException, status

from app.core.config import get_settings
from app.db.database import database_proxy
from app.models.device import Device, utc_now
from app.models.live_location_session import LiveLocationSession
from app.models.location_point import LocationPoint
from app.models.media import Media
from app.models.message import Message
from app.models.static_location import StaticLocation
from app.schemas.device import ClientApp, DeviceRole
from app.schemas.messages import MessageType
from app.services.bans import get_active_ban

EMPLOYEE_CHAT_ROLES = {"INSPECTOR", "ADMIN", "CHIEF"}
LIVE_LOCATION_DURATION = timedelta(minutes=15)
MEDIA_TTL = timedelta(days=7)
MEDIA_PHOTO_MAX_BYTES = 10 * 1024 * 1024
MEDIA_VIDEO_GIF_MAX_BYTES = 100 * 1024 * 1024
MEDIA_UPLOAD_MAX_BYTES = MEDIA_VIDEO_GIF_MAX_BYTES
PHOTO_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
GIF_MIME_TYPES = {"image/gif"}
VIDEO_MIME_TYPES = {"video/mp4"}
SUPPORTED_MEDIA_MIME_TYPES = PHOTO_MIME_TYPES | GIF_MIME_TYPES | VIDEO_MIME_TYPES


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
    storage_key = storage_key.strip()
    if not storage_key:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="storage_key cannot be empty",
        )
    normalized_mime_type = _normalize_media_mime_type(mime_type)
    _validate_stored_media_file(
        storage_key=storage_key,
        mime_type=normalized_mime_type,
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
            storage_key=storage_key,
            mime_type=normalized_mime_type,
        )
        Device.update(last_activity_at=utc_now()).where(Device.id == sender.id).execute()

    return message


def create_uploaded_media_message(
    *,
    sender: Device,
    client_app: ClientApp,
    filename: str | None,
    mime_type: str | None,
    content: bytes,
    observer_device_id: UUID | None,
) -> Message:
    cleanup_expired_media_files()

    if not content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Media file cannot be empty",
        )

    normalized_mime_type = _normalize_media_mime_type(mime_type)
    _validate_media_size(
        mime_type=normalized_mime_type,
        size_bytes=len(content),
    )

    storage_key = _new_media_storage_key(filename)
    file_path = _media_file_path(storage_key)

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(content)
        return create_media_message(
            sender=sender,
            client_app=client_app,
            storage_key=storage_key,
            mime_type=normalized_mime_type,
            observer_device_id=observer_device_id,
        )
    except Exception:
        if file_path.exists():
            file_path.unlink()
        raise


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
    if client_app == ClientApp.EYEWITNESS:
        _require_observer_not_banned(actor.id)
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
    if _as_utc_aware(session.ends_at) <= now:
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
    if _as_utc_aware(session.ends_at) > now:
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
            if (
                actor.current_role == DeviceRole.INSPECTOR.value
                and get_active_ban(message.observer_device_id) is not None
            ):
                continue
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


def cleanup_expired_media_files() -> int:
    deleted_count = 0
    now = utc_now()

    for media in Media.select():
        message = Message.get_or_none(Message.id == media.message_id)
        if message is None:
            continue
        if _media_expires_at(message=message, media=media) <= now:
            deleted_count += int(_delete_media_file_if_exists(media.storage_key))

    return deleted_count


def get_media_file_for_message(
    *,
    actor: Device,
    client_app: ClientApp,
    message_id: UUID,
) -> tuple[Path, Media]:
    message = get_message_or_404(message_id)
    if message.message_type != MessageType.MEDIA.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message is not media",
        )

    _require_chat_participant(
        actor=actor,
        client_app=client_app,
        observer_device_id=message.observer_device_id,
    )

    media = get_media_for_message(message)
    if media is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media metadata not found",
        )

    if _media_expires_at(message=message, media=media) <= utc_now():
        _delete_media_file_if_exists(media.storage_key)
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Media file has expired",
        )

    file_path = _media_file_path(media.storage_key)
    if not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media file not found",
        )

    Media.update(last_viewed_at=utc_now()).where(Media.message == message.id).execute()
    media = Media.get_by_id(message.id)
    return file_path, media


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
        _require_observer_not_banned(sender.id)
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


def _require_observer_not_banned(observer_device_id: UUID) -> None:
    if get_active_ban(observer_device_id) is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Observer device is banned",
        )


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


def _as_utc_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=_local_timezone()).astimezone(UTC)
    return value.astimezone(UTC)


def _local_timezone():
    return datetime.now().astimezone().tzinfo


def _new_media_storage_key(filename: str | None) -> str:
    now = utc_now()
    suffix = Path(filename or "").suffix.lower()
    if len(suffix) > 16 or not suffix.startswith(".") or not suffix[1:].isalnum():
        suffix = ""
    return f"{now:%Y/%m}/{uuid4().hex}{suffix}"


def _normalize_media_mime_type(mime_type: str | None) -> str:
    normalized = (mime_type or "").split(";", maxsplit=1)[0].strip().lower()
    if normalized not in SUPPORTED_MEDIA_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported media mime_type",
        )
    return normalized


def _validate_stored_media_file(*, storage_key: str, mime_type: str) -> None:
    file_path = _media_file_path(storage_key)
    if not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media file not found",
        )
    _validate_media_size(
        mime_type=mime_type,
        size_bytes=file_path.stat().st_size,
    )


def _validate_media_size(*, mime_type: str, size_bytes: int) -> None:
    max_bytes = (
        MEDIA_VIDEO_GIF_MAX_BYTES
        if mime_type in GIF_MIME_TYPES | VIDEO_MIME_TYPES
        else MEDIA_PHOTO_MAX_BYTES
    )
    if size_bytes > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Media file is too large",
        )


def _media_expires_at(*, message: Message, media: Media) -> datetime:
    base = media.last_viewed_at if media.last_viewed_at is not None else message.created_at
    return _as_utc_aware(base) + MEDIA_TTL


def _delete_media_file_if_exists(storage_key: str) -> bool:
    file_path = _media_file_path(storage_key)
    if file_path.is_file():
        file_path.unlink()
        return True
    return False


def _media_file_path(storage_key: str) -> Path:
    root = Path(get_settings().media_storage_dir).resolve()
    file_path = (root / storage_key).resolve()
    try:
        file_path.relative_to(root)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid media storage_key",
        ) from exc
    return file_path
