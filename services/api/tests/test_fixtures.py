import json
from pathlib import Path

from PIL import Image

FIX = Path(__file__).parent / "fixtures"


def test_fixture_files_exist() -> None:
    for name in ("hand_page_1.png", "hand_page_1.json", "card.pdf", "planner.pdf", "blank.png"):
        assert (FIX / name).stat().st_size > 0, name
    assert (FIX / "Caveat.ttf").exists()
    assert (FIX / "OFL.txt").exists()


def test_hand_page_json_matches() -> None:
    data = json.loads((FIX / "hand_page_1.json").read_text())
    assert len(data["lines"]) == 12
    assert all(line["text"] for line in data["lines"])
    with Image.open(FIX / "hand_page_1.png") as img:
        assert img.size == (1240, 1754)


def test_pdfs_open() -> None:
    import pypdfium2 as pdfium

    card = pdfium.PdfDocument(str(FIX / "card.pdf"))
    assert len(card) == 1
    w, h = card[0].get_size()
    assert round(w) == 360 and round(h) == 504  # 5x7 inch
    assert len(pdfium.PdfDocument(str(FIX / "planner.pdf"))) == 1
