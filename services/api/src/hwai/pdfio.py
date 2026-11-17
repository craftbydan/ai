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
# Decompression-bomb guard: set explicitly (Pillow's default is ~89 MP and only warns at 1x).
# ~50 MP covers a 600 DPI A4 scan (35 MP); anything bigger is rejected with a 400 before decoding.
MAX_IMAGE_PIXELS = 50_000_000
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
RENDER_DPI = 150


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


def _too_big() -> ApiError:
    return ApiError(
        400, "image_too_large", "That image has too many pixels. Please use a smaller image."
    )


def inspect_file(data: bytes) -> FileInfo:
    """Validate an upload (size, type, page count) and return what it is."""
    if len(data) > MAX_BYTES:
        raise ApiError(413, "file_too_large", "That file is over 20 MB.")
    kind, ext = sniff(data)
    if kind == "pdf":
        try:
            pdf = pdfium.PdfDocument(data)
        except pdfium.PdfiumError as exc:
            raise _unsupported() from exc
        try:
            count = len(pdf)
            if count == 0:
                raise _unsupported()
            if count > MAX_PAGES:
                raise ApiError(400, "too_many_pages", f"That file has more than {MAX_PAGES} pages.")
            scale = RENDER_DPI / PDF_POINTS_PER_INCH
            for i in range(count):
                w, h = pdf[i].get_size()
                if w * scale * h * scale > MAX_IMAGE_PIXELS:
                    raise _too_big()
        except pdfium.PdfiumError as exc:
            raise _unsupported() from exc
        finally:
            pdf.close()
        return FileInfo(kind, ext, count)
    try:
        with Image.open(io.BytesIO(data)) as img:
            if img.width * img.height > MAX_IMAGE_PIXELS:
                raise _too_big()
            img.verify()
    except Image.DecompressionBombError as exc:
        raise _too_big() from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise _unsupported() from exc
    return FileInfo(kind, ext, 1)


def page_images(path: str | Path, dpi: int = RENDER_DPI) -> list[Image.Image]:
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
