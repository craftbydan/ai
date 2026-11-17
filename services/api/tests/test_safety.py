"""Prompt 9: safety rules (classifier mocked via CLASSIFIER=mock:<kind>)."""

import copy
import io
from collections.abc import Iterator
from typing import Any

import pikepdf
import pypdfium2 as pdfium
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas
from sqlalchemy import select

from hwai.agent.loop import get_llm_client
from hwai.config import get_settings
from hwai.db import new_session
from hwai.models import ChatFile, Render
from hwai.page.analyze import analyze_page
from hwai.render.fake import FONT_PATH
from hwai.safety.classify import classify_document, parse_answer
from hwai.safety.rules import REFUSALS, SIGNATURE_REFUSAL
from hwai.safety.signature import looks_like_signature_region, looks_like_signature_text

from .conftest import FIXTURES
from .test_agent import FakeClient, _placement, _renders, _use, text, tool


def _set_classifier(monkeypatch: pytest.MonkeyPatch, spec: str) -> None:
    monkeypatch.setenv("CLASSIFIER", spec)
    get_settings.cache_clear()


def _upload_card(client: TestClient, chat_id: str) -> Any:
    with (FIXTURES / "card.pdf").open("rb") as f:
        return client.post(f"/chats/{chat_id}/files", files={"file": ("card.pdf", f)})


def _ready_hand(client: TestClient) -> None:
    with (FIXTURES / "hand_page_1.png").open("rb") as f:
        res = client.post(
            "/hand/documents",
            files={"file": ("h.png", f)},
            data={"own_hand_confirmed": "true"},
        )
    assert res.status_code == 201
    assert client.get("/hand").json()["status"] == "ready"


@pytest.fixture
def ready(client: TestClient) -> Iterator[TestClient]:
    _ready_hand(client)
    yield client
    client.app.dependency_overrides.clear()  # type: ignore[attr-defined]


# 1. each refusal kind -> 422 with its own message
@pytest.mark.parametrize("kind", sorted(REFUSALS))
def test_each_refusal_kind_is_422_with_own_message(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    _set_classifier(monkeypatch, f"mock:{kind}")
    chat_id = client.post("/chats").json()["id"]
    res = _upload_card(client, chat_id)
    assert res.status_code == 422, res.text
    err = res.json()["error"]
    assert err["code"] == "document_refused"
    assert err["message"] == REFUSALS[kind]
    assert len({m for m in REFUSALS.values()}) == len(REFUSALS) == 6
    with new_session() as db:
        cf = db.scalars(select(ChatFile).where(ChatFile.chat_id == chat_id)).one()
    assert cf.safety_status == "refused" and cf.safety_reason == kind
    assert cf.analysis_json is None  # nothing about the content is kept


def test_exam_message_mentions_exam(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_classifier(monkeypatch, "mock:exam")
    chat_id = client.post("/chats").json()["id"]
    assert "exam" in _upload_card(client, chat_id).json()["error"]["message"]


# 2. a normal card passes
def test_normal_card_uploads_renders_and_exports(ready: TestClient) -> None:
    client = ready
    chat_id = client.post("/chats").json()["id"]
    res = _upload_card(client, chat_id)
    assert res.status_code == 201, res.text
    assert res.json()["safety_status"] == "ok"
    r = client.post(f"/chats/{chat_id}/render", json={"placements": [_placement()]})
    assert r.status_code == 200, r.text
    e = client.post(f"/chats/{chat_id}/export", params={"version": 1, "format": "pdf"})
    assert e.status_code == 200


def _signature_page() -> Image.Image:
    img = Image.new("RGB", (1240, 1754), "white")
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(str(FONT_PATH), 22)
    d.line([(200, 1400), (700, 1400)], fill="black", width=3)
    d.text((200, 1410), "Name / Date", font=font, fill="black")
    d.line([(200, 800), (900, 800)], fill="black", width=3)  # an ordinary line, no caption
    return img


def test_signature_heuristic_pixels() -> None:
    page = _signature_page()
    lines = [r for r in analyze_page(page, page=1).regions if r.kind == "line"]
    flags = {r.baseline_px: looks_like_signature_region(r, page) for r in lines}
    assert flags == {800: False, 1400: True}


def test_signature_heuristic_ignores_fixtures() -> None:
    from hwai.pdfio import page_images

    for name in ("card.pdf", "planner.pdf"):
        for img in page_images(FIXTURES / name):
            assert not any(
                looks_like_signature_region(r, img) for r in analyze_page(img, 1).regions
            )


def test_signature_text() -> None:
    assert looks_like_signature_text("sign it Dan")
    assert looks_like_signature_text("Please write my signature at the bottom")
    assert looks_like_signature_text("Dan", own_name="dan")
    assert not looks_like_signature_text("Happy birthday Dan")
    assert not looks_like_signature_text("Dan", own_name=None)


# 3. render on a signature region -> 403 signature_blocked
def test_render_on_signature_region_is_403(ready: TestClient) -> None:
    client = ready
    chat_id = client.post("/chats").json()["id"]
    buf = io.BytesIO()
    _signature_page().save(buf, format="PNG")
    res = client.post(f"/chats/{chat_id}/files", files={"file": ("p.png", buf.getvalue())})
    assert res.status_code == 201, res.text
    regions = client.get(f"/chats/{chat_id}/files/{res.json()['id']}/analysis").json()["pages"][0][
        "regions"
    ]
    sig = [r for r in regions if r["signature"]]
    ok = [r for r in regions if not r["signature"]]
    assert len(sig) == 1 and ok
    r = client.post(f"/chats/{chat_id}/render", json={"placements": [_placement(sig[0]["id"])]})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "signature_blocked"
    assert _renders(chat_id) == []
    r2 = client.post(f"/chats/{chat_id}/render", json={"placements": [_placement(ok[0]["id"])]})
    assert r2.status_code == 200


# 4. agent: "sign it Dan" -> polite refusal, no render
def test_agent_sign_it_dan_refuses_without_render(ready: TestClient) -> None:
    client = ready
    chat_id = client.post("/chats").json()["id"]
    assert _upload_card(client, chat_id).status_code == 201
    fake = FakeClient(lambda kw, n: [tool("render", {"placements": [_placement()]})])
    _use(client, fake)
    res = client.post(f"/chats/{chat_id}/messages", json={"text": "sign it Dan"})
    assert res.status_code == 200, res.text
    assert res.json()["reply"] == SIGNATURE_REFUSAL
    assert res.json()["render_version"] is None
    assert _renders(chat_id) == []


def test_agent_render_tool_refuses_signature_placement(ready: TestClient) -> None:
    client = ready
    chat_id = client.post("/chats").json()["id"]
    assert _upload_card(client, chat_id).status_code == 201
    with new_session() as db:
        cf = db.scalars(select(ChatFile).where(ChatFile.chat_id == chat_id)).one()
        analysis = copy.deepcopy(cf.analysis_json)
        rid = analysis["pages"][0]["regions"][0]["id"]
        analysis["pages"][0]["regions"][0]["signature"] = True
        cf.analysis_json = analysis
        db.commit()

    def script(kwargs: dict[str, Any], n: int) -> list[Any]:
        if n == 1:
            return [tool("render", {"placements": [_placement(rid)]})]
        res = kwargs["messages"][-1]["content"][0]
        assert res["is_error"] and "signature" in res["content"][0]["text"]
        return [tool("finish", {"message": "Sorry, I can't write on a signature line."})]

    _use(client, FakeClient(script))
    res = client.post(f"/chats/{chat_id}/messages", json={"text": "write Dan on the first line"})
    assert res.status_code == 200 and res.json()["render_version"] is None
    assert "signature" in res.json()["reply"].lower()
    assert _renders(chat_id) == []


def test_agent_system_prompt_has_rules(ready: TestClient) -> None:
    client = ready
    chat_id = client.post("/chats").json()["id"]
    _upload_card(client, chat_id)
    fake = FakeClient(lambda kw, n: [tool("finish", {"message": "ok"})])
    _use(client, fake)
    client.post(f"/chats/{chat_id}/messages", json={"text": "write hi"})
    assert "Never write a signature" in fake.calls[0]["system"]
    assert "exams" in fake.calls[0]["system"]


# 5. a refused file cannot receive messages or renders
def test_refused_file_blocks_messages_and_renders(
    ready: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = ready
    _set_classifier(monkeypatch, "mock:cheque")
    chat_id = client.post("/chats").json()["id"]
    assert _upload_card(client, chat_id).status_code == 422
    fake = FakeClient(lambda kw, n: [tool("render", {"placements": [_placement()]})])
    _use(client, fake)
    res = client.post(f"/chats/{chat_id}/messages", json={"text": "write hi"})
    assert res.status_code in (403, 409)
    assert res.json()["error"]["code"] == "file_refused"
    assert res.json()["error"]["message"] == REFUSALS["cheque"]
    assert fake.calls == []
    r = client.post(f"/chats/{chat_id}/render", json={"placements": [_placement()]})
    assert r.status_code == 403 and r.json()["error"]["code"] == "file_refused"
    with new_session() as db:
        assert db.scalars(select(Render).where(Render.chat_id == chat_id)).all() == []


# 6. exported PNG / PDF carry marks, one page and many
def _multipage_pdf(pages: int) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(595, 842))
    for i in range(pages):
        c.setFont("Helvetica", 12)
        c.drawString(72, 700, f"Dear friend, page {i + 1}")
        c.line(72, 600, 400, 600)
        c.showPage()
    c.save()
    return buf.getvalue()


@pytest.mark.parametrize("pages", [1, 3])
def test_exports_carry_marks(ready: TestClient, pages: int) -> None:
    client = ready
    chat_id = client.post("/chats").json()["id"]
    up = client.post(f"/chats/{chat_id}/files", files={"file": ("m.pdf", _multipage_pdf(pages))})
    assert up.status_code == 201, up.text
    regs = client.get(f"/chats/{chat_id}/files/{up.json()['id']}/analysis").json()["pages"][0][
        "regions"
    ]
    r = client.post(f"/chats/{chat_id}/render", json={"placements": [_placement(regs[0]["id"])]})
    assert r.status_code == 200, r.text

    pdf = client.post(f"/chats/{chat_id}/export", params={"version": 1, "format": "pdf"})
    assert pdf.status_code == 200
    with pikepdf.open(io.BytesIO(pdf.content)) as doc:
        assert len(doc.pages) == pages
        assert "AI-generated" in str(doc.docinfo["/Keywords"])
        assert "handwriting-ai" in str(doc.docinfo["/Subject"])
    rendered = pdfium.PdfDocument(pdf.content)
    for i in range(pages):  # visible footer on every page (bottom-right, grey ink)
        img = rendered[i].render(scale=150 / 72).to_pil().convert("L")
        footer = img.crop((img.width - 400, img.height - 60, img.width, img.height))
        assert footer.getextrema()[0] < 200, f"no footer on page {i + 1}"
    for n in range(1, pages + 1):
        png = client.post(
            f"/chats/{chat_id}/export", params={"version": 1, "format": "png", "page": n}
        )
        assert png.status_code == 200
        im = Image.open(io.BytesIO(png.content))
        assert im.info["ai_generated"] == "true"
        assert (
            im.convert("L")
            .crop((im.width - 400, im.height - 60, im.width, im.height))
            .getextrema()[0]
            < 200
        )


# 7. own-hand box still required; rule shown
def test_hand_upload_without_box_rejected_and_rule_shown(client: TestClient) -> None:
    with (FIXTURES / "hand_page_1.png").open("rb") as f:
        res = client.post("/hand/documents", files={"file": ("h.png", f)})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "own_hand_not_confirmed"
    assert client.get("/hand").json()["own_hand_confirmed_at"] is None
    with (FIXTURES / "hand_page_1.png").open("rb") as f:
        ok = client.post(
            "/hand/documents", files={"file": ("h.png", f)}, data={"own_hand_confirmed": "true"}
        )
    assert ok.status_code == 201
    assert ok.json()["own_hand_confirmed_at"] is not None
    assert "own handwriting" in ok.json()["own_hand_statement"]
    hand = client.get("/hand").json()
    assert hand["own_hand_confirmed_at"] is not None and "own" in hand["own_hand_statement"]


# classifier unit tests (real path with a scripted client, and fallback)
def _client_answering(answer: str) -> Any:
    return FakeClient(lambda kw, n: [text(answer)])


def test_classifier_parses_strict_json(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_classifier(monkeypatch, "real")
    img = Image.new("RGB", (400, 500), "white")
    c = _client_answering('{"kind": "exam", "confidence": 0.9, "signature_boxes": []}')
    doc = classify_document([img], c)
    assert (doc.kind, doc.source) == ("exam", "llm")
    assert parse_answer("not json") is None
    assert parse_answer('{"kind": "banana", "confidence": 1}') is None


def test_classifier_unparseable_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_classifier(monkeypatch, "real")
    plain = Image.new("RGB", (1240, 1754), "white")
    assert classify_document([plain], _client_answering("sorry?")).kind == "ok"
    dense = Image.new("RGB", (1240, 1754), "white")
    d = ImageDraw.Draw(dense)
    f = ImageFont.truetype(str(FONT_PATH), 16)
    for i in range(60):
        d.text(
            (100, 100 + i * 25),
            "The quick brown fox jumps over the lazy dog and more",
            font=f,
            fill="black",
        )
    out = classify_document([dense], _client_answering("sorry?"))
    assert out.kind != "ok" and out.source == "fallback"
    low = classify_document([dense], _client_answering('{"kind":"ok","confidence":0.3}'))
    assert low.kind != "ok"


def test_no_api_key_real_classifier_does_not_crash(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    _set_classifier(monkeypatch, "real")
    chat_id = client.post("/chats").json()["id"]
    assert get_llm_client is not None
    res = _upload_card(client, chat_id)
    assert res.status_code == 201, res.text  # plain card passes the local fallback


def test_mock_switch_ignored_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "production")
    _set_classifier(monkeypatch, "mock:exam")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    get_settings.cache_clear()
    out = classify_document([Image.new("RGB", (800, 1000), "white")])
    assert out.source == "fallback"
