"""Signature heuristics: never put text on, or write, a signature.

`looks_like_signature_region` is pixel based (opencv, no OCR engine): a short wide line or
box near the bottom of the page with small printed text right under it (a "name / date" or
"signature" caption) or a printed "X" just to its left. Classifier-reported signature boxes
(see classify.py) are applied by `flag_signature_regions`.
"""

import re
from collections.abc import Sequence

import cv2
import numpy as np
from PIL import Image

from hwai.hand.segment import to_gray
from hwai.page.regions import Region

INK_THRESHOLD = 200
BOTTOM_FRAC = 0.45  # region must start in the lower 55% of the page...
MIN_ASPECT = 3.0  # ...be short and wide...
MIN_WIDTH_FRAC = 0.12
MAX_WIDTH_FRAC = 0.75  # signature spots are short; full-width rules are not
CAPTION_MAX_PX = 70  # caption search strip height under the line (150 DPI)
CAPTION_MIN_GLYPHS = 3
GLYPH_MIN_H, GLYPH_MAX_H = 5, 45

_TEXT_PATTERNS = [
    r"\bsignatures?\b",
    r"\bautograph",
    r"\bsign\s+(it|this|that|here|off|the\s+(card|letter|bottom|page|form)|my\s+name|for\s+me)\b",
    r"\bsign\s+(it\s+)?(as|with|using)\b",
    r"\bsigned\s*(by|:)",
    r"\bput\s+my\s+name\s+(at|on)\s+the\s+(bottom|signature)",
]
_TEXT_RE = re.compile("|".join(_TEXT_PATTERNS), re.IGNORECASE)


def looks_like_signature_text(text: str, own_name: str | None = None) -> bool:
    """True if `text` asks for a signature ("sign it Dan", "write my signature") or, when
    `own_name` is given, is nothing but that name (a bare name, as in a signature box)."""
    if _TEXT_RE.search(text):
        return True
    if own_name:
        norm = re.sub(r"[^a-z ]", "", text.lower()).split()
        name = re.sub(r"[^a-z ]", "", own_name.lower()).split()
        return bool(norm) and norm == name
    return False


def text_ink(gray: np.ndarray, threshold: int = INK_THRESHOLD) -> np.ndarray:
    """0/1 ink mask with long straight horizontal/vertical strokes (rules, borders) removed."""
    ink = (gray < threshold).astype(np.uint8)
    h = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1)))
    v = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40)))
    strokes = cv2.dilate(cv2.bitwise_or(h, v), np.ones((3, 3), np.uint8))
    out: np.ndarray = cv2.bitwise_and(ink, cv2.subtract(np.ones_like(strokes), strokes))
    return out


def _glyph_boxes(mask: np.ndarray) -> list[tuple[int, int, int, int]]:
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    out = []
    for i in range(1, n):
        x, y, w, h, area = (int(v) for v in stats[i])
        if GLYPH_MIN_H <= h <= GLYPH_MAX_H and w <= 4 * GLYPH_MAX_H and area >= 6:
            out.append((x, y, w, h))
    return out


def _is_x_mark(mask: np.ndarray, box: tuple[int, int, int, int]) -> bool:
    x, y, w, h = box
    if not (12 <= h <= 60 and 0.6 <= w / h <= 1.6):
        return False
    t = max(2, round(min(w, h) * 0.15))
    hit = 0
    for i in range(10):
        f = (i + 0.5) / 10
        for fx in (f, 1 - f):
            px, py = int(x + fx * (w - 1)), int(y + f * (h - 1))
            if mask[max(0, py - t) : py + t + 1, max(0, px - t) : px + t + 1].any():
                hit += 1
    return hit >= 17  # both diagonals inked, as an X is


def looks_like_signature_region(region: Region, page_img: Image.Image) -> bool:
    """True if the region reads as a signature line/box (see module docstring)."""
    x0, y0, x1, y1 = region.bbox_px
    w, h = x1 - x0, y1 - y0
    pw, ph = page_img.size
    if region.kind == "blank" or h <= 0 or not MIN_WIDTH_FRAC * pw <= w <= MAX_WIDTH_FRAC * pw:
        return False
    if region.kind == "box" and w / h < MIN_ASPECT:  # a line's bbox is its writing band
        return False
    if y0 < BOTTOM_FRAC * ph:
        return False
    mask = text_ink(to_gray(page_img))

    below = mask[y1 + 2 : min(ph, y1 + 2 + CAPTION_MAX_PX), max(0, x0) : min(pw, x1)]
    if below.size and len(_glyph_boxes(below)) >= CAPTION_MIN_GLYPHS:
        return True

    ys = slice(max(0, y1 - 70), min(ph, y1 + 10))
    left = mask[ys, max(0, x0 - 120) : x0 + 4]
    return any(_is_x_mark(left, b) for b in _glyph_boxes(left))


def flag_signature_regions(
    regions: list[Region],
    page_img: Image.Image,
    classifier_boxes: Sequence[tuple[float, float, float, float]] = (),
) -> list[Region]:
    """Copy of `regions` with `signature=True` on every region that looks like a signature
    spot by pixels or overlaps a classifier-reported box (fractions of the page, x0 y0 x1 y1)."""
    pw, ph = page_img.size
    out: list[Region] = []
    for r in regions:
        flagged = r.signature or looks_like_signature_region(r, page_img)
        if not flagged:
            for fx0, fy0, fx1, fy1 in classifier_boxes:
                ix = min(r.bbox_px[2], fx1 * pw) - max(r.bbox_px[0], fx0 * pw)
                iy = min(r.bbox_px[3], fy1 * ph) - max(r.bbox_px[1], fy0 * ph)
                if ix > 0 and iy > -0.5 * r.height:
                    flagged = True
                    break
        out.append(r.model_copy(update={"signature": flagged}))
    return out
