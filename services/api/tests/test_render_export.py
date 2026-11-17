import io

import numpy as np
import pikepdf
from PIL import Image

from hwai.export import export_pdf, export_png
from hwai.render import get_renderer
from hwai.render.fake import FakeRenderer
from hwai.text.splitter import EnglishSplitter


def _bytes(seed: int, word: str = "hello") -> bytes:
    return FakeRenderer().render_word(word, [], seed=seed, size_px=64).image.tobytes()


def test_same_seed_identical_bytes() -> None:
    assert _bytes(1) == _bytes(1)


def test_different_seed_different_bytes() -> None:
    assert _bytes(1) != _bytes(2)


def test_rgba_with_nonempty_bbox() -> None:
    w = get_renderer().render_word("hello", [], seed=1, size_px=64)
    assert w.image.mode == "RGBA"
    bbox = w.image.getchannel("A").getbbox()
    assert bbox is not None and bbox[2] - bbox[0] > 40
    assert 0 < w.baseline_px <= w.image.height


def test_empty_word_is_1x1_transparent() -> None:
    w = FakeRenderer().render_word("", [], seed=1, size_px=64)
    assert w.image.size == (1, 1)
    assert w.image.getpixel((0, 0))[3] == 0


def test_png_export_has_ai_chunk_and_footer() -> None:
    page = Image.new("RGB", (1240, 1754), "white")
    data = export_png(page)
    img = Image.open(io.BytesIO(data))
    img.load()
    assert img.info["ai_generated"] == "true"
    footer = np.array(img.convert("L"))[-60:, -400:]
    assert (footer < 250).any()


def test_pdf_export_metadata() -> None:
    page = Image.new("RGB", (620, 877), "white")
    data = export_pdf([page], (297.6, 421.0))
    with pikepdf.open(io.BytesIO(data)) as pdf:
        assert "AI-generated" in str(pdf.docinfo["/Keywords"])
        assert "handwriting-ai" in str(pdf.docinfo["/Subject"])


def test_english_splitter() -> None:
    assert EnglishSplitter().units("Dear Dan,\nthank you!") == [
        "Dear",
        "Dan",
        ",",
        "\n",
        "thank",
        "you",
        "!",
    ]
