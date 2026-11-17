import pytest
from fastapi.testclient import TestClient

from hwai.config import get_settings
from hwai.main import create_app


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=False)
