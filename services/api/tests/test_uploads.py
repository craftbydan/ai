import io
from pathlib import Path

from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from hwai.auth import current_user
from hwai.db import make_engine
from hwai.main import create_app
from hwai.models import HandDocument, User

from .conftest import FIXTURES


def _files(data_dir: Path) -> list[Path]:
    return [
        p
        for p in data_dir.rglob("*")
        if p.is_file() and p.suffix != ".sqlite" and p.parent.name != "crops"
    ]


def _upload(client: TestClient, name: str, confirmed: str = "true"):  # type: ignore[no-untyped-def]
    with (FIXTURES / name).open("rb") as f:
        return client.post(
            "/hand/documents", files={"file": (name, f)}, data={"own_hand_confirmed": confirmed}
        )


def test_hand_upload_confirmed_creates_row_and_file(client: TestClient, data_dir: Path) -> None:
    res = _upload(client, "hand_page_1.png")
    assert res.status_code == 201
    assert res.json()["page_count"] == 1
    with Session(make_engine()) as db:
        assert db.scalar(select(func.count()).select_from(HandDocument)) == 1
    stored = _files(data_dir)
    assert len(stored) == 1
    assert stored[0].suffix == ".png" and stored[0].stem != "hand_page_1"
    hand = client.get("/hand").json()
    assert hand["own_hand_confirmed_at"] is not None
    assert len(hand["documents"]) == 1


def test_unchecked_own_hand_box_returns_400(client: TestClient, data_dir: Path) -> None:
    res = _upload(client, "hand_page_1.png", confirmed="false")
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "own_hand_not_confirmed"
    with Session(make_engine()) as db:
        assert db.scalar(select(func.count()).select_from(HandDocument)) == 0
    assert _files(data_dir) == []
    assert client.get("/hand").json()["status"] == "empty"


def test_text_file_renamed_png_is_rejected(client: TestClient, data_dir: Path) -> None:
    res = client.post(
        "/hand/documents",
        files={"file": ("x.png", io.BytesIO(b"just some text, not an image"))},
        data={"own_hand_confirmed": "true"},
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "unsupported_file"
    assert _files(data_dir) == []


def test_31_page_pdf_is_rejected(client: TestClient, data_dir: Path) -> None:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for _ in range(31):
        c.showPage()
    c.save()
    chat_id = client.post("/chats").json()["id"]
    res = client.post(
        f"/chats/{chat_id}/files", files={"file": ("big.pdf", io.BytesIO(buf.getvalue()))}
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "too_many_pages"
    assert _files(data_dir) == []


def test_chat_file_upload_pdfs_have_one_page(client: TestClient, data_dir: Path) -> None:
    chat_id = client.post("/chats").json()["id"]
    for name in ("card.pdf", "planner.pdf"):
        with (FIXTURES / name).open("rb") as f:
            res = client.post(f"/chats/{chat_id}/files", files={"file": (name, f)})
        assert res.status_code == 201
        assert res.json()["page_count"] == 1
        assert res.json()["kind"] == "pdf"
    detail = client.get(f"/chats/{chat_id}").json()
    assert len(detail["files"]) == 2
    assert detail["messages"] == []
    assert all(p.parent.name == "target" for p in _files(data_dir))


def test_other_user_cannot_read_chat(client: TestClient) -> None:
    chat_id = client.post("/chats").json()["id"]
    assert client.get(f"/chats/{chat_id}").status_code == 200

    with Session(make_engine()) as db:
        other = User(email="other@local")
        db.add(other)
        db.commit()
        other_id = other.id

    app2 = create_app()

    def _other() -> User:
        with Session(make_engine()) as db:
            return db.get_one(User, other_id)

    app2.dependency_overrides[current_user] = _other
    c2 = TestClient(app2, raise_server_exceptions=False)
    assert c2.get(f"/chats/{chat_id}").status_code == 404
    with (FIXTURES / "card.pdf").open("rb") as f:
        assert c2.post(f"/chats/{chat_id}/files", files={"file": ("c.pdf", f)}).status_code == 404
