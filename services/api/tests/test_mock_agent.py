"""AGENT=mock and the per-request test classifier header (end-to-end test switches)."""

import pytest
from fastapi.testclient import TestClient

from hwai.config import get_settings

from .conftest import FIXTURES


def _ready_hand(client: TestClient) -> None:
    with (FIXTURES / "hand_page_1.png").open("rb") as f:
        res = client.post(
            "/hand/documents",
            files={"file": ("hand_page_1.png", f)},
            data={"own_hand_confirmed": "true"},
        )
    assert res.status_code == 201


def _upload_card(client: TestClient, chat_id: str, headers: dict[str, str] | None = None) -> int:
    with (FIXTURES / "card.pdf").open("rb") as f:
        res = client.post(
            f"/chats/{chat_id}/files", files={"file": ("card.pdf", f)}, headers=headers or {}
        )
    return res.status_code


def test_mock_agent_renders_without_api_key(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT", "mock")
    get_settings.cache_clear()
    _ready_hand(client)
    chat_id = client.post("/chats").json()["id"]
    assert _upload_card(client, chat_id) == 201
    res = client.post(f"/chats/{chat_id}/messages", json={"text": "write happy birthday"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["render_version"] == 1
    assert client.get(body["preview_url"]).status_code == 200


def test_mock_agent_still_needs_a_ready_hand(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT", "mock")
    get_settings.cache_clear()
    chat_id = client.post("/chats").json()["id"]
    _upload_card(client, chat_id)
    res = client.post(f"/chats/{chat_id}/messages", json={"text": "hi"})
    assert res.status_code == 409 and res.json()["error"]["code"] == "hand_not_ready"


def test_mock_agent_ignored_in_production(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hwai.agent.loop import mock_agent_enabled

    monkeypatch.setenv("AGENT", "mock")
    monkeypatch.setenv("ENV", "production")
    get_settings.cache_clear()
    assert mock_agent_enabled() is False


def test_classifier_header_switches_kind_when_mock_is_on(client: TestClient) -> None:
    chat_id = client.post("/chats").json()["id"]
    assert _upload_card(client, chat_id, {"X-Test-Classifier": "mock:exam"}) == 422


def test_classifier_header_ignored_without_mock(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLASSIFIER", "real")
    get_settings.cache_clear()
    chat_id = client.post("/chats").json()["id"]
    # a real classifier is never steered by the header: card.pdf is plain, so it passes
    assert _upload_card(client, chat_id, {"X-Test-Classifier": "mock:exam"}) == 201


def test_list_chats_and_chat_detail_fields(client: TestClient) -> None:
    assert client.get("/chats").json() == []
    chat_id = client.post("/chats").json()["id"]
    listed = client.get("/chats").json()
    assert [c["id"] for c in listed] == [chat_id]
    detail = client.get(f"/chats/{chat_id}").json()
    assert detail["latest_render_version"] is None


def test_refused_file_carries_friendly_message(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLASSIFIER", "mock:exam")
    get_settings.cache_clear()
    chat_id = client.post("/chats").json()["id"]
    assert _upload_card(client, chat_id) == 422
    files = client.get(f"/chats/{chat_id}").json()["files"]
    assert files[0]["safety_status"] == "refused" and "exam" in files[0]["safety_message"]
