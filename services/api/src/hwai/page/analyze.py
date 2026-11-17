"""Classical image analysis of a target page: ruled lines, empty boxes, big blank areas.

No LLM, no model weights. Everything is derived from the pixels (nothing is fixture-specific).
Coordinates are pixels at the analysed image's resolution (150 DPI for PDFs), top-left origin.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel

from hwai.hand.segment import deskew_page, to_gray
from hwai.page.regions import MIN_REGION_PX, Region, finalize_regions, merge_segments
from hwai.pdfio import page_images

MAX_DESKEW_DEG = 5.0
INK_THRESHOLD = 215  # grey below this counts as printed ink
MARGIN_FRAC = 0.03
MAX_BLANK = 4
MIN_BLANK_AREA_FRAC = 0.05
DEFAULT_LINE_HEIGHT_PX = 75
MAX_LINE_HEIGHT_PX = 150
FRAME_AREA_FRAC = 0.5  # an enclosed area this big is the page border, not a writeable box
BOX_MAX_INK_FRAC = 0.02


class PageAnalysis(BaseModel):
    width: int
    height: int
    regions: list[Region]
    ink_mask_coverage: float


def prepare_page(img: Image.Image) -> Image.Image:
    """RGB page image after a simple deskew (up to 5 degrees). Analysis uses this frame."""
    return deskew_page(img.convert("RGB"), MAX_DESKEW_DEG).convert("RGB")


def _strokes(mask: np.ndarray, horizontal: bool, length: int) -> np.ndarray:
    """Pixels belonging to straight horizontal (or vertical) strokes of at least `length` px."""
    shape = (length, 1) if horizontal else (1, length)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, shape)
    out: np.ndarray = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    return out


def _find_boxes(
    mask: np.ndarray,
) -> tuple[list[tuple[int, int, int, int]], list[tuple[int, int, int, int]], np.ndarray]:
    """Closed, mostly empty rectangles. Returns (boxes, frames, structure_mask); a frame is an
    enclosed area so large it is the page border (kept only to ignore its edges)."""
    h, w = mask.shape
    struct = _strokes(mask, True, 30) | _strokes(mask, False, 30)
    walls = cv2.dilate(struct, np.ones((3, 3), np.uint8), iterations=2)
    free = (walls == 0).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(free, connectivity=4)
    boxes: list[tuple[int, int, int, int]] = []
    frames: list[tuple[int, int, int, int]] = []
    inner = mask.astype(bool) & (walls == 0)
    for i in range(1, n):
        x, y, bw, bh, area = (int(v) for v in stats[i])
        if x == 0 or y == 0 or x + bw >= w or y + bh >= h:
            continue  # reaches the page edge: not enclosed
        if bw < MIN_REGION_PX or bh < MIN_REGION_PX or area < 0.9 * bw * bh:
            continue
        bbox = (x, y, x + bw, y + bh)
        if area > FRAME_AREA_FRAC * w * h:
            frames.append(bbox)
            continue
        if inner[y : y + bh, x : x + bw].mean() <= BOX_MAX_INK_FRAC:
            boxes.append(bbox)
    return boxes, frames, struct


def _on_edge(seg: tuple[int, int, int], rect: tuple[int, int, int, int], tol: int = 10) -> bool:
    x0, x1, y = seg
    rx0, ry0, rx1, ry1 = rect
    return x0 >= rx0 - tol and x1 <= rx1 + tol and (abs(y - ry0) <= tol or abs(y - ry1) <= tol)


def _vertical_rules(mask: np.ndarray) -> np.ndarray:
    """Long vertical strokes (margin rules, box walls), slightly thickened. Structure, not text."""
    v = _strokes(mask, False, max(MIN_REGION_PX, int(0.06 * mask.shape[0])))
    out: np.ndarray = cv2.dilate(v, np.ones((1, 5), np.uint8), iterations=1)
    return out


def _find_line_segments(mask: np.ndarray) -> list[tuple[int, int, int]]:
    """Long thin horizontal strokes as (x0, x1, y), fragments of one line merged."""
    h, w = mask.shape
    gap = 3  # bridges antialiasing breaks only; text must not fuse into false lines
    closed = cv2.morphologyEx(
        mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (gap, 1))
    )
    long_strokes = _strokes(closed, True, max(MIN_REGION_PX, int(0.06 * w)))
    # A long vertical stroke (notebook margin, box wall) touches every rule it crosses and would
    # fuse them into one tall component; cut it out so each rule is judged on its own. The
    # pieces on either side are merged back below, so a line may span the margin.
    long_strokes = long_strokes & (1 - _vertical_rules(mask))
    max_thick = max(8, int(0.005 * max(w, h)))
    n, _, stats, _ = cv2.connectedComponentsWithStats(long_strokes, connectivity=8)
    segs: list[tuple[int, int, int]] = []
    for i in range(1, n):
        x, y, bw, bh, _area = (int(v) for v in stats[i])
        if bh <= max_thick:
            segs.append((x, x + bw, y + bh // 2))
    return merge_segments(segs, max_gap=max(12, int(0.03 * w)))


def _overlap(a: tuple[int, int, int], b: tuple[int, int, int]) -> bool:
    shared = min(a[1], b[1]) - max(a[0], b[0])
    return shared >= 0.5 * min(a[1] - a[0], b[1] - b[0])


def _line_regions(segs: list[tuple[int, int, int]], content_ink: np.ndarray) -> list[Region]:
    regions: list[Region] = []
    for i, seg in enumerate(segs):
        x0, x1, y = seg
        above = [s for s in segs[:i] if _overlap(s, seg) and s[2] < y]
        below = [s for s in segs[i + 1 :] if _overlap(s, seg) and s[2] > y]
        if above:
            lh = y - max(s[2] for s in above)
        elif below:
            lh = min(s[2] for s in below) - y
        else:
            lh = DEFAULT_LINE_HEIGHT_PX
        lh = min(lh, MAX_LINE_HEIGHT_PX)
        top = max(0, y - lh)
        # do not reach up into printed text sitting over this line
        window = content_ink[top : max(top, y - 3), x0:x1]
        if window.size:
            rows = np.flatnonzero(window.sum(axis=1) >= 2)
            if rows.size:
                top = top + int(rows[-1]) + 3
        regions.append(
            Region(
                id="",
                page=1,
                kind="line",
                bbox_px=(x0, top, x1, y),
                baseline_px=y,
                line_height_px=lh,
            )
        )
    return regions


def _largest_free_rect(free: np.ndarray) -> tuple[int, int, int, int, int]:
    """Largest axis-aligned all-True rectangle: (area, r0, c0, r1, c1), r1/c1 exclusive."""
    rows, cols = free.shape
    heights = [0] * cols
    best = (0, 0, 0, 0, 0)
    for r in range(rows):
        row = free[r]
        heights = [heights[c] + 1 if row[c] else 0 for c in range(cols)]
        stack: list[tuple[int, int]] = []  # (start column, height)
        for c in range(cols + 1):
            cur = heights[c] if c < cols else 0
            start = c
            while stack and stack[-1][1] >= cur:
                s, hh = stack.pop()
                area = hh * (c - s)
                if area > best[0]:
                    best = (area, r - hh + 1, s, r + 1, c)
                start = s
            stack.append((start, cur))
    return best


def _blank_regions(occupied: np.ndarray) -> list[Region]:
    """Up to four largest empty rectangles inside the page margin, avoiding `occupied` pixels."""
    h, w = occupied.shape
    f = max(1, max(h, w) // 320)
    hc, wc = -(-h // f), -(-w // f)
    padded = np.ones((hc * f, wc * f), dtype=bool)
    padded[:h, :w] = occupied
    mx, my = int(round(MARGIN_FRAC * w)), int(round(MARGIN_FRAC * h))
    padded[:my, :] = True
    padded[h - my :, :] = True
    padded[:, :mx] = True
    padded[:, w - mx :] = True
    grid = padded.reshape(hc, f, wc, f).any(axis=(1, 3))
    out: list[Region] = []
    for _ in range(MAX_BLANK):
        area, r0, c0, r1, c1 = _largest_free_rect(~grid)
        if area == 0:
            break
        x0, y0, x1, y1 = c0 * f, r0 * f, min(w, c1 * f), min(h, r1 * f)
        grid[r0:r1, c0:c1] = True
        if (
            x1 - x0 < MIN_REGION_PX
            or y1 - y0 < MIN_REGION_PX
            or (x1 - x0) * (y1 - y0) < MIN_BLANK_AREA_FRAC * w * h
        ):
            continue
        out.append(Region(id="", page=1, kind="blank", bbox_px=(x0, y0, x1, y1)))
    return out


def analyze_page(img: Image.Image | np.ndarray, page: int = 1) -> PageAnalysis:
    """Find writeable regions on one page image (already upright; see `prepare_page`)."""
    gray = to_gray(img)
    h, w = gray.shape
    mask = (gray < INK_THRESHOLD).astype(np.uint8)

    boxes, frames, _ = _find_boxes(mask)
    segs = [s for s in _find_line_segments(mask) if not any(_on_edge(s, r) for r in boxes + frames)]

    # ink that is not a ruled line: used to keep line regions off printed text
    line_px = np.zeros_like(mask)
    for x0, x1, y in _find_line_segments(mask):
        line_px[max(0, y - 6) : y + 7, x0:x1] = 1
    content = mask.astype(bool) & ~line_px.astype(bool) & ~_vertical_rules(mask).astype(bool)

    raw = _line_regions(segs, content)
    raw += [Region(id="", page=1, kind="box", bbox_px=b) for b in boxes]
    regions = finalize_regions(raw, w, h, page)

    occupied = cv2.dilate(mask, np.ones((13, 13), np.uint8)).astype(bool)
    for r in regions:
        x0, y0, x1, y1 = r.bbox_px
        occupied[y0:y1, x0:x1] = True
    blanks = _blank_regions(occupied)
    regions = finalize_regions(regions + blanks, w, h, page)
    return PageAnalysis(
        width=w, height=h, regions=regions, ink_mask_coverage=round(float(mask.mean()), 4)
    )


def analyze_pages(pages: list[Image.Image]) -> dict[str, Any]:
    """JSON-ready analysis of every page: `{"pages": [PageAnalysis, ...]}` (deterministic)."""
    return {
        "pages": [analyze_page(p, page=i + 1).model_dump(mode="json") for i, p in enumerate(pages)]
    }


def load_pages(path: str | Path) -> list[Image.Image]:
    """Page images (PDF pages at 150 DPI or the image itself), deskewed. The frame in which
    regions are expressed, and the one served by the page-image endpoint."""
    return [prepare_page(p) for p in page_images(path)]


KIND_COLORS = {"line": (0, 120, 255), "box": (230, 90, 0), "blank": (0, 160, 70)}


def draw_regions(img: Image.Image, regions: list[Region]) -> Image.Image:
    """Copy of `img` with a labelled rectangle per region (debug overlay)."""
    out = img.convert("RGB")
    draw = ImageDraw.Draw(out, "RGBA")
    font = ImageFont.load_default(size=max(12, out.width // 60))
    for r in regions:
        color = KIND_COLORS.get(r.kind, (200, 0, 200))
        draw.rectangle(r.bbox_px, outline=color, width=3, fill=(*color, 28))
        if r.baseline_px is not None:
            x0, _, x1, _ = r.bbox_px
            draw.line([(x0, r.baseline_px), (x1, r.baseline_px)], fill=color, width=2)
        x0, y0, _, _ = r.bbox_px
        draw.text((x0 + 4, y0 + 2), r.id, fill=color, font=font)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m hwai.page.analyze")
    parser.add_argument("file", type=Path)
    parser.add_argument("--overlay", type=Path, help="write a PNG with the regions drawn on it")
    parser.add_argument("--page", type=int, default=1, help="page for the overlay (1-based)")
    args = parser.parse_args(argv)
    pages = load_pages(args.file)
    result = analyze_pages(pages)
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    if args.overlay:
        idx = args.page - 1
        regs = [Region.model_validate(r) for r in result["pages"][idx]["regions"]]
        draw_regions(pages[idx], regs).save(args.overlay)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
