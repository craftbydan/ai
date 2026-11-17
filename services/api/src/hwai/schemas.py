"""Pydantic API schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    renderer: str
    ocr: str


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody


class HandDocumentOut(BaseModel):
    id: str
    page_count: int
    status: str
    created_at: datetime


class HandOut(BaseModel):
    id: str | None
    status: str
    own_hand_confirmed_at: datetime | None
    documents: list[HandDocumentOut]


class ChatFileOut(BaseModel):
    id: str
    kind: str
    page_count: int
    safety_status: str
    safety_reason: str | None
    created_at: datetime


class MessageOut(BaseModel):
    id: str
    role: str
    content_json: Any
    created_at: datetime


class ChatOut(BaseModel):
    id: str
    hand_id: str | None
    title: str
    created_at: datetime


class ChatDetail(ChatOut):
    files: list[ChatFileOut]
    messages: list[MessageOut]
