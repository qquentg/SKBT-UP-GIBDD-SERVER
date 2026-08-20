from datetime import datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field


class MessageType(StrEnum):
    TEXT = "TEXT"


class MessageCreateRequest(BaseModel):
    message_type: MessageType
    text: Annotated[str | None, Field(max_length=4096)] = None
    observer_device_id: UUID | None = None


class MessageResponse(BaseModel):
    message_id: UUID
    observer_device_id: UUID
    sender_device_id: UUID
    message_type: MessageType
    text: str | None
    created_at: datetime
    delivered_at: datetime | None


class ChatResponse(BaseModel):
    observer_device_id: UUID
    last_message_id: UUID
    last_message_type: MessageType
    last_text: str | None
    last_created_at: datetime
    last_delivered_at: datetime | None


class ChatsResponse(BaseModel):
    chats: list[ChatResponse]


class ChatMessagesResponse(BaseModel):
    messages: list[MessageResponse]
