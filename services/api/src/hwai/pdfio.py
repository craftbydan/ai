"""PDF/PNG/JPEG <-> PIL image helpers."""

import io
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, UnidentifiedImageError

from hwai.errors import ApiError

MAX_BYTES = 20 * 1024 * 1024
MAX_PAGES = 30
PDF_POINTS_PER_INCH = 72


@dataclass(frozen=True)
class FileInfo:
    kind: str  # pdf | image
    ext: str  # pdf | png | jpg
    page_count: int


def _unsupported() -> ApiError:
    return ApiError(400, "unsupported_file", "Please upload a PDF, PNG or JPEG file.")


def sniff(data: bytes) -> tuple[str, str]:
    """Return (kind, ext) from file content, not from the filename."""
    if data.startswith(b"%PDF-"):
        return "pdf", "pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image", "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image", "jpg"
    raise _unsupported()


def inspect_file(data: bytes) -> FileInfo:
    """Validate an upload (size, type, page count) and return what it is."""
    if len(data) > MAX_BYTES:
        raise ApiError(413, "file_too_large", "That file is over 20 MB.")
    kind, ext = sniff(data)
    if kind == "pdf":
        try:
            pdf = pdfium.PdfDocument(data)
            count = len(pdf)
            pdf.close()
        except pdfium.PdfiumError as exc:
            raise _unsupported() from exc
        if count == 0:
            raise _unsupported()
        if count > MAX_PAGES:
            raise ApiError(400, "too_many_pages", f"That file has more than {MAX_PAGES} pages.")
        return FileInfo(kind, ext, count)
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise _unsupported() from exc
    return FileInfo(kind, ext, 1)


def page_images(path: str | Path, dpi: int = 150) -> list[Image.Image]:
    """Render a PDF (one image per page) or load an image (one page) as RGB."""
    data = Path(path).read_bytes()
    info = inspect_file(data)
    if info.kind == "image":
        with Image.open(io.BytesIO(data)) as img:
            return [img.convert("RGB")]
    pdf = pdfium.PdfDocument(data)
    try:
        scale = dpi / PDF_POINTS_PER_INCH
        return [pdf[i].render(scale=scale).to_pil().convert("RGB") for i in range(len(pdf))]
    finally:
        pdf.close()


def pdf_page_size_points(path: str | Path) -> tuple[float, float] | None:
    """Size of the first page of a PDF in points, as stored in the file; None for images."""
    data = Path(path).read_bytes()
    if not data.startswith(b"%PDF-"):
        return None
    pdf = pdfium.PdfDocument(data)
    try:
        width, height = pdf[0].get_size()
        return float(width), float(height)
    finally:
        pdf.close()
