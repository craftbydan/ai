"""Style crop taken from the synthetic fixture page (never a real person's handwriting)."""

from pathlib import Path

import numpy as np
from PIL import Image

from hwai.render.base import StyleRef

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures"


def fixture_style_ref(max_width: int = 400) -> StyleRef:
    """First words of the first line of fixtures/hand_page_1.png, cropped to the ink."""
    import json

    page = Image.open(FIXTURES / "hand_page_1.png").convert("L")
    meta = json.loads((FIXTURES / "hand_page_1.json").read_text())
    line = meta["lines"][0]
    base = int(line["baseline_px"])
    band = np.asarray(page)[max(0, base - 110) : base + 50]
    ys, xs = np.nonzero(band < 200)
    y0 = max(0, base - 110)
    top, bottom, left = int(ys.min()), int(ys.max()) + 1, int(xs.min())
    crop = page.crop((left, y0 + top, left + max_width, y0 + bottom))
    return StyleRef(text=str(line["text"]).split()[0], image=crop)
