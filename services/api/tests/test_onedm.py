import os
import subprocess
import sys

import numpy as np
import pytest
from PIL import Image

from hwai.config import get_settings
from hwai.errors import ApiError
from hwai.render import get_renderer
from hwai.render.base import StyleRef
from hwai.render.fixture_style import fixture_style_ref
from hwai.render.onedm import (
    OneDMRenderer,
    estimate_baseline,
    gray_to_rgba,
    prepare_style,
    validate_word,
)


def _synthetic_output() -> np.ndarray:
    """64 x 160 white page with a dark 'word' band and a thin descender."""
    a = np.ones((64, 160), dtype=np.float32)
    a[20:44, 30:120] = 0.1  # body
    a[44:56, 60:63] = 0.2  # descender
    return a


def test_gray_to_rgba_ink_is_alpha_and_background_removed() -> None:
    w = gray_to_rgba(_synthetic_output())
    assert w.image.mode == "RGBA"
    arr = np.asarray(w.image)
    assert arr[:, :, 3].max() == 255
    assert (arr[:, :, 3] == 0).sum() > 0  # transparent background survives the crop
    bbox = w.image.getchannel("A").getbbox()
    assert bbox is not None
    # cropped to ink: 90 wide, 36 tall (rows 20..56)
    assert w.image.size == (90, 36)


def test_gray_to_rgba_baseline_is_bottom_of_body_not_descender() -> None:
    w = gray_to_rgba(_synthetic_output())
    assert w.baseline_px == 24  # body rows 20..43 -> 24 rows from the top of the crop


def test_gray_to_rgba_scale_and_channel_input() -> None:
    rgb = np.repeat(_synthetic_output()[:, :, None], 3, axis=2)
    w = gray_to_rgba(rgb, scale=0.5)
    assert w.image.size == (45, 18)
    assert 0 < w.baseline_px <= w.image.height


def test_gray_to_rgba_blank_gives_1x1_transparent() -> None:
    w = gray_to_rgba(np.ones((64, 96), dtype=np.float32))
    assert w.image.size == (1, 1) and w.image.getpixel((0, 0))[3] == 0


def test_estimate_baseline_blank() -> None:
    assert estimate_baseline(np.zeros((10, 5), dtype=np.uint8)) == 10


def test_prepare_style_shapes_and_range() -> None:
    img = Image.new("RGBA", (400, 100), (0, 0, 0, 0))
    img.paste((10, 10, 10, 255), (50, 30, 300, 60))
    style, lap = prepare_style(img)
    assert style.shape == (64, 256) and lap.shape == style.shape
    assert style.dtype == np.float32 and 0.0 <= style.min() and style.max() <= 1.0
    assert style[0, 0] == 1.0  # transparent -> white paper
    assert style.min() < 0.2 and lap.max() > 0
    assert lap.min() >= 0.0 and lap.max() <= 1.0


def test_prepare_style_pads_narrow_and_clips_wide() -> None:
    narrow, _ = prepare_style(Image.new("L", (20, 64), 0))
    assert narrow.shape == (64, 128)
    wide, _ = prepare_style(Image.new("L", (2000, 64), 0))
    assert wide.shape == (64, 352)


def test_validate_word() -> None:
    validate_word("hello, World.")
    with pytest.raises(ApiError) as e:
        validate_word("café")
    assert e.value.code == "unsupported_character"


def test_get_renderer_onedm_without_torch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RENDERER", "onedm")
    get_settings.cache_clear()
    r = get_renderer()
    assert isinstance(r, OneDMRenderer)
    assert "torch" not in sys.modules


def test_import_does_not_import_torch() -> None:
    code = "import hwai.render.onedm, hwai.render, sys; assert 'torch' not in sys.modules"
    subprocess.run(
        [sys.executable, "-c", code], check=True, env={**os.environ, "RENDERER": "onedm"}
    )


@pytest.mark.parametrize("method", ["render_word", "render_words"])
def test_empty_style_refs_raise_no_style_ref(method: str) -> None:
    r = OneDMRenderer()
    with pytest.raises(ApiError) as e:
        if method == "render_word":
            r.render_word("hello", [], seed=1, size_px=64)
        else:
            r.render_words(["hello"], [], seed=1)
    assert e.value.code == "no_style_ref"
    assert "torch" not in sys.modules


def test_missing_weights_is_a_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ONEDM_WEIGHTS_PATH", "")
    get_settings.cache_clear()
    style = [StyleRef("a", Image.new("L", (200, 64), 255))]
    with pytest.raises(ApiError) as e:
        OneDMRenderer().render_word("hello", style, seed=1, size_px=64)
    assert e.value.code in {"onedm_not_installed", "onedm_weights_missing"}


# --- GPU only: RUN_GPU_TESTS=1 RENDERER=onedm pytest -m gpu -----------------------------------
gpu = pytest.mark.skipif(os.environ.get("RUN_GPU_TESTS") != "1", reason="set RUN_GPU_TESTS=1")


@pytest.mark.gpu
@gpu
def test_gpu_render_hello_and_seed_changes_output() -> None:
    r = OneDMRenderer()
    style = [fixture_style_ref()]
    a = r.render_word("hello", style, seed=1, size_px=64)
    b = r.render_word("hello", style, seed=2, size_px=64)
    assert a.image.mode == "RGBA"
    assert a.image.getchannel("A").getbbox() is not None
    assert a.image.tobytes() != b.image.tobytes()
