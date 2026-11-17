"""DELETE /chats/{id}, DELETE /hand (ownership + nothing left on disk) and concurrent users."""

import io
import threading
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from PIL import Image, ImageChops
from reportlab.pdfgen import canvas
from sqlalchemy import func, select

from hwai.db import new_session
from hwai.models import (
    Chat,
    ChatFile,
    Export,
    HandDocument,
    Message,
    Render,
    WordSample,
)

from .conftest import FIXTURES, new_client, signup


def _files(data_dir: Path) -> list[Path]:
    return [p for p in data_dir.rglob("*") if p.is_file() and p.suffix != ".sqlite"]


def _upload_hand(client: TestClient) -> None:
    with (FIXTURES / "hand_page_1.png").open("rb") as f:
        res = client.post(
            "/hand/documents",
            files={"file": ("h.png", f)},
            data={"own_hand_confirmed": "true"},
        )
    assert res.status_code == 201, res.text


def _card_chat(client: TestClient, pdf: Path | None = None) -> str:
    chat_id = str(client.post("/chats").json()["id"])
    with (pdf or FIXTURES / "card.pdf").open("rb") as f:
        res = client.post(f"/chats/{chat_id}/files", files={"file": ("c.pdf", f)})
    assert res.status_code == 201, res.text
    return chat_id


def _render(client: TestClient, chat_id: str, text: str, seed: int = 1) -> Any:
    detail = client.get(f"/chats/{chat_id}").json()
    fid = detail["files"][0]["id"]
    regions = client.get(f"/chats/{chat_id}/files/{fid}/analysis").json()["pages"][0]["regions"]
    body = {"placements": [{"region_id": regions[0]["id"], "text": text, "seed": seed}]}
    return client.post(f"/chats/{chat_id}/render", json=body)


def _count(model: Any) -> int:
    with new_session() as db:
        return int(db.scalar(select(func.count()).select_from(model)) or 0)


def _two_page_pdf(path: Path) -> Path:
    c = canvas.Canvas(str(path), pagesize=(595, 842))
    for _ in range(2):
        c.drawString(100, 700, "card")
        c.showPage()
    c.save()
    return path


def test_delete_chat_removes_files_renders_exports_and_rows(
    client: TestClient, data_dir: Path, tmp_path: Path
) -> None:
    _upload_hand(client)
    hand_files = _files(data_dir)
    keep = _card_chat(client)  # a second chat must be untouched
    chat_id = _card_chat(client, _two_page_pdf(tmp_path / "two.pdf"))
    r = _render(client, chat_id, "Hello")
    assert r.status_code == 200, r.text
    assert client.post(f"/chats/{chat_id}/export?version=1&format=pdf").status_code == 200
    assert client.post(f"/chats/{chat_id}/export?version=1&format=png").status_code == 200
    with new_session() as db:
        db.add(Message(chat_id=chat_id, role="user", content_json={"text": "hi"}))
        db.commit()
    before = _files(data_dir)
    assert len(before) > len(hand_files) + 4  # target, previews (2 pages), 2 exports, other chat

    assert client.delete(f"/chats/{chat_id}").status_code == 204
    assert client.get(f"/chats/{chat_id}").status_code == 404
    assert client.delete(f"/chats/{chat_id}").status_code == 404

    left = _files(data_dir)
    # Only the hand files and the untouched second chat's target file remain.
    assert len(left) == len(hand_files) + 1
    with new_session() as db:
        assert db.scalar(select(func.count()).select_from(Chat)) == 1
        assert db.scalars(select(ChatFile.chat_id)).all() == [keep]
        assert db.scalar(select(func.count()).select_from(Render)) == 0
        assert db.scalar(select(func.count()).select_from(Export)) == 0
        assert db.scalar(select(func.count()).select_from(Message)) == 0
    assert client.get(f"/chats/{keep}").status_code == 200


def test_delete_chat_ownership_is_404_and_changes_nothing(
    client: TestClient, data_dir: Path
) -> None:
    chat_id = _card_chat(client)
    files = _files(data_dir)
    other = signup(new_client(), "other@example.com")
    # `other` has a real account cookie, so it is a different user than the dev user.
    assert other.delete(f"/chats/{chat_id}").status_code == 404
    assert _files(data_dir) == files
    assert _count(Chat) == 1
    assert client.get(f"/chats/{chat_id}").status_code == 200


def test_delete_hand_removes_samples_crops_documents(client: TestClient, data_dir: Path) -> None:
    _upload_hand(client)
    assert client.get("/hand").json()["status"] == "ready"
    assert _count(WordSample) > 0 and _count(HandDocument) == 1
    chat_id = _card_chat(client)
    target_files = [p for p in _files(data_dir) if p.parent.name == "target"]

    assert client.delete("/hand").status_code == 204

    assert _count(WordSample) == 0 and _count(HandDocument) == 0
    assert not [p for p in _files(data_dir) if p.parent.name in ("crops", "hand")]
    assert [p for p in _files(data_dir) if p.parent.name == "target"] == target_files
    hand = client.get("/hand").json()
    assert hand["status"] == "empty"
    assert hand["documents"] == [] and hand["sample_count"] == 0
    assert hand["own_hand_confirmed_at"] is None
    assert client.get(f"/chats/{chat_id}").status_code == 200
    assert client.delete("/hand").status_code == 204  # idempotent
    _upload_hand(client)  # and a fresh upload works afterwards
    assert client.get("/hand").json()["status"] == "ready"


def test_delete_hand_only_touches_own_hand(client: TestClient, data_dir: Path) -> None:
    other = signup(new_client(), "other@example.com")
    _upload_hand(other)
    _upload_hand(client)
    samples = _count(WordSample)
    assert other.get("/hand").json()["status"] == "ready"
    assert client.delete("/hand").status_code == 204
    assert other.get("/hand").json()["status"] == "ready"
    assert 0 < _count(WordSample) < samples
    assert other.delete("/hand").status_code == 204
    assert _count(WordSample) == 0
    assert not [p for p in _files(data_dir) if p.parent.name in ("crops", "hand")]


def test_delete_hand_with_no_hand_is_ok(client: TestClient) -> None:
    assert client.delete("/hand").status_code == 204


# --- concurrency ---------------------------------------------------------------------------------


def _run_parallel(*jobs: Any) -> list[Any]:
    barrier = threading.Barrier(len(jobs))
    results: list[Any] = [None] * len(jobs)
    errors: list[BaseException] = []

    def work(i: int, job: Any) -> None:
        try:
            barrier.wait(timeout=10)
            results[i] = job()
        except BaseException as exc:  # noqa: BLE001 - re-raised below, never swallowed
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(i, j)) for i, j in enumerate(jobs)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)
    if errors:
        raise errors[0]
    return results


def test_two_simultaneous_ingestions_do_not_mix(client: TestClient, data_dir: Path) -> None:
    a = signup(new_client(), "a@example.com")
    b = signup(new_client(), "b@example.com")
    ra, rb = _run_parallel(lambda: _upload_hand(a), lambda: _upload_hand(b))
    ha, hb = a.get("/hand").json(), b.get("/hand").json()
    assert ha["status"] == hb["status"] == "ready"
    assert ha["id"] != hb["id"]
    with new_session() as db:
        for hand, other in ((ha, hb), (hb, ha)):
            samples = db.scalars(select(WordSample).where(WordSample.hand_id == hand["id"])).all()
            assert len(samples) == hand["sample_count"] > 0
            doc_ids = {d["id"] for d in hand["documents"]}
            assert {s.document_id for s in samples} == doc_ids
            assert not doc_ids & {d["id"] for d in other["documents"]}
            prefixes = {s.crop_path.split("/")[0] for s in samples}
            assert len(prefixes) == 1  # all crops of one hand live under exactly one user dir
        assert len({s.crop_path.split("/")[0] for s in db.scalars(select(WordSample))}) == 2


def _img(client: TestClient, url: str) -> Image.Image:
    res = client.get(url)
    assert res.status_code == 200
    return Image.open(io.BytesIO(res.content)).convert("RGB")


def test_two_simultaneous_renders_do_not_cross_contaminate(client: TestClient) -> None:
    users = [signup(new_client(), f"u{i}@example.com") for i in range(2)]
    for u in users:
        _upload_hand(u)
    chats = [_card_chat(u) for u in users]
    texts = ["Happy birthday Alice", "Congratulations Bob on everything"]

    results = _run_parallel(
        lambda: _render(users[0], chats[0], texts[0], seed=11),
        lambda: _render(users[1], chats[1], texts[1], seed=22),
    )
    assert [r.status_code for r in results] == [200, 200]
    concurrent = [_img(u, r.json()["preview_url"]) for u, r in zip(users, results, strict=True)]

    # The seeded fake renderer is deterministic: a calm, sequential render of the same text and
    # seed must be pixel-identical, so nothing from the other user's render leaked in.
    for u, chat_id, text, seed, img in zip(users, chats, texts, (11, 22), concurrent, strict=True):
        again = _render(u, chat_id, text, seed=seed)
        assert again.status_code == 200
        assert ImageChops.difference(img, _img(u, again.json()["preview_url"])).getbbox() is None
    # And the two previews differ from each other (they carry different text).
    assert ImageChops.difference(concurrent[0], concurrent[1]).getbbox() is not None
    # Each user sees only their own chat.
    assert users[0].get(f"/chats/{chats[1]}").status_code == 404
    assert users[1].get(f"/chats/{chats[0]}").status_code == 404
