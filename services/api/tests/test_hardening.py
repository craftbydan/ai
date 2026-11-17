"""Bad input never crashes the server: clean 4xx JSON errors, and /health still answers."""

import io
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from reportlab.pdfgen import canvas

from hwai.config import get_settings
from hwai.pdfio import MAX_IMAGE_PIXELS, MAX_PAGES

from .conftest import FIXTURES


def _pdf(pages: int, size: tuple[int, int] = (200, 200)) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=size)
    for _ in range(pages):
        c.drawString(20, 20, "x")
        c.showPage()
    c.save()
    return buf.getvalue()


def _huge_png() -> bytes:
    """~400 megapixels, but a few hundred KB: an all-white 1-bit PNG (a classic bomb shape)."""
    img = Image.new("1", (20000, 20000), 1)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _assert_clean(res: Any, status: int | None = None) -> None:
    assert 400 <= res.status_code < 500, (res.status_code, res.text)
    if status is not None:
        assert res.status_code == status, res.text
    err = res.json()["error"]
    assert isinstance(err["code"], str) and isinstance(err["message"], str) and err["message"]
    assert set(err) >= {"code", "message"}


def _healthy(client: TestClient) -> None:
    res = client.get("/health")
    assert res.status_code == 200 and res.json()["status"] == "ok"


def _ready_hand(client: TestClient) -> None:
    with (FIXTURES / "hand_page_1.png").open("rb") as f:
        res = client.post(
            "/hand/documents",
            files={"file": ("h.png", f)},
            data={"own_hand_confirmed": "true"},
        )
    assert res.status_code == 201
    assert client.get("/hand").json()["status"] == "ready"


def _hand_upload(client: TestClient, data: bytes, name: str = "x.bin") -> Any:
    return client.post(
        "/hand/documents", files={"file": (name, data)}, data={"own_hand_confirmed": "true"}
    )


def _chat_upload(client: TestClient, chat_id: str, data: bytes, name: str = "x.bin") -> Any:
    return client.post(f"/chats/{chat_id}/files", files={"file": (name, data)})


BAD_FILES: dict[str, tuple[bytes, int, str]] = {
    "zero_byte": (b"", 400, "unsupported_file"),
    "corrupted_pdf": (b"%PDF-1.7\n1 0 obj << /Broken\n garbage \x00\xff", 400, "unsupported_file"),
    "truncated_png": (b"\x89PNG\r\n\x1a\n" + b"\x00" * 20, 400, "unsupported_file"),
    "text_file": (b"hello world", 400, "unsupported_file"),
    "pdf_31_pages": (_pdf(MAX_PAGES + 1), 400, "too_many_pages"),
    "huge_dimensions": (_huge_png(), 400, "image_too_large"),
    "huge_pdf_page": (_pdf(1, (40000, 40000)), 400, "image_too_large"),
    "oversized": (b"%PDF-1.7\n" + b"0" * (20 * 1024 * 1024 + 1), 413, "file_too_large"),
}


@pytest.mark.parametrize("case", sorted(BAD_FILES))
def test_hand_upload_rejects_bad_files(client: TestClient, case: str) -> None:
    data, status, code = BAD_FILES[case]
    res = _hand_upload(client, data)
    _assert_clean(res, status)
    assert res.json()["error"]["code"] == code
    _healthy(client)
    assert client.get("/hand").json()["documents"] == []  # nothing half-stored


@pytest.mark.parametrize("case", sorted(BAD_FILES))
def test_chat_upload_rejects_bad_files(client: TestClient, case: str, data_dir: Any) -> None:
    chat_id = client.post("/chats").json()["id"]
    data, status, code = BAD_FILES[case]
    res = _chat_upload(client, chat_id, data)
    _assert_clean(res, status)
    assert res.json()["error"]["code"] == code
    _healthy(client)
    assert client.get(f"/chats/{chat_id}").json()["files"] == []
    assert not [p for p in data_dir.rglob("*") if p.is_file() and p.suffix != ".sqlite"]


def test_thirty_page_pdf_is_accepted(client: TestClient) -> None:
    chat_id = client.post("/chats").json()["id"]
    assert _chat_upload(client, chat_id, _pdf(MAX_PAGES)).status_code == 201


def test_pillow_pixel_limit_is_set_explicitly() -> None:
    assert Image.MAX_IMAGE_PIXELS == MAX_IMAGE_PIXELS


def test_curl_example_empty_file_is_400_json(client: TestClient) -> None:
    res = client.post(
        "/hand/documents", files={"file": ("null", b"")}, data={"own_hand_confirmed": "true"}
    )
    _assert_clean(res, 400)
    _healthy(client)


def test_missing_file_part_is_clean_422(client: TestClient) -> None:
    res = client.post("/hand/documents", data={"own_hand_confirmed": "true"})
    _assert_clean(res, 422)
    _healthy(client)


# --- messages and render text -------------------------------------------------------------------


@pytest.fixture
def chat_ready(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("AGENT", "mock")
    get_settings.cache_clear()
    _ready_hand(client)
    chat_id = client.post("/chats").json()["id"]
    with (FIXTURES / "card.pdf").open("rb") as f:
        assert (
            client.post(f"/chats/{chat_id}/files", files={"file": ("c.pdf", f)}).status_code == 201
        )
    return chat_id


@pytest.mark.parametrize("text", ["", " ", "   \n\t  ", "​"[:0], "　　"])
def test_empty_or_blank_message_is_422(client: TestClient, chat_ready: str, text: str) -> None:
    res = client.post(f"/chats/{chat_ready}/messages", json={"text": text})
    _assert_clean(res, 422)
    assert res.json()["error"]["code"] == "validation_error"
    _healthy(client)


def test_message_too_long_is_422(client: TestClient, chat_ready: str) -> None:
    res = client.post(f"/chats/{chat_ready}/messages", json={"text": "a" * 2001})
    _assert_clean(res, 422)
    _healthy(client)


@pytest.mark.parametrize(
    "text",
    [
        "Happy birthday \U0001f382\U0001f389 Mom!",
        "café naïve über 你好 สวัสดี مرحبا",
        "é ‮ rtl \u0000 nul ퟿",
        "a" * 1900,  # one extremely long word
    ],
)
def test_unusual_message_text_never_crashes(client: TestClient, chat_ready: str, text: str) -> None:
    res = client.post(f"/chats/{chat_ready}/messages", json={"text": text})
    assert res.status_code < 500, res.text
    if res.status_code >= 400:
        _assert_clean(res)
    _healthy(client)


def _first_region(client: TestClient, chat_id: str) -> str:
    detail = client.get(f"/chats/{chat_id}").json()
    fid = detail["files"][0]["id"]
    regions = client.get(f"/chats/{chat_id}/files/{fid}/analysis").json()["pages"][0]["regions"]
    return str(regions[0]["id"])


@pytest.mark.parametrize(
    "text",
    [
        "Happy birthday \U0001f382\U0001f389",
        "你好 สวัสดี مرحبا",
        "x" * 2000,
        "supercalifragilistic" * 90,
        "",
        "   ",
        "line one\nline two\ttabbed",
    ],
)
def test_render_endpoint_unusual_text_never_crashes(
    client: TestClient, chat_ready: str, text: str
) -> None:
    rid = _first_region(client, chat_ready)
    body = {"placements": [{"region_id": rid, "text": text, "seed": 3}]}
    res = client.post(f"/chats/{chat_ready}/render", json=body)
    assert res.status_code < 500, res.text
    if res.status_code >= 400:
        _assert_clean(res)
    else:
        assert client.get(res.json()["preview_url"]).status_code == 200
    _healthy(client)


def test_render_text_over_limit_is_422(client: TestClient, chat_ready: str) -> None:
    rid = _first_region(client, chat_ready)
    body = {"placements": [{"region_id": rid, "text": "a" * 2001}]}
    _assert_clean(client.post(f"/chats/{chat_ready}/render", json=body), 422)
    _healthy(client)
