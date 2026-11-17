from fastapi import FastAPI
from fastapi.testclient import TestClient

from hwai.main import create_app


def test_health_ok(client: TestClient) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "renderer": "fake", "ocr": "fake"}


def test_unhandled_exception_uses_standard_error_shape() -> None:
    app: FastAPI = create_app()

    @app.get("/__boom")
    def boom() -> None:  # test-only route
        raise RuntimeError("secret detail must not leak")

    res = TestClient(app, raise_server_exceptions=False).get("/__boom")
    assert res.status_code == 500
    body = res.json()
    assert body["error"]["code"] == "internal"
    assert "secret detail" not in body["error"]["message"]


def test_not_found_uses_standard_error_shape(client: TestClient) -> None:
    res = client.get("/nope")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "http_404"


def test_cors_allows_web_origin(client: TestClient) -> None:
    res = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert res.headers["access-control-allow-origin"] == "http://localhost:3000"
