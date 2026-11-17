"""POST /chats/{id}/messages: run the chat agent."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from hwai.agent.loop import run_agent
from hwai.deps import DbDep, UserDep
from hwai.errors import ApiError
from hwai.llm import get_llm_client
from hwai.models import Hand
from hwai.routes.chats import get_owned_chat
from hwai.routes.renders import target_file

router = APIRouter()


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class MessageReply(BaseModel):
    reply: str
    render_version: int | None
    preview_url: str | None


@router.post("/chats/{chat_id}/messages", response_model=MessageReply)
def post_message(
    chat_id: str,
    body: MessageIn,
    db: DbDep,
    user: UserDep,
    client: Annotated[Any, Depends(get_llm_client)],
) -> MessageReply:
    chat = get_owned_chat(db, user, chat_id)
    hand = db.get(Hand, chat.hand_id) if chat.hand_id else None
    if hand is None or hand.status != "ready":
        raise ApiError(
            409,
            "hand_not_ready",
            "Your handwriting is not ready yet. Upload it and wait until it is learned.",
        )
    target_file(db, chat)  # friendly 400 no_file / file_refused before any model call
    result = run_agent(db, chat, body.text, client)
    return MessageReply(
        reply=result.reply, render_version=result.render_version, preview_url=result.preview_url
    )
