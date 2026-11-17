import io
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from hwai import storage
from hwai.deps import DbDep, UserDep
from hwai.errors import ApiError
from hwai.llm import get_llm_client
from hwai.models import Chat, ChatFile, Hand, Message, User
from hwai.page.analyze import analyze_pages, load_pages
from hwai.page.regions import Region
from hwai.pdfio import inspect_file
from hwai.routes.hand import get_user_hand
from hwai.routes.uploads import read_upload
from hwai.safety.classify import classify_document
from hwai.safety.rules import message_for
from hwai.safety.signature import flag_signature_regions
from hwai.schemas import ChatDetail, ChatFileOut, ChatOut, MessageOut

router = APIRouter()


def get_owned_chat(db: Session, user: User, chat_id: str) -> Chat:
    """Ownership check used by every chat route: not yours means 404."""
    chat = db.scalar(select(Chat).where(Chat.id == chat_id, Chat.user_id == user.id))
    if chat is None:
        raise ApiError(404, "not_found", "Chat not found.")
    return chat


@router.post("/chats", response_model=ChatOut, status_code=201)
def create_chat(db: DbDep, user: UserDep) -> Chat:
    hand = get_user_hand(db, user)
    if hand is None:
        hand = Hand(user_id=user.id)
        db.add(hand)
        db.flush()
    chat = Chat(user_id=user.id, hand_id=hand.id)
    db.add(chat)
    db.commit()
    return chat


@router.get("/chats/{chat_id}", response_model=ChatDetail)
def read_chat(chat_id: str, db: DbDep, user: UserDep) -> ChatDetail:
    chat = get_owned_chat(db, user, chat_id)
    files = db.scalars(
        select(ChatFile).where(ChatFile.chat_id == chat.id).order_by(ChatFile.created_at)
    ).all()
    messages = db.scalars(
        select(Message).where(Message.chat_id == chat.id).order_by(Message.created_at)
    ).all()
    return ChatDetail(
        **ChatOut.model_validate(chat, from_attributes=True).model_dump(),
        files=[ChatFileOut.model_validate(f, from_attributes=True) for f in files],
        messages=[MessageOut.model_validate(m, from_attributes=True) for m in messages],
    )


@router.post("/chats/{chat_id}/files", response_model=ChatFileOut, status_code=201)
def upload_chat_file(
    chat_id: str,
    file: Annotated[UploadFile, File()],
    db: DbDep,
    user: UserDep,
    client: Annotated[Any, Depends(get_llm_client)],
) -> ChatFile:
    chat = get_owned_chat(db, user, chat_id)
    data = read_upload(file)
    info = inspect_file(data)
    rel = storage.save_file(user.id, "target", data, info.ext)
    chat_file = ChatFile(chat_id=chat.id, file_path=rel, kind=info.kind, page_count=info.page_count)
    try:
        pages = load_pages(storage.absolute_path(rel))
        doc = classify_document(pages, client)
        if doc.kind != "ok":
            reason = doc.kind + (":fallback" if doc.source == "fallback" else "")
            chat_file.safety_status = "refused"
            chat_file.safety_reason = reason
            db.add(chat_file)
            db.commit()
            raise ApiError(422, "document_refused", message_for(reason))
        analysis = analyze_pages(pages)
        for n, pg in enumerate(analysis["pages"], 1):
            boxes = [b[1:] for b in doc.signature_boxes if b[0] == n]
            flagged = flag_signature_regions(
                [Region.model_validate(r) for r in pg["regions"]], pages[n - 1], boxes
            )
            pg["regions"] = [r.model_dump(mode="json") for r in flagged]
        chat_file.analysis_json = analysis
        db.add(chat_file)
        db.commit()
    except ApiError:
        raise
    except Exception:
        db.rollback()
        storage.delete_file(rel)
        raise
    return chat_file


def get_owned_file(db: Session, user: User, chat_id: str, file_id: str) -> ChatFile:
    chat = get_owned_chat(db, user, chat_id)
    chat_file = db.scalar(
        select(ChatFile).where(ChatFile.id == file_id, ChatFile.chat_id == chat.id)
    )
    if chat_file is None:
        raise ApiError(404, "not_found", "File not found.")
    return chat_file


@router.get("/chats/{chat_id}/files/{file_id}/analysis")
def read_file_analysis(chat_id: str, file_id: str, db: DbDep, user: UserDep) -> dict[str, Any]:
    chat_file = get_owned_file(db, user, chat_id, file_id)
    if chat_file.analysis_json is None:
        raise ApiError(404, "not_found", "This file has not been analysed.")
    return chat_file.analysis_json


@router.get("/chats/{chat_id}/files/{file_id}/pages/{n}.png")
def read_file_page(chat_id: str, file_id: str, n: int, db: DbDep, user: UserDep) -> Response:
    chat_file = get_owned_file(db, user, chat_id, file_id)
    if n < 1 or n > chat_file.page_count:
        raise ApiError(404, "not_found", "Page not found.")
    page = load_pages(storage.absolute_path(chat_file.file_path))[n - 1]
    buf = io.BytesIO()
    page.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")
