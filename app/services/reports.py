from io import BytesIO
from copy import copy

from fastapi import HTTPException, status
from openpyxl import Workbook

from app.models.ban import Ban
from app.models.device import Device
from app.models.live_location_session import LiveLocationSession
from app.models.media import Media
from app.models.message import Message
from app.models.role_event import RoleEvent
from app.models.static_location import StaticLocation
from app.schemas.device import DeviceRole
from app.schemas.messages import MessageType
from app.services.bans import ban_number, is_ban_active


def require_report_access(actor: Device) -> None:
    if actor.current_role != DeviceRole.CHIEF.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Reports are allowed only for CHIEF",
        )


def generate_excel_report() -> bytes:
    workbook = Workbook()
    _fill_bans_sheet(workbook.active)
    _fill_roles_sheet(workbook.create_sheet("Roles"))
    _fill_messages_sheet(workbook.create_sheet("Messages"))

    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def _fill_bans_sheet(sheet) -> None:
    sheet.title = "Bans"
    _append_header(
        sheet,
        [
            "ban_id",
            "observer_device_id",
            "issued_by_device_id",
            "started_at",
            "ends_at",
            "ban_number",
            "is_active",
        ],
    )
    for ban in Ban.select().order_by(Ban.started_at.asc(), Ban.id.asc()):
        sheet.append(
            [
                str(ban.id),
                str(ban.observer_device_id),
                str(ban.issued_by_device_id),
                _datetime_value(ban.started_at),
                _datetime_value(ban.ends_at),
                ban_number(ban),
                is_ban_active(ban),
            ]
        )


def _fill_roles_sheet(sheet) -> None:
    _append_header(
        sheet,
        [
            "event_id",
            "actor_device_id",
            "target_device_id",
            "action",
            "role",
            "created_at",
        ],
    )
    for event in RoleEvent.select().order_by(RoleEvent.created_at.asc(), RoleEvent.id.asc()):
        sheet.append(
            [
                str(event.id),
                str(event.actor_device_id) if event.actor_device_id is not None else None,
                str(event.target_device_id),
                event.action,
                event.role,
                _datetime_value(event.created_at),
            ]
        )


def _fill_messages_sheet(sheet) -> None:
    _append_header(
        sheet,
        [
            "message_id",
            "observer_device_id",
            "sender_device_id",
            "message_type",
            "text",
            "created_at",
            "delivered_at",
            "media_storage_key",
            "media_mime_type",
            "static_latitude",
            "static_longitude",
            "live_ends_at",
        ],
    )
    for message in Message.select().order_by(Message.created_at.asc(), Message.id.asc()):
        media = _media_for_message(message)
        static_location = _static_location_for_message(message)
        live_location = _live_location_for_message(message)
        sheet.append(
            [
                str(message.id),
                str(message.observer_device_id),
                str(message.sender_device_id),
                message.message_type,
                message.text,
                _datetime_value(message.created_at),
                _datetime_value(message.delivered_at),
                media.storage_key if media is not None else None,
                media.mime_type if media is not None else None,
                static_location.latitude if static_location is not None else None,
                static_location.longitude if static_location is not None else None,
                _datetime_value(live_location.ends_at)
                if live_location is not None
                else None,
            ]
        )


def _append_header(sheet, values: list[str]) -> None:
    sheet.append(values)
    for cell in sheet[1]:
        font = copy(cell.font)
        font.bold = True
        cell.font = font


def _media_for_message(message: Message) -> Media | None:
    if message.message_type != MessageType.MEDIA.value:
        return None
    return Media.get_or_none(Media.message == message.id)


def _static_location_for_message(message: Message) -> StaticLocation | None:
    if message.message_type != MessageType.STATIC_LOCATION.value:
        return None
    return StaticLocation.get_or_none(StaticLocation.message == message.id)


def _live_location_for_message(message: Message) -> LiveLocationSession | None:
    if message.message_type != MessageType.LIVE_LOCATION.value:
        return None
    return LiveLocationSession.get_or_none(LiveLocationSession.message == message.id)


def _datetime_value(value):
    return value.isoformat() if value is not None else None
