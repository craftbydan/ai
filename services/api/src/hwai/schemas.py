"""Pydantic API schemas."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from hwai.safety.rules import OWN_HAND_STATEMENT


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
    own_hand_confirmed_at: datetime | None = None
    own_hand_statement: str = OWN_HAND_STATEMENT


class HandOut(BaseModel):
    id: str | None
    status: str
    status_reason: str | None = None
    status_message: str | None = None
    sample_count: int = 0
    own_hand_confirmed_at: datetime | None
    own_hand_statement: str = OWN_HAND_STATEMENT
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


class Placement(BaseModel):
    """What to write where. Placements come from the request body (later, from the agent)."""

    region_id: str = Field(min_length=1, max_length=64)
    text: str = Field(max_length=2000)
    align: Literal["left", "center", "right"] = "left"
    size_scale: float = Field(default=1.0, ge=0.5, le=1.5)
    slant_deg: float = Field(default=0.0, ge=-15, le=15)
    jitter: float = Field(default=0.5, ge=0, le=1)
    seed: int = 0


class RenderRequest(BaseModel):
    placements: list[Placement] = Field(max_length=100)


class FitItem(BaseModel):
    region_id: str
    fit: bool
    cut_words: int
    size_px: int
    shrink: float


class FitReport(BaseModel):
    all_fit: bool
    placements: list[FitItem]


class RenderOut(BaseModel):
    version: int
    preview_url: str
    fit_report: FitReport
