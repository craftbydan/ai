"""Export a render as a marked PDF or PNG at the original page size."""

import io
from typing import Literal

from fastapi import APIRouter, Response
from PIL import Image

from hwai import storage
from hwai.billing import billing_required, checkout_hint, is_paid
from hwai.config import get_settings
from hwai.deps import DbDep, UserDep
from hwai.errors import ApiError
from hwai.export import export_pdf, export_png, image_size_points
from hwai.models import Export
from hwai.pdfio import pdf_page_size_points
from hwai.routes.chats import get_owned_chat
from hwai.routes.renders import get_owned_render, page_path, target_file

router = APIRouter()


@router.post("/chats/{chat_id}/export")
def export_render(
    chat_id: str,
    version: int,
    format: Literal["pdf", "png"],
    db: DbDep,
    user: UserDep,
    page: int = 1,
) -> Response:
    chat = get_owned_chat(db, user, chat_id)
    render = get_owned_render(db, chat, version)
    chat_file = target_file(db, chat)  # safety first: a refused file is never exportable
    if billing_required(get_settings()) and not is_paid(db, chat.id, version):
        raise ApiError(
            402,
            "payment_required",
            "Please pay to export this version.",
            checkout_hint(chat, version),
        )
    assert render.preview_path is not None
    pages: list[Image.Image] = []
    n = 1
    while True:
        try:
            data = storage.read_file(page_path(render.preview_path, n))
        except FileNotFoundError:
            break
        pages.append(Image.open(io.BytesIO(data)).convert("RGB"))
        n += 1
    if not pages:
        raise ApiError(404, "not_found", "Render not found.")

    if format == "pdf":
        size = pdf_page_size_points(storage.absolute_path(chat_file.file_path)) or (
            image_size_points(pages[0])
        )
        content = export_pdf(pages, size)
        media = "application/pdf"
    else:
        if page < 1 or page > len(pages):
            raise ApiError(404, "not_found", "Page not found.")
        content = export_png(pages[page - 1])
        media = "image/png"
    rel = storage.save_file(user.id, "exports", content, format)
    db.add(Export(render_id=render.id, format=format, file_path=rel))
    db.commit()
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="export-v{version}.{format}"'},
    )
