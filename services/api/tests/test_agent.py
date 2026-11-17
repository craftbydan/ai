"""Chat agent tests with a scripted fake LLM client (no API key needed)."""

import copy
import io
import json
from collections.abc import Callable, Iterator
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from hwai.agent.loop import downscale, get_llm_client
from hwai.auth import current_user
from hwai.config import get_settings
from hwai.db import make_engine, new_session
from hwai.main import create_app
from hwai.models import Message, Render, User

from .conftest import FIXTURES

Script = Callable[[dict[str, Any], int], list[Any]]


def tool(name: str, inp: dict[str, Any], id: str = "tu1") -> Any:
    return SimpleNamespace(type="tool_use", id=id, name=name, input=inp)


def text(t: str) -> Any:
    return SimpleNamespace(type="text", text=t)


class FakeClient:
    """Scripted stand-in for anthropic.Anthropic: `.messages.create(**kwargs)`."""

    def __init__(self, script: Script) -> None:
        self.script = script
        self.calls: list[dict[str, Any]] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs: Any) -> Any:
        self.calls.append(copy.deepcopy(kwargs))
        content = self.script(kwargs, len(self.calls))
        return SimpleNamespace(
            content=content,
            usage=SimpleNamespace(input_tokens=1000, output_tokens=50),
            stop_reason="tool_use",
        )


def _placement(rid: str = "p1-blank-01", size: float = 1.0) -> dict[str, Any]:
    return {
        "region_id": rid,
        "text": "Happy birthday",
        "align": "center",
        "size_scale": size,
        "slant_deg": 0,
        "jitter": 0.5,
        "seed": 1,
    }


def _last_placements(kwargs: dict[str, Any]) -> list[dict[str, Any]]:
    for block in kwargs["messages"][-1]["content"]:
        if block.get("type") == "text" and block["text"].startswith("Last render"):
            parsed: list[dict[str, Any]] = json.loads(block["text"].split("placements: ", 1)[1])
            return parsed
    raise AssertionError("last placements missing from context")


def _first_message_script(kwargs: dict[str, Any], n: int) -> list[Any]:
    last = kwargs["messages"][-1]["content"]
    if last[0].get("type") == "tool_result":
        return [tool("finish", {"message": "Done."}, "tu2")]
    if "bigger" in last[-1]["text"]:
        placements = _last_placements(kwargs)
        for p in placements:
            p["size_scale"] = round(p["size_scale"] * 1.25, 2)
        return [tool("render", {"placements": placements})]
    return [tool("render", {"placements": [_placement()]})]


@pytest.fixture
def agent_client(client: TestClient) -> Iterator[tuple[TestClient, str]]:
    with (FIXTURES / "hand_page_1.png").open("rb") as f:
        res = client.post(
            "/hand/documents",
            files={"file": ("hand_page_1.png", f)},
            data={"own_hand_confirmed": "true"},
        )
    assert res.status_code == 201
    assert client.get("/hand").json()["status"] == "ready"
    chat_id = client.post("/chats").json()["id"]
    with (FIXTURES / "card.pdf").open("rb") as f:
        assert (
            client.post(f"/chats/{chat_id}/files", files={"file": ("card.pdf", f)}).status_code
            == 201
        )
    yield client, chat_id
    client.app.dependency_overrides.clear()  # type: ignore[attr-defined]


def _use(client: TestClient, fake: FakeClient) -> None:
    client.app.dependency_overrides[get_llm_client] = lambda: fake  # type: ignore[attr-defined]


def _renders(chat_id: str) -> list[Render]:
    with new_session() as db:
        return list(
            db.scalars(
                select(Render).where(Render.chat_id == chat_id).order_by(Render.version)
            ).all()
        )


def test_write_centered_then_make_it_bigger(agent_client: tuple[TestClient, str]) -> None:
    client, chat_id = agent_client
    fake = FakeClient(_first_message_script)
    _use(client, fake)

    res = client.post(
        f"/chats/{chat_id}/messages", json={"text": "write Happy birthday centered on the card"}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["render_version"] == 1 and body["reply"]
    png = client.get(body["preview_url"])
    assert png.status_code == 200 and Image.open(io.BytesIO(png.content)).format == "PNG"
    v1 = _renders(chat_id)
    assert len(v1) == 1 and v1[0].placements_json[0]["align"] == "center"
    with new_session() as db:
        rows = db.scalars(select(Message).where(Message.chat_id == chat_id)).all()
        calls = [
            b
            for m in rows
            if m.role == "assistant"
            for b in m.content_json["content"]
            if b["type"] == "tool_use" and b["name"] == "render"
        ]
    assert len(calls) == 1

    res2 = client.post(f"/chats/{chat_id}/messages", json={"text": "make it bigger"})
    assert res2.status_code == 200, res2.text
    assert res2.json()["render_version"] == 2
    v = _renders(chat_id)
    assert v[1].placements_json[0]["size_scale"] > v[0].placements_json[0]["size_scale"]


def test_unknown_region_is_a_tool_error_not_a_crash(agent_client: tuple[TestClient, str]) -> None:
    client, chat_id = agent_client

    def script(kwargs: dict[str, Any], n: int) -> list[Any]:
        if n == 1:
            return [tool("render", {"placements": [_placement("p9-nope-99")]})]
        if n == 2:
            result = kwargs["messages"][-1]["content"][0]
            assert result["is_error"] is True
            assert "does not exist" in result["content"][0]["text"]
            return [tool("render", {"placements": [_placement()]})]
        return [tool("finish", {"message": "Done."})]

    fake = FakeClient(script)
    _use(client, fake)
    res = client.post(f"/chats/{chat_id}/messages", json={"text": "write hi"})
    assert res.status_code == 200, res.text
    assert res.json()["render_version"] == 1
    assert len(fake.calls) == 3


def test_call_cap_returns_apology(agent_client: tuple[TestClient, str]) -> None:
    client, chat_id = agent_client
    fake = FakeClient(lambda kw, n: [tool("list_regions", {"page": 1}, f"tu{n}")])
    _use(client, fake)
    res = client.post(f"/chats/{chat_id}/messages", json={"text": "loop forever"})
    assert res.status_code == 200
    assert len(fake.calls) == 6
    assert "sorry" in res.json()["reply"].lower()
    assert res.json()["render_version"] is None


def test_hand_not_ready_is_409(client: TestClient) -> None:
    chat_id = client.post("/chats").json()["id"]
    with (FIXTURES / "card.pdf").open("rb") as f:
        client.post(f"/chats/{chat_id}/files", files={"file": ("card.pdf", f)})
    fake = FakeClient(lambda kw, n: [tool("finish", {"message": "x"})])
    _use(client, fake)
    res = client.post(f"/chats/{chat_id}/messages", json={"text": "hi"})
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "hand_not_ready"
    assert fake.calls == []


def test_no_file_is_friendly_400(agent_client: tuple[TestClient, str]) -> None:
    client, _ = agent_client
    empty = client.post("/chats").json()["id"]
    _use(client, FakeClient(lambda kw, n: [tool("finish", {"message": "x"})]))
    res = client.post(f"/chats/{empty}/messages", json={"text": "hi"})
    assert res.status_code == 400 and res.json()["error"]["code"] == "no_file"


def test_every_message_row_has_token_counts_and_tool_calls(
    agent_client: tuple[TestClient, str],
) -> None:
    client, chat_id = agent_client
    _use(client, FakeClient(_first_message_script))
    client.post(f"/chats/{chat_id}/messages", json={"text": "write Happy birthday"})
    with new_session() as db:
        rows = db.scalars(select(Message).where(Message.chat_id == chat_id)).all()
    assert {r.role for r in rows} == {"user", "assistant", "tool"}
    for r in rows:
        u = r.content_json["usage"]
        assert {"input_tokens", "output_tokens", "est_thb"} <= u.keys()
    assistants = [r for r in rows if r.role == "assistant"]
    assert sum(r.content_json["usage"]["input_tokens"] for r in assistants) == 2000
    assert any(r.content_json["usage"]["est_thb"] > 0 for r in assistants)


def test_page_images_are_downscaled() -> None:
    assert max(downscale(Image.new("RGB", (1275, 1650))).size) == 1200
    assert downscale(Image.new("RGB", (400, 300))).size == (400, 300)


@pytest.fixture
def no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    get_settings.cache_clear()


def _ready_hand(client: TestClient) -> None:
    with (FIXTURES / "hand_page_1.png").open("rb") as f:
        res = client.post(
            "/hand/documents",
            files={"file": ("hand_page_1.png", f)},
            data={"own_hand_confirmed": "true"},
        )
    assert res.status_code == 201


def _err(res: Any, status: int, code: str) -> None:
    assert res.status_code == status, res.text
    assert res.json()["error"]["code"] == code


def test_no_api_key_gives_clean_error(agent_client: tuple[TestClient, str], no_key: None) -> None:
    client, chat_id = agent_client
    res = client.post(f"/chats/{chat_id}/messages", json={"text": "hi"})
    _err(res, 503, "agent_not_configured")
    with new_session() as db:
        assert db.scalars(select(Message).where(Message.chat_id == chat_id)).all() == []


def test_no_key_unready_hand_is_409(client: TestClient, no_key: None) -> None:
    chat_id = client.post("/chats").json()["id"]
    with (FIXTURES / "card.pdf").open("rb") as f:
        client.post(f"/chats/{chat_id}/files", files={"file": ("card.pdf", f)})
    _err(client.post(f"/chats/{chat_id}/messages", json={"text": "hi"}), 409, "hand_not_ready")


def test_no_key_ready_hand_without_file_is_400(client: TestClient, no_key: None) -> None:
    _ready_hand(client)
    chat_id = client.post("/chats").json()["id"]
    _err(client.post(f"/chats/{chat_id}/messages", json={"text": "hi"}), 400, "no_file")


def test_no_key_other_users_chat_is_404(agent_client: tuple[TestClient, str], no_key: None) -> None:
    client, chat_id = agent_client
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
    _err(c2.post(f"/chats/{chat_id}/messages", json={"text": "hi"}), 404, "not_found")
