import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from hwai.db import new_session
from hwai.hand.ocr import FakeOcr, get_ocr
from hwai.hand.profile import style_refs_for
from hwai.hand.segment import find_lines, split_words
from hwai.models import WordSample
from hwai.storage import absolute_path

FIXTURES = Path(__file__).parent / "fixtures"
TRUTH = json.loads((FIXTURES / "hand_page_1.json").read_text())


def _upload(client: TestClient, name: str) -> None:
    with (FIXTURES / name).open("rb") as f:
        res = client.post(
            "/hand/documents", files={"file": (name, f)}, data={"own_hand_confirmed": "true"}
        )
    assert res.status_code == 201


def test_find_lines_matches_ground_truth_line_count() -> None:
    lines = find_lines(Image.open(FIXTURES / "hand_page_1.png"))
    assert abs(len(lines) - len(TRUTH["lines"])) <= 1


def test_most_words_get_a_crop(client: TestClient) -> None:
    _upload(client, "hand_page_1.png")
    expected = sum(len(line["text"].split()) for line in TRUTH["lines"])
    with new_session() as db:
        count = len(db.scalars(select(WordSample)).all())
    assert count >= 0.8 * expected
    hand = client.get("/hand").json()
    assert hand["sample_count"] == count


def test_fixture_page_becomes_ready_with_valid_crops(client: TestClient) -> None:
    _upload(client, "hand_page_1.png")
    hand = client.get("/hand").json()
    assert hand["status"] == "ready"
    assert hand["sample_count"] >= 20
    assert hand["documents"][0]["status"] == "done"
    with new_session() as db:
        samples = db.scalars(select(WordSample)).all()
    for s in samples:
        with Image.open(absolute_path(s.crop_path)) as im:
            assert im.width > 8 and im.height > 8
            assert (im.width, im.height) == (s.width, s.height)


def test_blank_page_fails_with_not_enough_ink(client: TestClient) -> None:
    _upload(client, "blank.png")
    hand = client.get("/hand").json()
    assert hand["status"] == "failed"
    assert hand["status_reason"] == "not_enough_ink"
    assert "handwriting" in hand["status_message"]
    assert hand["sample_count"] == 0


def test_style_refs_seeds_give_different_orderings(client: TestClient) -> None:
    _upload(client, "hand_page_1.png")
    hand_id = client.get("/hand").json()["id"]
    a = [r.text for r in style_refs_for(hand_id, k=12, seed=1)]
    b = [r.text for r in style_refs_for(hand_id, k=12, seed=2)]
    again = [r.text for r in style_refs_for(hand_id, k=12, seed=1)]
    assert a != b
    assert a == again


def test_segment_imports_without_torch() -> None:
    assert "torch" not in sys.modules
    assert "transformers" not in sys.modules
    assert split_words(Image.new("L", (100, 40), 255)) == []


def test_get_ocr_selected_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from hwai.config import get_settings

    monkeypatch.setenv("OCR", "fake")
    get_settings.cache_clear()
    assert isinstance(get_ocr(), FakeOcr)
    monkeypatch.setenv("OCR", "nope")
    get_settings.cache_clear()
    with pytest.raises(ValueError):
        get_ocr()
