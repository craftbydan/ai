from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hwai import models  # noqa: F401  (register tables)
from hwai.config import get_settings
from hwai.db import Base, make_engine
from hwai.main import create_app

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Every test gets its own DATA_DIR and a fresh database."""
    data_dir = tmp_path / "data"
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("CLASSIFIER", "mock:ok")  # tests never call the real classifier
    # Tests that are not about accounts/billing run as the dev user with payment off. Auth and
    # billing tests flip these (DEV_USER=0, BILLING=on) and log in for real via `signup()`.
    monkeypatch.setenv("DEV_USER", "1")
    monkeypatch.setenv("BILLING", "off")
    for name in ("SECRET_KEY", "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET"):
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    engine = make_engine()
    Base.metadata.create_all(engine)
    engine.dispose()
    yield data_dir
    get_settings.cache_clear()


@pytest.fixture
def data_dir(_isolated_data_dir: Path) -> Path:
    return _isolated_data_dir


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=False)


PASSWORD = "correct horse battery"


def signup(client: TestClient, email: str, password: str = PASSWORD) -> TestClient:
    """Create an account on `client` (it keeps the session cookie)."""
    res = client.post("/auth/signup", json={"email": email, "password": password})
    assert res.status_code == 201, res.text
    return client


def new_client() -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=False)
