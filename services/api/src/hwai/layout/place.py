"""Layout engine: words -> pixels on a region, and composing the ink onto a page.

All coordinates are 150-DPI pixels, top-left origin. Ink never leaves the region: every word
image is cropped to the region box before it is returned.
"""

import math
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
from PIL import Image

from hwai.page.regions import Region
from hwai.render.base import Renderer, StyleRef
from hwai.render.jitter import apply_jitter
from hwai.text.splitter import EnglishSplitter, TextSplitter

Align = Literal["left", "center", "right"]

LINE_SPACING = 1.2
SHRINK_STEPS = (1.0, 0.9, 0.8, 0.7, 0.6)  # up to 40% smaller
WORD_GAP = 0.28  # of the font size
PUNCT_GAP = 0.04
NO_SPACE_BEFORE = set(".,!?;:)]}%”’…")
NO_SPACE_AFTER = set("([{“‘")
MIN_SIZE_PX = 8
MAX_SIZE_PX = 90


@dataclass(frozen=True)
class PlacedWord:
    x: int
    y: int
    image: Image.Image  # RGBA ink, already inside the region
    text: str = ""


@dataclass
class PlacedText:
    words: list[PlacedWord]
    region_id: str
    page: int
    bbox_px: tuple[int, int, int, int]
    fit: bool = True
    cut_words: int = 0
    size_px: int = 0
    shrink: float = 1.0
    unit_count: int = 0
    extra: dict[str, float] = field(default_factory=dict)


def base_size_px(region: Region, size_scale: float) -> int:
    """Font size before any shrinking: from the line height (lines) or the box size (others)."""
    if region.kind == "line" and region.line_height_px:
        size = 0.85 * region.line_height_px
    else:
        size = min(0.12 * region.width, 0.2 * region.height, MAX_SIZE_PX)
    return max(MIN_SIZE_PX, round(size * size_scale))


def _word_seed(seed: int, idx: int) -> int:
    return (seed * 7919 + idx * 104729 + 17) & 0x7FFFFFFF


def _styled(
    word_img: Image.Image, baseline: int, scale: float, slant_deg: float, angle: float
) -> tuple[Image.Image, int]:
    """Scale, shear (slant) and rotate one word; returns the cropped image and baseline offset."""
    img = word_img.convert("RGBA")
    if abs(scale - 1.0) > 1e-3:
        w = max(1, round(img.width * scale))
        h = max(1, round(img.height * scale))
        img = img.resize((w, h), Image.Resampling.LANCZOS)
        baseline = round(baseline * scale)
    t = math.tan(math.radians(slant_deg))
    if abs(t) < 1e-4 and abs(angle) < 1e-3:
        return img, baseline
    w, h = img.size
    sin_a = abs(math.sin(math.radians(angle)))
    py = math.ceil(w * sin_a) + 3
    px = math.ceil(h * abs(t)) + math.ceil(h * sin_a) + 3
    canvas = Image.new("RGBA", (w + 2 * px, h + 2 * py), (0, 0, 0, 0))
    canvas.paste(img, (px, py))
    by = baseline + py
    if abs(t) >= 1e-4:
        canvas = canvas.transform(
            canvas.size,
            Image.Transform.AFFINE,
            (1.0, t, -t * by, 0.0, 1.0, 0.0),
            resample=Image.Resampling.BICUBIC,
        )
    if abs(angle) >= 1e-3:
        canvas = canvas.rotate(angle, resample=Image.Resampling.BICUBIC)
    bbox = canvas.getchannel("A").getbbox()
    if bbox is None:
        return img, baseline
    return canvas.crop(bbox), by - bbox[1]


@dataclass
class _Unit:
    text: str
    image: Image.Image
    baseline: int


def _gap(prev: str, cur: str, size: int) -> int:
    if cur[0] in NO_SPACE_BEFORE or prev[-1] in NO_SPACE_AFTER:
        return round(PUNCT_GAP * size)
    return round(WORD_GAP * size)


def _wrap(units: list[_Unit | None], width: int, size: int) -> tuple[list[list[int]], list[int]]:
    """Greedy wrap. `None` is an explicit newline. Returns (lines of unit indices, too-wide)."""
    lines: list[list[int]] = [[]]
    used = 0
    too_wide: list[int] = []
    prev: str | None = None
    for i, u in enumerate(units):
        if u is None:
            lines.append([])
            used, prev = 0, None
            continue
        if u.image.width > width:
            too_wide.append(i)
            continue
        gap = _gap(prev, u.text, size) if prev is not None and lines[-1] else 0
        if lines[-1] and used + gap + u.image.width > width:
            lines.append([])
            used, gap = 0, 0
        lines[-1].append(i)
        used += gap + u.image.width
        prev = u.text
    return lines, too_wide


def _clip(img: Image.Image, x: int, y: int, box: tuple[int, int, int, int]) -> PlacedWord | None:
    x0, y0, x1, y1 = box
    left, top = max(x, x0), max(y, y0)
    right, bottom = min(x + img.width, x1), min(y + img.height, y1)
    if right <= left or bottom <= top:
        return None
    cropped = img.crop((left - x, top - y, right - x, bottom - y))
    if cropped.getchannel("A").getbbox() is None:
        return None
    return PlacedWord(left, top, cropped)


def layout_text(
    region: Region,
    text: str,
    align: Align,
    size_scale: float,
    slant_deg: float,
    jitter: float,
    seed: int,
    renderer: Renderer,
    style_refs: list[StyleRef],
    splitter: TextSplitter | None = None,
) -> PlacedText:
    """Render every word and place it inside `region`. Shrinks up to 40% when the text does not
    fit; if it still does not, `fit` is False, `cut_words` counts what was left out, and nothing
    is ever drawn outside the region."""
    box = region.bbox_px
    x0, y0, x1, y1 = box
    pad = max(4, round(0.02 * region.width))
    width = region.width - 2 * pad
    size0 = base_size_px(region, size_scale)

    raw: list[str | None] = []
    for tok in (splitter or EnglishSplitter()).units(text):
        if tok == "\n":
            raw.append(None)
        elif tok.strip():
            raw.append(tok)
    n_units = sum(1 for u in raw if u is not None)

    def build(shrink: float) -> list[_Unit | None]:
        out: list[_Unit | None] = []
        idx = 0
        for u in raw:
            if u is None:
                out.append(None)
                continue
            wseed = _word_seed(seed, idx)
            rng = np.random.default_rng(wseed)
            word = renderer.render_word(u, style_refs, wseed, size0)
            var = 1.0 + float(rng.uniform(-0.04, 0.04)) * jitter
            angle = float(np.clip(rng.normal(0, 1.2), -3, 3)) * jitter
            img = word.image
            if jitter > 0:
                img = apply_jitter(img, wseed, strength=jitter)
            styled, base = _styled(img, word.baseline_px, shrink * var, slant_deg, angle)
            out.append(_Unit(u, styled, base))
            idx += 1
        return out

    if n_units == 0:
        return PlacedText([], region.id, region.page, box, True, 0, size0, 1.0, 0)

    # Render once at full size (renders are the expensive part), then shrink by resizing.
    base_units = build(1.0)
    chosen_shrink = SHRINK_STEPS[-1]
    lines: list[list[int]] = []
    units: list[_Unit | None] = base_units
    cut = 0
    max_lines = 1
    fit = False
    for step in SHRINK_STEPS:
        if step == 1.0:
            units = base_units
        else:
            units = [
                None if u is None else _Unit(u.text, *_styled(u.image, u.baseline, step, 0.0, 0.0))
                for u in base_units
            ]
        size = max(1, round(size0 * step))
        line_h = LINE_SPACING * size
        max_lines = max(1, int(region.height // line_h))
        lines, too_wide = _wrap(units, width, size)
        nonempty = [ln for ln in lines if ln] if region.kind == "line" else lines
        lines = nonempty or lines
        chosen_shrink = step
        if len(lines) <= max_lines and not too_wide:
            fit = True
            cut = 0
            break
        kept = lines[:max_lines]
        cut = n_units - sum(len(ln) for ln in kept)
    size = max(1, round(size0 * chosen_shrink))
    line_h = LINE_SPACING * size
    lines = lines[:max_lines]

    by_idx: dict[int, _Unit] = {i: un for i, un in enumerate(units) if un is not None}

    # Positions: baselines relative to the first line, x per line by alignment.
    placed: list[tuple[int, int, _Unit]] = []  # (x, baseline_y, unit)
    for li, line in enumerate(lines):
        if not line:
            continue
        gaps = [
            _gap(by_idx[a].text, by_idx[b].text, size) for a, b in zip(line, line[1:], strict=False)
        ]
        line_w = sum(by_idx[i].image.width for i in line) + sum(gaps)
        if align == "center":
            x = x0 + pad + (width - line_w) // 2
        elif align == "right":
            x = x1 - pad - line_w
        else:
            x = x0 + pad
        by = round(li * line_h)
        for k, i in enumerate(line):
            un = by_idx[i]
            jrng = np.random.default_rng(_word_seed(seed, i) ^ 0x5BD1E995)
            wob = round(float(jrng.normal(0, 0.025 * size)) * jitter)
            placed.append((x, by + wob, un))
            x += un.image.width + (gaps[k] if k < len(gaps) else 0)

    if not placed:  # every word was wider than the region (e.g. one extremely long word)
        return PlacedText(
            [], region.id, region.page, box, False, n_units, size, chosen_shrink, n_units
        )

    if region.kind == "line" and region.baseline_px is not None:
        shift = region.baseline_px
    else:
        tops = [by - u.baseline for _, by, u in placed]
        bottoms = [by - u.baseline + u.image.height for _, by, u in placed]
        block_top, block_bottom = min(tops), max(bottoms)
        shift = round((y0 + y1) / 2 - (block_top + block_bottom) / 2)
        shift = (
            min(max(shift, y0 - block_top), y1 - block_bottom)
            if (block_bottom - block_top <= region.height)
            else shift
        )

    words: list[PlacedWord] = []
    for x, by, u in placed:
        pw = _clip(u.image, x, by + shift - u.baseline, box)
        if pw is not None:
            words.append(PlacedWord(pw.x, pw.y, pw.image, u.text))
    return PlacedText(
        words=words,
        region_id=region.id,
        page=region.page,
        bbox_px=box,
        fit=fit,
        cut_words=0 if fit else cut,
        size_px=size,
        shrink=chosen_shrink,
        unit_count=n_units,
    )


def compose(page_img: Image.Image, placed_texts: list[PlacedText]) -> Image.Image:
    """Multiply-blend all ink onto a copy of the page so ruled lines show through.
    Pixels with no ink are left exactly as they were."""
    page = np.array(page_img.convert("RGB"), dtype=np.float32)
    h, w = page.shape[:2]
    for pt in placed_texts:
        for pw in pt.words:
            x0, y0 = pw.x, pw.y
            x1, y1 = min(w, x0 + pw.image.width), min(h, y0 + pw.image.height)
            if x0 < 0 or y0 < 0 or x1 <= x0 or y1 <= y0:
                continue
            ink = np.array(pw.image.convert("RGBA"), dtype=np.float32)[: y1 - y0, : x1 - x0]
            alpha = ink[:, :, 3:4] / 255.0
            region = page[y0:y1, x0:x1]
            page[y0:y1, x0:x1] = region * (1.0 - alpha) + region * (ink[:, :, :3] / 255.0) * alpha
    return Image.fromarray(np.clip(np.rint(page), 0, 255).astype(np.uint8), "RGB")
