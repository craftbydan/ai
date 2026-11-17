from pathlib import Path

import pytest

from hwai.config import Settings


def test_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("RENDERER", "OCR", "DATA_DIR", "WEB_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.renderer == "fake"
    assert s.ocr == "fake"
    assert s.data_dir == Path("./data")
    assert s.web_base_url == "http://localhost:3000"
    assert s.agent_model == "claude-haiku-5-5"
    assert s.price_thb_per_document == 20
    assert s.max_pages_per_document == 10


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RENDERER", "onedm")
    assert Settings(_env_file=None).renderer == "onedm"  # type: ignore[call-arg]
