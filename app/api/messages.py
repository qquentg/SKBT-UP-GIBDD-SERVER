from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse

from app.api.dependencies import get_authorized_device, require_employee_client
from app.models.ban import Ban
from app.models.device import Device
from app.models.message import Message
from app.schemas.bans import BanResponse
from app.schemas.device import ClientApp
from app.schemas.messages import (
    ChatMessagesResponse,
    ChatResponse,
    ChatsResponse,
    LiveLocationPointCreateRequest,
    LiveLocationResponse,
    LiveLocationStartRequest,
    LocationPointResponse,
    LocationPointsResponse,
    MediaCreateRequest,
    MediaResponse,
    MessageCreateRequest,
    MessageResponse,
    MessageType,
    StaticLocationCreateRequest,
    StaticLocationResponse,
)
from app.services.messages import (
    MEDIA_UPLOAD_MAX_BYTES,
    add_live_location_point,
    create_live_location_message,
    create_media_message,
    create_static_location_message,
    create_text_message,
    create_uploaded_media_message,
    get_live_location_session_for_message,
    get_media_file_for_message,
    get_media_for_message,
    get_static_location_for_message,
    list_chat_messages,
    list_chats,
    list_live_location_points,
    mark_message_delivered,
    stop_live_location,
)
from app.services.bans import ban_number, get_active_ban, is_ban_active

router = APIRouter(tags=["messages"])


@router.post("/api/v1/messages", response_model=MessageResponse)
def post_message(
    payload: MessageCreateRequest,
    client_app: ClientApp = Header(alias="X-Client-App"),
    sender: Device = Depends(get_authorized_device),
) -> MessageResponse:
    if payload.message_type != MessageType.TEXT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use dedicated endpoint for this message_type",
        )

    message = create_text_message(
        sender=sender,
        client_app=client_app,
        text=payload.text,
        observer_device_id=payload.observer_device_id,
    )
    return _message_response(message)


@router.post("/api/v1/messages/static-location", response_model=MessageResponse)
def post_static_location_message(
    payload: StaticLocationCreateRequest,
    client_app: ClientApp = Header(alias="X-Client-App"),
    sender: Device = Depends(get_authorized_device),
) -> MessageResponse:
    message = create_static_location_message(
        sender=sender,
        client_app=client_app,
        latitude=payload.latitude,
        longitude=payload.longitude,
        observer_device_id=payload.observer_device_id,
    )
    return _message_response(message)


@router.post("/api/v1/messages/media", response_model=MessageResponse)
def post_media_message(
    payload: MediaCreateRequest,
    client_app: ClientApp = Header(alias="X-Client-App"),
    sender: Device = Depends(get_authorized_device),
) -> MessageResponse:
    message = create_media_message(
        sender=sender,
        client_app=client_app,
        storage_key=payload.storage_key,
        mime_type=payload.mime_type,
        observer_device_id=payload.observer_device_id,
    )
    return _message_response(message)


@router.post("/api/v1/messages/media/upload", response_model=MessageResponse)
async def post_media_upload(
    file: UploadFile = File(...),
    observer_device_id: Annotated[UUID | None, Form()] = None,
    client_app: ClientApp = Header(alias="X-Client-App"),
    sender: Device = Depends(get_authorized_device),
) -> MessageResponse:
    content = await file.read(MEDIA_UPLOAD_MAX_BYTES + 1)
    message = create_uploaded_media_message(
        sender=sender,
        client_app=client_app,
        filename=file.filename,
        mime_type=file.content_type,
        content=content,
        observer_device_id=observer_device_id,
    )
    return _message_response(message)


@router.post("/api/v1/messages/live-location/start", response_model=MessageResponse)
def post_live_location_start(
    payload: LiveLocationStartRequest,
    client_app: ClientApp = Header(alias="X-Client-App"),
    sender: Device = Depends(get_authorized_device),
) -> MessageResponse:
    message = create_live_location_message(
        sender=sender,
        client_app=client_app,
        observer_device_id=payload.observer_device_id,
    )
    return _message_response(message)


@router.post(
    "/api/v1/messages/{message_id}/live-location/points",
    response_model=LocationPointResponse,
)
def post_live_location_point(
    message_id: UUID,
    payload: LiveLocationPointCreateRequest,
    client_app: ClientApp = Header(alias="X-Client-App"),
    actor: Device = Depends(get_authorized_device),
) -> LocationPointResponse:
    point = add_live_location_point(
        actor=actor,
        client_app=client_app,
        message_id=message_id,
        latitude=payload.latitude,
        longitude=payload.longitude,
    )
    return _location_point_response(point)


@router.post("/api/v1/messages/{message_id}/live-location/stop", response_model=MessageResponse)
def post_live_location_stop(
    message_id: UUID,
    client_app: ClientApp = Header(alias="X-Client-App"),
    actor: Device = Depends(get_authorized_device),
) -> MessageResponse:
    message = stop_live_location(
        actor=actor,
        client_app=client_app,
        message_id=message_id,
    )
    return _message_response(message)


@router.get(
    "/api/v1/messages/{message_id}/live-location/points",
    response_model=LocationPointsResponse,
)
def get_live_location_points(
    message_id: UUID,
    client_app: ClientApp = Header(alias="X-Client-App"),
    actor: Device = Depends(get_authorized_device),
    after_recorded_at: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=300)] = 100,
) -> LocationPointsResponse:
    points = list_live_location_points(
        actor=actor,
        client_app=client_app,
        message_id=message_id,
        after_recorded_at=after_recorded_at,
        limit=limit,
    )
    return LocationPointsResponse(
        points=[_location_point_response(point) for point in points]
    )


@router.get("/api/v1/messages/{message_id}/media")
def get_media_file(
    message_id: UUID,
    client_app: ClientApp = Header(alias="X-Client-App"),
    actor: Device = Depends(get_authorized_device),
) -> FileResponse:
    file_path, media = get_media_file_for_message(
        actor=actor,
        client_app=client_app,
        message_id=message_id,
    )
    return FileResponse(
        path=file_path,
        media_type=media.mime_type,
        filename=file_path.name,
    )


@router.get("/api/v1/chats", response_model=ChatsResponse)
def get_chats(
    _: None = Depends(require_employee_client),
    actor: Device = Depends(get_authorized_device),
) -> ChatsResponse:
    chats = [_chat_response(message) for message in list_chats(actor)]
    return ChatsResponse(chats=chats)


@router.get(
    "/api/v1/chats/{observer_device_id}/messages",
    response_model=ChatMessagesResponse,
)
def get_chat_messages(
    observer_device_id: UUID,
    client_app: ClientApp = Header(alias="X-Client-App"),
    actor: Device = Depends(get_authorized_device),
    after_message_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ChatMessagesResponse:
    messages = list_chat_messages(
        actor=actor,
        client_app=client_app,
        observer_device_id=observer_device_id,
        after_message_id=after_message_id,
        limit=limit,
    )
    return ChatMessagesResponse(messages=[_message_response(message) for message in messages])


@router.patch("/api/v1/messages/{message_id}/delivered", response_model=MessageResponse)
def patch_message_delivered(
    message_id: UUID,
    client_app: ClientApp = Header(alias="X-Client-App"),
    actor: Device = Depends(get_authorized_device),
) -> MessageResponse:
    message = mark_message_delivered(
        actor=actor,
        client_app=client_app,
        message_id=message_id,
    )
    return _message_response(message)


def _message_response(message: Message) -> MessageResponse:
    static_location = get_static_location_for_message(message)
    media = get_media_for_message(message)
    live_location = get_live_location_session_for_message(message)
    return MessageResponse(
        message_id=message.id,
        observer_device_id=message.observer_device_id,
        sender_device_id=message.sender_device_id,
        message_type=message.message_type,
        text=message.text,
        static_location=(
            StaticLocationResponse(
                latitude=static_location.latitude,
                longitude=static_location.longitude,
            )
            if static_location is not None
            else None
        ),
        media=(
            MediaResponse(
                storage_key=media.storage_key,
                mime_type=media.mime_type,
                last_viewed_at=media.last_viewed_at,
            )
            if media is not None
            else None
        ),
        live_location=(
            LiveLocationResponse(ends_at=live_location.ends_at)
            if live_location is not None
            else None
        ),
        created_at=message.created_at,
        delivered_at=message.delivered_at,
    )


def _chat_response(message: Message) -> ChatResponse:
    message_response = _message_response(message)
    active_ban = get_active_ban(message.observer_device_id)
    return ChatResponse(
        observer_device_id=message_response.observer_device_id,
        last_message_id=message_response.message_id,
        last_message_type=message_response.message_type,
        last_text=message_response.text,
        last_static_location=message_response.static_location,
        last_media=message_response.media,
        last_live_location=message_response.live_location,
        last_created_at=message_response.created_at,
        last_delivered_at=message_response.delivered_at,
        active_ban=_ban_response(active_ban) if active_ban is not None else None,
    )


def _ban_response(ban: Ban) -> BanResponse:
    return BanResponse(
        ban_id=ban.id,
        observer_device_id=ban.observer_device_id,
        issued_by_device_id=ban.issued_by_device_id,
        started_at=ban.started_at,
        ends_at=ban.ends_at,
        ban_number=ban_number(ban),
        is_active=is_ban_active(ban),
    )


def _location_point_response(point) -> LocationPointResponse:
    return LocationPointResponse(
        recorded_at=point.recorded_at,
        latitude=point.latitude,
        longitude=point.longitude,
    )
