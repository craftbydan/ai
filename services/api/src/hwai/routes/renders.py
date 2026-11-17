"""Render placements onto the chat's target file and serve versioned previews."""

import io
from typing import Any

from fastapi import APIRouter, Response
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from hwai import storage
from hwai.deps import DbDep, UserDep
from hwai.errors import ApiError
from hwai.layout.place import PlacedText, compose, layout_text
from hwai.models import Chat, ChatFile, Render
from hwai.page.analyze import load_pages
from hwai.page.regions import Region
from hwai.render import get_renderer
from hwai.routes.chats import get_owned_chat
from hwai.schemas import FitItem, FitReport, Placement, RenderOut, RenderRequest

router = APIRouter()


def page_path(preview_path: str, page: int) -> str:
    """Stored composed page n of a render (page 1 is `preview_path` itself)."""
    return preview_path if page == 1 else preview_path.replace(".png", f"-p{page}.png")


def target_file(db: Session, chat: Chat) -> ChatFile:
    chat_file = db.scalar(
        select(ChatFile)
        .where(ChatFile.chat_id == chat.id)
        .order_by(ChatFile.created_at.desc(), ChatFile.id.desc())
    )
    if chat_file is None:
        raise ApiError(400, "no_file", "Upload a file to write on first.")
    if chat_file.safety_status != "ok":
        raise ApiError(400, "file_refused", "That file cannot be written on.")
    return chat_file


def get_owned_render(db: Session, chat: Chat, version: int) -> Render:
    render = db.scalar(select(Render).where(Render.chat_id == chat.id, Render.version == version))
    if render is None or render.preview_path is None:
        raise ApiError(404, "not_found", "Render not found.")
    return render


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def render_placements(db: Session, chat: Chat, placements: list[Placement]) -> RenderOut:
    """Shared by POST /chats/{id}/render and the agent's `render` tool."""
    chat_file = target_file(db, chat)
    analysis: dict[str, Any] = chat_file.analysis_json or {"pages": []}
    regions = {
        r["id"]: Region.model_validate(r) for page in analysis["pages"] for r in page["regions"]
    }
    for p in placements:
        if p.region_id not in regions:
            raise ApiError(
                422,
                "unknown_region",
                f"Region '{p.region_id}' does not exist on this file. "
                f"Valid regions: {', '.join(sorted(regions)) or 'none'}.",
            )

    renderer = get_renderer()
    placed: list[PlacedText] = []
    for p in placements:
        refs = []
        if chat.hand_id:
            from hwai.hand.profile import style_refs_for

            refs = style_refs_for(chat.hand_id, k=8, seed=p.seed, db=db)
        placed.append(
            layout_text(
                regions[p.region_id],
                p.text,
                p.align,
                p.size_scale,
                p.slant_deg,
                p.jitter,
                p.seed,
                renderer,
                refs,
            )
        )

    pages = load_pages(storage.absolute_path(chat_file.file_path))
    composed = [
        compose(img, [pt for pt in placed if pt.page == n]) for n, img in enumerate(pages, 1)
    ]

    last = db.scalar(select(func.max(Render.version)).where(Render.chat_id == chat.id)) or 0
    version = last + 1
    preview_path = storage.save_file(chat.user_id, "renders", _png(composed[0]), "png")
    for n, img in enumerate(composed[1:], 2):
        storage.write_file(page_path(preview_path, n), _png(img))
    db.add(
        Render(
            chat_id=chat.id,
            version=version,
            placements_json=[p.model_dump() for p in placements],
            preview_path=preview_path,
        )
    )
    db.commit()
    report = FitReport(
        all_fit=all(pt.fit for pt in placed),
        placements=[
            FitItem(
                region_id=pt.region_id,
                fit=pt.fit,
                cut_words=pt.cut_words,
                size_px=pt.size_px,
                shrink=pt.shrink,
            )
            for pt in placed
        ],
    )
    return RenderOut(
        version=version,
        preview_url=f"/chats/{chat.id}/renders/{version}/preview.png",
        fit_report=report,
    )


@router.post("/chats/{chat_id}/render", response_model=RenderOut)
def render_chat(chat_id: str, body: RenderRequest, db: DbDep, user: UserDep) -> RenderOut:
    chat = get_owned_chat(db, user, chat_id)
    return render_placements(db, chat, body.placements)


@router.get("/chats/{chat_id}/renders/{version}/preview.png")
def render_preview(chat_id: str, version: int, db: DbDep, user: UserDep, page: int = 1) -> Response:
    chat = get_owned_chat(db, user, chat_id)
    render = get_owned_render(db, chat, version)
    assert render.preview_path is not None
    try:
        data = storage.read_file(page_path(render.preview_path, page))
    except FileNotFoundError:
        raise ApiError(404, "not_found", "Page not found.") from None
    return Response(content=data, media_type="image/png")
