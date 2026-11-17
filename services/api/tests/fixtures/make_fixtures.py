"""Generate deterministic synthetic fixtures (run twice -> byte-identical files).

Outputs next to this script: hand_page_1.png, hand_page_1.json, card.pdf,
planner.pdf, blank.png. Uses the OFL font Caveat.ttf; no real handwriting.
"""

import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

HERE = Path(__file__).resolve().parent
FONT_PATH = HERE / "Caveat.ttf"
SEED = 20261117

PAGE_W, PAGE_H = 1240, 1754  # A4 at 150 DPI

SENTENCES = [
    "The quick brown fox jumps over the lazy dog.",
    "Pack my box with five dozen liquor jugs.",
    "Happy birthday, I hope your day is wonderful.",
    "Thank you so much for the lovely gift.",
    "We are meeting at the station at seven.",
    "Please bring warm clothes and a good book.",
    "My favourite season is autumn with golden leaves.",
    "A small step today makes a big journey tomorrow.",
    "Remember to water the plants before you leave.",
    "The market sells fresh bread, honey and apples.",
    "She wrote a long letter to her oldest friend.",
    "Every morning begins with a warm cup of tea.",
]


def make_hand_page() -> None:
    rng = random.Random(SEED)
    font = ImageFont.truetype(str(FONT_PATH), 64)
    img = Image.new("L", (PAGE_W, PAGE_H), 255)
    draw = ImageDraw.Draw(img)
    top, pitch, left = 200, 120, 110
    lines = []
    for i, text in enumerate(SENTENCES):
        baseline = top + i * pitch + rng.randint(-4, 4)
        x = float(left)
        drift = 0.0
        for ch in text:
            drift += rng.uniform(-1.5, 1.5)
            drift = max(-10.0, min(10.0, drift))
            y = baseline + drift
            draw.text((x, y), ch, font=font, fill=rng.randint(10, 50), anchor="ls")
            x += font.getlength(ch) + rng.uniform(-0.5, 1.5)
        lines.append({"line": i + 1, "text": text, "baseline_px": baseline})
    img.save(HERE / "hand_page_1.png", optimize=False)
    (HERE / "hand_page_1.json").write_text(
        json.dumps({"width": PAGE_W, "height": PAGE_H, "lines": lines}, indent=2) + "\n"
    )


def _canvas(path: Path, size: tuple[float, float]) -> canvas.Canvas:
    return canvas.Canvas(str(path), pagesize=size, invariant=1, pageCompression=0)


def make_card() -> None:
    w, h = 5 * inch, 7 * inch
    c = _canvas(HERE / "card.pdf", (w, h))
    c.setStrokeColorRGB(0.2, 0.2, 0.2)
    c.setLineWidth(2)
    c.rect(0.3 * inch, 0.3 * inch, w - 0.6 * inch, h - 0.6 * inch)
    c.setFont("Helvetica", 14)
    c.drawString(0.7 * inch, h - 1.2 * inch, "To:")
    c.setLineWidth(1)
    c.line(1.1 * inch, h - 1.22 * inch, w - 0.7 * inch, h - 1.22 * inch)
    c.save()


def make_planner() -> None:
    w, h = 8.27 * inch, 11.69 * inch
    c = _canvas(HERE / "planner.pdf", (w, h))
    c.setFont("Helvetica-Bold", 18)
    c.drawString(0.8 * inch, h - 0.9 * inch, "Weekly Planner")
    c.setLineWidth(0.8)
    c.setStrokeColorRGB(0.4, 0.4, 0.4)
    y = h - 1.6 * inch
    for _ in range(10):
        c.line(0.8 * inch, y, w - 0.8 * inch, y)
        y -= 0.45 * inch
    c.setLineWidth(1.2)
    box_w = (w - 2.0 * inch) / 2
    for i in range(2):
        c.rect(0.8 * inch + i * (box_w + 0.4 * inch), 1.0 * inch, box_w, 2.2 * inch)
    c.save()


def make_blank() -> None:
    Image.new("RGB", (PAGE_W, PAGE_H), (255, 255, 255)).save(HERE / "blank.png")


def main() -> None:
    make_hand_page()
    make_card()
    make_planner()
    make_blank()


if __name__ == "__main__":
    main()
