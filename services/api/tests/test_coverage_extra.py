"""Direct tests for export.py and the signature heuristics (coverage floor, real assertions)."""

import io
from pathlib import Path

import pikepdf
import pytest
from PIL import Image, ImageDraw

from hwai import export
from hwai.page.regions import Region
from hwai.safety.signature import flag_signature_regions, looks_like_signature_region


def test_px_to_pt_and_page_size_use_150_dpi() -> None:
    assert export.px_to_pt(150) == pytest.approx(72.0)
    w, h = export.image_size_points(Image.new("RGB", (1240, 1754)))
    assert (round(w), round(h)) == (595, 842)


def test_export_pdf_without_pages_is_an_error() -> None:
    with pytest.raises(ValueError):
        export.export_pdf([], (100.0, 100.0))


def test_export_png_composites_overlay_layers_and_marks() -> None:
    page = Image.new("RGB", (400, 300), "white")
    ink = Image.new("RGBA", (20, 20), (0, 0, 0, 255))
    out = Image.open(io.BytesIO(export.export_png(page, [(ink, (50, 60))])))
    assert out.text["ai_generated"] == "true"  # type: ignore[attr-defined]
    assert out.convert("RGB").getpixel((60, 70)) == (0, 0, 0)
    assert out.convert("RGB").getpixel((5, 5)) == (255, 255, 255)


def test_export_pdf_has_one_page_per_image_and_metadata() -> None:
    pages = [Image.new("RGB", (300, 400), "white") for _ in range(3)]
    data = export.export_pdf(pages, (144.0, 192.0))
    with pikepdf.open(io.BytesIO(data)) as pdf:
        assert len(pdf.pages) == 3
        assert str(pdf.docinfo["/Keywords"]) == export.PDF_KEYWORDS
        assert str(pdf.docinfo["/Subject"]) == export.PDF_SUBJECT


def test_export_demo_writes_a_marked_pdf(tmp_path: Path) -> None:
    out = tmp_path / "demo.pdf"
    export._demo(str(out))
    with pikepdf.open(out) as pdf:
        assert len(pdf.pages) == 1
        assert str(pdf.docinfo["/Subject"]) == export.PDF_SUBJECT


def _line_region(y: int) -> Region:
    return Region(
        id="r1",
        page=1,
        kind="line",
        bbox_px=(300, y - 4, 900, y + 4),
        baseline_px=y,
        line_height_px=40,
    )


def _page_with_x_mark() -> tuple[Image.Image, Region]:
    page = Image.new("RGB", (1000, 1400), "white")
    d = ImageDraw.Draw(page)
    y = 1250
    d.line([(300, y), (900, y)], fill="black", width=2)
    d.line([(240, y - 40), (270, y - 10)], fill="black", width=4)  # an X before the line
    d.line([(270, y - 40), (240, y - 10)], fill="black", width=4)
    return page, _line_region(y)


def test_x_mark_before_a_low_line_is_a_signature_spot() -> None:
    page, region = _page_with_x_mark()
    assert looks_like_signature_region(region, page)


def test_plain_line_without_x_or_caption_is_not() -> None:
    page = Image.new("RGB", (1000, 1400), "white")
    ImageDraw.Draw(page).line([(300, 1250), (900, 1250)], fill="black", width=2)
    assert not looks_like_signature_region(_line_region(1250), page)


def test_line_high_on_the_page_is_never_a_signature_spot() -> None:
    page, _ = _page_with_x_mark()
    assert not looks_like_signature_region(_line_region(200), page)


def test_classifier_boxes_flag_overlapping_regions_only() -> None:
    page = Image.new("RGB", (1000, 1400), "white")
    near = Region(id="a", page=1, kind="blank", bbox_px=(100, 100, 400, 300))
    far = Region(id="b", page=1, kind="blank", bbox_px=(600, 900, 900, 1100))
    out = flag_signature_regions([near, far], page, [(0.05, 0.05, 0.5, 0.25)])
    assert [r.signature for r in out] == [True, False]
    assert [r.signature for r in flag_signature_regions([near, far], page)] == [False, False]
