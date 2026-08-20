from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query

from app.api.dependencies import get_authorized_device, require_employee_client
from app.models.device import Device
from app.models.message import Message
from app.schemas.device import ClientApp
from app.schemas.messages import (
    ChatMessagesResponse,
    ChatResponse,
    ChatsResponse,
    MessageCreateRequest,
    MessageResponse,
)
from app.services.messages import (
    create_text_message,
    list_chat_messages,
    list_chats,
    mark_message_delivered,
)

router = APIRouter(tags=["messages"])


@router.post("/api/v1/messages", response_model=MessageResponse)
def post_message(
    payload: MessageCreateRequest,
    client_app: ClientApp = Header(alias="X-Client-App"),
    sender: Device = Depends(get_authorized_device),
) -> MessageResponse:
    message = create_text_message(
        sender=sender,
        client_app=client_app,
        text=payload.text,
        observer_device_id=payload.observer_device_id,
    )
    return _message_response(message)


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
    return MessageResponse(
        message_id=message.id,
        observer_device_id=message.observer_device_id,
        sender_device_id=message.sender_device_id,
        message_type=message.message_type,
        text=message.text,
        created_at=message.created_at,
        delivered_at=message.delivered_at,
    )


def _chat_response(message: Message) -> ChatResponse:
    return ChatResponse(
        observer_device_id=message.observer_device_id,
        last_message_id=message.id,
        last_message_type=message.message_type,
        last_text=message.text,
        last_created_at=message.created_at,
        last_delivered_at=message.delivered_at,
    )
