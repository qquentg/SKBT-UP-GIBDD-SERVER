from datetime import datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, Field


class MessageType(StrEnum):
    TEXT = "TEXT"
    MEDIA = "MEDIA"
    STATIC_LOCATION = "STATIC_LOCATION"


class MessageCreateRequest(BaseModel):
    message_type: MessageType
    text: Annotated[str | None, Field(max_length=4096)] = None
    observer_device_id: UUID | None = None


class StaticLocationCreateRequest(BaseModel):
    observer_device_id: UUID | None = None
    latitude: Annotated[float, Field(ge=-90, le=90)]
    longitude: Annotated[float, Field(ge=-180, le=180)]


class MediaCreateRequest(BaseModel):
    observer_device_id: UUID | None = None
    storage_key: Annotated[str, Field(min_length=1, max_length=512)]
    mime_type: Annotated[str, Field(min_length=1, max_length=128)]


class StaticLocationResponse(BaseModel):
    latitude: float
    longitude: float


class MediaResponse(BaseModel):
    storage_key: str
    mime_type: str
    last_viewed_at: datetime | None


class MessageResponse(BaseModel):
    message_id: UUID
    observer_device_id: UUID
    sender_device_id: UUID
    message_type: MessageType
    text: str | None
    static_location: StaticLocationResponse | None = None
    media: MediaResponse | None = None
    created_at: datetime
    delivered_at: datetime | None


class ChatResponse(BaseModel):
    observer_device_id: UUID
    last_message_id: UUID
    last_message_type: MessageType
    last_text: str | None
    last_static_location: StaticLocationResponse | None = None
    last_media: MediaResponse | None = None
    last_created_at: datetime
    last_delivered_at: datetime | None


class ChatsResponse(BaseModel):
    chats: list[ChatResponse]


class ChatMessagesResponse(BaseModel):
    messages: list[MessageResponse]
