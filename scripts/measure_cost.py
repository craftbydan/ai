"""Measure rendering cost: seconds and baht per page of ~180 words with One-DM.

Run from the repo root (or anywhere):  python scripts/measure_cost.py
Needs: NVIDIA GPU, `make install-ml`, ONEDM_WEIGHTS_PATH and GPU_COST_THB_PER_HOUR.
Writes data/cost_report.json ({seconds_per_page, thb_per_page, ...}).
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import NoReturn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api" / "src"))

PAGES = 3
WORDS_PER_PAGE = 180
WARN_THB = 1.0
SAMPLE = (
    "the quick brown fox jumps over the lazy dog while seven happy children sing "
    "about warm summer days and good friends"
).split()


def fail(msg: str) -> NoReturn:
    print(f"measure_cost: {msg}", file=sys.stderr)
    sys.exit(2)


def main() -> None:
    os.environ["RENDERER"] = "onedm"
    from hwai.config import get_settings

    settings = get_settings()
    if settings.gpu_cost_thb_per_hour <= 0:
        fail("GPU_COST_THB_PER_HOUR is not set (price per hour of this GPU in THB).")
    if not settings.onedm_weights_path or not Path(settings.onedm_weights_path).is_file():
        fail("ONEDM_WEIGHTS_PATH is not set or the file does not exist.")

    from hwai.errors import ApiError
    from hwai.render.fixture_style import fixture_style_ref
    from hwai.render.onedm import OneDMRenderer

    renderer = OneDMRenderer()
    style = [fixture_style_ref()]
    words = [SAMPLE[i % len(SAMPLE)] for i in range(WORDS_PER_PAGE)]
    try:
        print("loading model and warming up ...")
        renderer.render_words(words[:4], style, seed=0)  # load + warm up, not timed
        start = time.perf_counter()
        for page in range(PAGES):
            renderer.render_words(words, style, seed=1000 * (page + 1))
        elapsed = time.perf_counter() - start
    except ApiError as exc:
        fail(f"[{exc.code}] {exc.message}")

    seconds_per_page = elapsed / PAGES
    thb_per_page = seconds_per_page / 3600 * settings.gpu_cost_thb_per_hour
    report = {
        "seconds_per_page": round(seconds_per_page, 3),
        "thb_per_page": round(thb_per_page, 4),
        "pages": PAGES,
        "words_per_page": WORDS_PER_PAGE,
        "gpu_cost_thb_per_hour": settings.gpu_cost_thb_per_hour,
        "sampling_steps": settings.onedm_sampling_steps,
        "batch_size": settings.onedm_batch_size,
    }
    out = settings.data_dir / "cost_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"seconds per page: {seconds_per_page:.2f}")
    print(f"THB per page:     {thb_per_page:.3f}")
    if thb_per_page > WARN_THB:
        print(f"WARNING: {thb_per_page:.2f} THB per page is above {WARN_THB} THB; margin is negative.")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
