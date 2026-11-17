"""Flatten pages to PNG/PDF. Every export is marked AI generated; there is no way to disable it.

Pixel to PDF-point conversion lives only in this module (analysis is at 150 DPI).
"""

import io
from collections.abc import Sequence

import pikepdf
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from hwai.render.fake import FONT_PATH

DPI = 150
POINTS_PER_PIXEL = 72 / DPI
FOOTER_TEXT = "AI generated"
FOOTER_PT = 7
PDF_KEYWORDS = "AI-generated"
PDF_SUBJECT = "Generated with handwriting-ai"


def px_to_pt(px: float) -> float:
    return px * POINTS_PER_PIXEL


def _mark(page: Image.Image) -> Image.Image:
    """Return an RGB copy with the visible footer mark drawn bottom-right."""
    out = page.convert("RGB")
    draw = ImageDraw.Draw(out)
    font_px = max(1, round(FOOTER_PT / POINTS_PER_PIXEL))
    font = ImageFont.truetype(str(FONT_PATH), font_px)
    margin = font_px
    draw.text(
        (out.width - margin, out.height - margin),
        FOOTER_TEXT,
        font=font,
        fill=(110, 110, 110),
        anchor="rs",
    )
    return out


def _composite(
    page_image: Image.Image, overlay_layers: Sequence[tuple[Image.Image, tuple[int, int]]]
) -> Image.Image:
    base = page_image.convert("RGBA")
    for layer, (x, y) in overlay_layers:
        base.alpha_composite(layer.convert("RGBA"), (x, y))
    return base


def export_png(
    page_image: Image.Image,
    overlay_layers: Sequence[tuple[Image.Image, tuple[int, int]]] = (),
) -> bytes:
    """Composite RGBA overlays (image, (x, y) px) onto the page and write a marked PNG."""
    from PIL.PngImagePlugin import PngInfo

    info = PngInfo()
    info.add_text("ai_generated", "true")
    info.add_text("generator", PDF_SUBJECT)
    buf = io.BytesIO()
    _mark(_composite(page_image, overlay_layers)).save(
        buf, format="PNG", pnginfo=info, dpi=(DPI, DPI)
    )
    return buf.getvalue()


def export_pdf(pages: Sequence[Image.Image], size_points: tuple[float, float]) -> bytes:
    """One PDF page per image, each scaled to `size_points`, with AI-generated metadata."""
    if not pages:
        raise ValueError("export_pdf needs at least one page")
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=size_points)
    c.setTitle("Handwriting AI export")
    c.setSubject(PDF_SUBJECT)
    c.setKeywords(PDF_KEYWORDS)
    for page in pages:
        marked = _mark(page)
        c.drawImage(ImageReader(marked), 0, 0, width=size_points[0], height=size_points[1])
        c.showPage()
    c.save()

    # Re-open with pikepdf so metadata is guaranteed present in the Info dictionary.
    with pikepdf.open(io.BytesIO(buf.getvalue())) as pdf:
        pdf.docinfo["/Keywords"] = PDF_KEYWORDS
        pdf.docinfo["/Subject"] = PDF_SUBJECT
        out = io.BytesIO()
        pdf.save(out)
    return out.getvalue()


def _demo(out: str) -> None:
    from hwai.render.fake import FakeRenderer

    page = Image.new("RGB", (1240, 1754), "white")  # A4 at 150 DPI
    word = FakeRenderer().render_word("Hello", [], seed=1, size_px=96)
    pdf = export_pdf(
        [_composite(page, [(word.image, (200, 300))])],
        (px_to_pt(page.width), px_to_pt(page.height)),
    )
    with open(out, "wb") as f:
        f.write(pdf)
    print(f"wrote {out}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="export demo")
    parser.add_argument("--demo", action="store_true", required=True)
    parser.add_argument("--out", default="/tmp/demo.pdf")
    _demo(parser.parse_args().out)
