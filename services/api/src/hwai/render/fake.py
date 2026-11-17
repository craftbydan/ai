"""FakeRenderer: OFL handwriting font plus seeded jitter. Always available, no GPU."""

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from hwai.render.base import Renderer, StyleRef, WordImage
from hwai.render.jitter import apply_jitter

FONT_PATH = Path(__file__).parent / "assets" / "Caveat.ttf"


def _empty() -> WordImage:
    return WordImage(image=Image.new("RGBA", (1, 1), (0, 0, 0, 0)), baseline_px=0)


class FakeRenderer(Renderer):
    def render_word(
        self, word: str, style_refs: list[StyleRef], seed: int, size_px: int
    ) -> WordImage:
        if not word.strip() or size_px < 1:
            return _empty()
        rng = np.random.default_rng(seed)
        size = max(1, round(size_px * (1 + float(rng.uniform(-0.04, 0.04)))))
        font = ImageFont.truetype(str(FONT_PATH), size)
        ascent, descent = font.getmetrics()
        pad = max(4, size // 4)
        width = int(font.getlength(word)) + 2 * pad
        wobble = max(1.0, size * 0.03)
        height = ascent + descent + 2 * pad + int(2 * wobble)
        base_y = pad + int(wobble) + ascent

        # Ink colour: dark blue-black with a seeded darkness level.
        dark = int(rng.integers(20, 70))
        ink = (dark, dark, min(255, dark + 25), 255)

        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        for i, ch in enumerate(word):
            if ch.isspace():
                continue
            x = pad + font.getlength(word[:i])
            dy = float(rng.normal(0, wobble / 2))
            draw.text((x, base_y + dy), ch, font=font, fill=ink, anchor="ls")

        angle = float(rng.uniform(-2.0, 2.0))
        canvas = canvas.rotate(
            angle, resample=Image.Resampling.BICUBIC, center=(pad, base_y), expand=False
        )
        canvas = apply_jitter(canvas, int(rng.integers(0, 2**31 - 1)), strength=0.5)

        bbox = canvas.getchannel("A").getbbox()
        if bbox is None:
            return _empty()
        left, top, right, bottom = bbox
        cropped = canvas.crop((left, top, right, bottom))
        return WordImage(image=cropped, baseline_px=max(0, base_y - top))


def main() -> None:
    parser = argparse.ArgumentParser(description="FakeRenderer demo")
    parser.add_argument("--demo", required=True, help="text to render")
    parser.add_argument("--out", required=True, help="output PNG path")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--size", type=int, default=64)
    args = parser.parse_args()

    from hwai.text.splitter import EnglishSplitter

    renderer = FakeRenderer()
    words = [
        (u, renderer.render_word(u, [], args.seed * 1000 + i, args.size))
        for i, u in enumerate(EnglishSplitter().units(args.demo))
        if u.strip()
    ]
    gap = args.size // 4
    base = max((w.baseline_px for _, w in words), default=0)
    below = max((w.image.height - w.baseline_px for _, w in words), default=0)
    total_w = sum(w.image.width for _, w in words) + gap * (len(words) + 1)
    sheet = Image.new("RGBA", (max(total_w, 1), base + below + 2 * gap), (255, 255, 255, 255))
    x = gap
    for _, w in words:
        sheet.alpha_composite(w.image, (x, gap + base - w.baseline_px))
        x += w.image.width + gap
    sheet.convert("RGB").save(args.out)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
