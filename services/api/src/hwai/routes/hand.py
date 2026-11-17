from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, File, Form, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from hwai import storage
from hwai.deps import DbDep, UserDep
from hwai.errors import ApiError
from hwai.hand.ingest import ingest_document
from hwai.hand.profile import REASONS
from hwai.models import Hand, HandDocument, User, WordSample
from hwai.pdfio import inspect_file
from hwai.routes.uploads import read_upload
from hwai.schemas import HandDocumentOut, HandOut

router = APIRouter()


def get_user_hand(db: Session, user: User) -> Hand | None:
    return db.scalar(select(Hand).where(Hand.user_id == user.id))


def hand_out(db: Session, hand: Hand | None) -> HandOut:
    if hand is None:
        return HandOut(id=None, status="empty", own_hand_confirmed_at=None, documents=[])
    count = db.scalar(
        select(func.count()).select_from(WordSample).where(WordSample.hand_id == hand.id)
    )
    docs = db.scalars(
        select(HandDocument)
        .where(HandDocument.hand_id == hand.id)
        .order_by(HandDocument.created_at, HandDocument.id)
    ).all()
    return HandOut(
        id=hand.id,
        status=hand.status,
        status_reason=hand.status_reason,
        status_message=REASONS.get(hand.status_reason or "", hand.status_reason),
        sample_count=count or 0,
        own_hand_confirmed_at=hand.own_hand_confirmed_at,
        documents=[HandDocumentOut.model_validate(d, from_attributes=True) for d in docs],
    )


@router.get("/hand", response_model=HandOut)
def read_hand(db: DbDep, user: UserDep) -> HandOut:
    return hand_out(db, get_user_hand(db, user))


@router.post("/hand/documents", response_model=HandDocumentOut, status_code=201)
def upload_hand_document(
    file: Annotated[UploadFile, File()],
    background: BackgroundTasks,
    db: DbDep,
    user: UserDep,
    own_hand_confirmed: Annotated[bool, Form()] = False,
) -> HandDocumentOut:
    if not own_hand_confirmed:
        raise ApiError(
            400,
            "own_hand_not_confirmed",
            "Please confirm this is your own handwriting before uploading.",
        )
    data = read_upload(file)
    info = inspect_file(data)
    hand = get_user_hand(db, user)
    if hand is None:
        hand = Hand(user_id=user.id)
        db.add(hand)
    if hand.own_hand_confirmed_at is None:
        hand.own_hand_confirmed_at = datetime.now(UTC)
    rel = storage.save_file(user.id, "hand", data, info.ext)
    hand.status = "learning"
    hand.status_reason = None
    db.flush()
    doc = HandDocument(hand_id=hand.id, file_path=rel, page_count=info.page_count)
    db.add(doc)
    try:
        db.commit()
    except Exception:
        db.rollback()
        storage.delete_file(rel)
        raise
    background.add_task(ingest_document, doc.id)
    return HandDocumentOut.model_validate(doc, from_attributes=True).model_copy(
        update={"own_hand_confirmed_at": hand.own_hand_confirmed_at}
    )
