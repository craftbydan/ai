"""Region type and the pure helpers that tidy raw detections into stable regions."""

from typing import Literal

from pydantic import BaseModel, field_validator

MIN_REGION_PX = 40

RegionKind = Literal["line", "box", "blank"]


class Region(BaseModel):
    """A writeable area on a page, in 150-DPI pixels, top-left origin, x1/y1 exclusive."""

    id: str
    page: int
    kind: RegionKind
    bbox_px: tuple[int, int, int, int]  # x0, y0, x1, y1
    baseline_px: int | None = None
    line_height_px: int | None = None
    signature: bool = False  # set by safety.signature; never writeable

    @field_validator("bbox_px")
    @classmethod
    def _ordered(cls, v: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        if v[2] < v[0] or v[3] < v[1]:
            raise ValueError("bbox_px must be (x0, y0, x1, y1) with x1>=x0 and y1>=y0")
        return v

    @property
    def width(self) -> int:
        return self.bbox_px[2] - self.bbox_px[0]

    @property
    def height(self) -> int:
        return self.bbox_px[3] - self.bbox_px[1]


def merge_segments(
    segments: list[tuple[int, int, int]], max_gap: int, y_tol: int = 3
) -> list[tuple[int, int, int]]:
    """Merge fragments of one ruled line. Segments are (x0, x1, y); fragments whose y differs by
    at most `y_tol` and whose horizontal gap is at most `max_gap` become one segment."""
    out: list[tuple[int, int, int]] = []
    for x0, x1, y in sorted(segments, key=lambda s: (s[2], s[0], s[1])):
        for i, (ox0, ox1, oy) in enumerate(out):
            if abs(oy - y) <= y_tol and x0 <= ox1 + max_gap and x1 >= ox0 - max_gap:
                out[i] = (min(ox0, x0), max(ox1, x1), round((oy + y) / 2))
                break
        else:
            out.append((x0, x1, y))
    return sorted(out, key=lambda s: (s[2], s[0], s[1]))


def finalize_regions(regions: list[Region], width: int, height: int, page: int) -> list[Region]:
    """Clamp to the page, drop anything under 40 px either way, sort top-to-bottom and assign
    stable ids like `p1-line-03` (numbered per kind in reading order)."""
    kept: list[Region] = []
    for r in regions:
        x0, y0, x1, y1 = r.bbox_px
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(width, x1), min(height, y1)
        if x1 - x0 < MIN_REGION_PX or y1 - y0 < MIN_REGION_PX:
            continue
        kept.append(r.model_copy(update={"bbox_px": (x0, y0, x1, y1), "page": page}))
    kept.sort(key=lambda r: (r.bbox_px[1], r.bbox_px[0], r.kind, r.bbox_px[3], r.bbox_px[2]))
    counts: dict[str, int] = {}
    out: list[Region] = []
    for r in kept:
        counts[r.kind] = counts.get(r.kind, 0) + 1
        out.append(r.model_copy(update={"id": f"p{page}-{r.kind}-{counts[r.kind]:02d}"}))
    return out
