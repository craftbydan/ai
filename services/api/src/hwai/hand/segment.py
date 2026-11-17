"""Pure image maths for finding lines and words in a handwriting page (no torch).

All boxes are `BBox(x0, y0, x1, y1)` in pixels, top-left origin, x1/y1 exclusive.
"""

from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image


@dataclass(frozen=True)
class BBox:
    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def height(self) -> int:
        return self.y1 - self.y0


def to_gray(img: Image.Image | np.ndarray) -> np.ndarray:
    """Greyscale uint8 array from a PIL image (any mode) or an array."""
    if isinstance(img, Image.Image):
        return np.asarray(img.convert("L"), dtype=np.uint8)
    arr = np.asarray(img)
    if arr.ndim == 3:
        arr = cv2.cvtColor(arr.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    return arr.astype(np.uint8)


def ink_mask(gray: np.ndarray) -> np.ndarray:
    """Boolean mask of ink pixels: adaptive threshold, also required to be fairly dark."""
    short = min(gray.shape)
    block = max(15, (short // 20) | 1)
    adaptive = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, block, 12
    )
    mask: np.ndarray = (adaptive > 0) & (gray < 190)
    return mask


def estimate_skew(gray: np.ndarray, max_deg: float = 3.0) -> float:
    """Skew in degrees (positive = text runs downward to the right), by projection sharpness."""
    scale = 600.0 / max(gray.shape)
    small = cv2.resize(
        gray, None, fx=min(scale, 1.0), fy=min(scale, 1.0), interpolation=cv2.INTER_AREA
    )
    mask = ink_mask(small).astype(np.float32)
    if mask.sum() < 50:
        return 0.0
    h, w = mask.shape
    best_angle, best_score = 0.0, -1.0
    for angle in np.arange(-max_deg, max_deg + 0.01, 0.25):
        m = cv2.getRotationMatrix2D((w / 2, h / 2), float(angle), 1.0)
        rot = cv2.warpAffine(mask, m, (w, h), flags=cv2.INTER_NEAREST)
        score = float(np.var(rot.sum(axis=1)))
        if score > best_score + 1e-6:
            best_angle, best_score = float(angle), score
    return -best_angle


def deskew_page(img: Image.Image, max_deg: float = 3.0) -> Image.Image:
    """Rotate a page by a small estimated skew (skips rotation below 0.3 degrees)."""
    gray = to_gray(img)
    skew = estimate_skew(gray, max_deg)
    if abs(skew) < 0.3:
        return img
    h, w = gray.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), -skew, 1.0)
    out = cv2.warpAffine(
        np.asarray(img.convert("L")), m, (w, h), flags=cv2.INTER_LINEAR, borderValue=255
    )
    return Image.fromarray(out)


def _runs(flags: np.ndarray) -> list[tuple[int, int]]:
    """Half-open (start, end) runs where `flags` is True."""
    padded = np.concatenate([[0], flags.astype(np.int8), [0]])
    edges = np.diff(padded)
    starts = np.flatnonzero(edges == 1)
    ends = np.flatnonzero(edges == -1)
    return [(int(s), int(e)) for s, e in zip(starts, ends, strict=True)]


def _merge(runs: list[tuple[int, int]], max_gap: int) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for s, e in runs:
        if out and s - out[-1][1] <= max_gap:
            out[-1] = (out[-1][0], e)
        else:
            out.append((s, e))
    return out


def find_lines(page_img: Image.Image | np.ndarray, pad: int = 4) -> list[BBox]:
    """Text lines of a page, top to bottom, by horizontal projection of ink.

    Call `deskew_page` first if the page may be slightly rotated.
    """
    gray = to_gray(page_img)
    h, w = gray.shape
    mask = ink_mask(gray)
    rows = mask.sum(axis=1)
    noise = max(1, int(0.002 * w))
    runs = _merge(_runs(rows > noise), max(5, int(0.008 * h)))
    boxes: list[BBox] = []
    min_h = max(10, int(0.008 * h))
    for y0, y1 in runs:
        band = mask[y0:y1]
        if y1 - y0 < min_h or int(band.sum()) < 40:
            continue
        cols = np.flatnonzero(band.sum(axis=0) > 0)
        x0, x1 = int(cols[0]), int(cols[-1]) + 1
        boxes.append(BBox(max(0, x0 - pad), max(0, y0 - pad), min(w, x1 + pad), min(h, y1 + pad)))
    return boxes


def split_words(
    line_img: Image.Image | np.ndarray,
    pad: int = 4,
    gap_ratio: float = 0.2,
    n_words: int | None = None,
) -> list[BBox]:
    """Word boxes inside one line image, left to right.

    A word break is an ink-free vertical gap wider than `gap_ratio` x the line's ink height.
    If `n_words` is given (for example the word count an OCR engine read), the line is instead
    cut at its `n_words - 1` widest gaps. Boxes are relative to `line_img`, padded by `pad`.
    """
    gray = to_gray(line_img)
    h, w = gray.shape
    mask = ink_mask(gray)
    rows = np.flatnonzero(mask.sum(axis=1) > 0)
    if rows.size == 0:
        return []
    ink_h = int(rows[-1] - rows[0] + 1)
    cols = mask.sum(axis=0) > 0
    ink_runs = _runs(cols)
    if n_words is None:
        runs = _merge(ink_runs, max(2, int(gap_ratio * ink_h)))
    else:
        gaps = sorted(
            ((ink_runs[i + 1][0] - ink_runs[i][1], i) for i in range(len(ink_runs) - 1)),
            reverse=True,
        )
        breaks = {i for _, i in gaps[: max(0, n_words - 1)]}
        runs = []
        for i, (s, e) in enumerate(ink_runs):
            if runs and (i - 1) not in breaks:
                runs[-1] = (runs[-1][0], e)
            else:
                runs.append((s, e))
    boxes: list[BBox] = []
    for x0, x1 in runs:
        sub = mask[:, x0:x1]
        ys = np.flatnonzero(sub.sum(axis=1) > 0)
        if ys.size == 0:
            continue
        boxes.append(
            BBox(
                max(0, x0 - pad),
                max(0, int(ys[0]) - pad),
                min(w, x1 + pad),
                min(h, int(ys[-1]) + 1 + pad),
            )
        )
    return boxes
