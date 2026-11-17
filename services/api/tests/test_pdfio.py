from hwai.pdfio import page_images

from .conftest import FIXTURES


def test_page_images_pdf_at_150_dpi() -> None:
    pages = page_images(FIXTURES / "card.pdf")
    assert len(pages) == 1
    assert pages[0].mode == "RGB"
    assert pages[0].width > 500


def test_page_images_single_image_is_one_page() -> None:
    pages = page_images(FIXTURES / "hand_page_1.png")
    assert len(pages) == 1
    assert pages[0].size == (1240, 1754)
