from datetime import UTC

from app.models.live_location_session import LiveLocationSession
from app.models.location_point import LocationPoint
from app.models.media import Media
from app.models.message import Message
from app.models.static_location import StaticLocation
from app.schemas.messages import MessageType


def message_payload(message: Message) -> dict:
    static_location = _static_location_for_message(message)
    media = _media_for_message(message)
    live_location = _live_location_for_message(message)
    return {
        "message_id": str(message.id),
        "observer_device_id": str(message.observer_device_id),
        "sender_device_id": str(message.sender_device_id),
        "message_type": message.message_type,
        "text": message.text,
        "static_location": (
            {
                "latitude": static_location.latitude,
                "longitude": static_location.longitude,
            }
            if static_location is not None
            else None
        ),
        "media": (
            {
                "storage_key": media.storage_key,
                "mime_type": media.mime_type,
                "last_viewed_at": _datetime_value(media.last_viewed_at),
            }
            if media is not None
            else None
        ),
        "live_location": (
            {"ends_at": _datetime_value(live_location.ends_at)}
            if live_location is not None
            else None
        ),
        "created_at": _datetime_value(message.created_at),
        "delivered_at": _datetime_value(message.delivered_at),
    }


def location_point_payload(point: LocationPoint) -> dict:
    return {
        "recorded_at": _datetime_value(point.recorded_at),
        "latitude": point.latitude,
        "longitude": point.longitude,
    }


def _static_location_for_message(message: Message) -> StaticLocation | None:
    if message.message_type != MessageType.STATIC_LOCATION.value:
        return None
    return StaticLocation.get_or_none(StaticLocation.message == message.id)


def _media_for_message(message: Message) -> Media | None:
    if message.message_type != MessageType.MEDIA.value:
        return None
    return Media.get_or_none(Media.message == message.id)


def _live_location_for_message(message: Message) -> LiveLocationSession | None:
    if message.message_type != MessageType.LIVE_LOCATION.value:
        return None
    return LiveLocationSession.get_or_none(LiveLocationSession.message == message.id)


def _datetime_value(value):
    if value is None:
        return None
    if value.tzinfo is not None and value.astimezone(UTC).utcoffset().total_seconds() == 0:
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return value.isoformat()
