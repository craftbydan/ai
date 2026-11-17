"""ORM models (payments arrive in Prompt 11)."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from hwai.db import Base


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(UTC)


def _id() -> Mapped[str]:
    return mapped_column(String(32), primary_key=True, default=new_id)


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=utcnow)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = _id()
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), default=None)
    created_at: Mapped[datetime] = _created()


class Hand(Base):
    __tablename__ = "hands"
    id: Mapped[str] = _id()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="empty")  # empty|learning|ready|failed
    own_hand_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    status_reason: Mapped[str | None] = mapped_column(String(64), default=None)
    created_at: Mapped[datetime] = _created()


class HandDocument(Base):
    __tablename__ = "hand_documents"
    id: Mapped[str] = _id()
    hand_id: Mapped[str] = mapped_column(ForeignKey("hands.id"), index=True)
    file_path: Mapped[str] = mapped_column(String(512))
    page_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="uploaded")
    created_at: Mapped[datetime] = _created()


class WordSample(Base):
    __tablename__ = "word_samples"
    id: Mapped[str] = _id()
    hand_id: Mapped[str] = mapped_column(ForeignKey("hands.id"), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("hand_documents.id"))
    text: Mapped[str] = mapped_column(String(128))
    crop_path: Mapped[str] = mapped_column(String(512))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    ocr_confidence: Mapped[float | None] = mapped_column(Float, default=None)
    quality_score: Mapped[float | None] = mapped_column(Float, default=None)


class Chat(Base):
    __tablename__ = "chats"
    id: Mapped[str] = _id()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    hand_id: Mapped[str | None] = mapped_column(ForeignKey("hands.id"), default=None)
    title: Mapped[str] = mapped_column(String(255), default="New chat")
    created_at: Mapped[datetime] = _created()


class ChatFile(Base):
    __tablename__ = "chat_files"
    id: Mapped[str] = _id()
    chat_id: Mapped[str] = mapped_column(ForeignKey("chats.id"), index=True)
    file_path: Mapped[str] = mapped_column(String(512))
    kind: Mapped[str] = mapped_column(String(8))  # pdf|image
    page_count: Mapped[int] = mapped_column(Integer)
    analysis_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    safety_status: Mapped[str] = mapped_column(String(8), default="ok")  # ok|refused
    safety_reason: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = _created()


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = _id()
    chat_id: Mapped[str] = mapped_column(ForeignKey("chats.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user|assistant|tool
    content_json: Mapped[Any] = mapped_column(JSON)
    created_at: Mapped[datetime] = _created()


class Render(Base):
    __tablename__ = "renders"
    id: Mapped[str] = _id()
    chat_id: Mapped[str] = mapped_column(ForeignKey("chats.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    placements_json: Mapped[Any] = mapped_column(JSON)
    preview_path: Mapped[str | None] = mapped_column(String(512), default=None)
    created_at: Mapped[datetime] = _created()


class Export(Base):
    __tablename__ = "exports"
    id: Mapped[str] = _id()
    render_id: Mapped[str] = mapped_column(ForeignKey("renders.id"), index=True)
    format: Mapped[str] = mapped_column(String(8))  # pdf|png
    file_path: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = _created()
