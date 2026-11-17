"""Environment settings. Config only through env vars (see .env.example)."""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_base_url: str = "http://localhost:8000"
    web_base_url: str = "http://localhost:3000"
    env: str = "dev"
    data_dir: Path = Path("./data")
    renderer: str = "fake"  # fake | onedm
    ocr: str = "fake"  # fake | trocr
    fake_ocr_truth_path: Path | None = None  # FakeOcr ground truth (tests only)
    secret_key: str = ""
    agent: str = "real"  # real | mock (mock ignored when ENV=production)
    classifier: str = "real"  # real | mock:<kind> (mock ignored when ENV=production)

    anthropic_api_key: str = ""
    agent_model: str = "claude-haiku-5-5"
    # Cost estimate only (USD per million tokens, USD->THB); set to the model's real price.
    agent_usd_per_mtok_in: float = 1.0
    agent_usd_per_mtok_out: float = 5.0
    usd_thb: float = 36.0

    onedm_repo_dir: Path = Path("./vendor/One-DM")
    onedm_weights_path: str = ""
    onedm_vae_path: str = "runwayml/stable-diffusion-v1-5"  # HF id or local dir with vae/
    onedm_sampling_steps: int = 50
    onedm_batch_size: int = 32
    gpu_cost_thb_per_hour: float = 0.0

    dev_user: bool = False  # ENV=dev only: act as the seeded dev user when nobody is logged in
    stripe_secret_key: str = ""  # TEST keys only (sk_test_); anything else fails startup
    stripe_webhook_secret: str = ""
    billing: str = "on"  # on | off (off is honoured only when ENV=dev)
    pricing_mode: str = "per_document"  # per_document | per_page
    price_thb_per_document: int = 20
    price_thb_per_page: int = 1
    max_pages_per_document: int = 10

    @field_validator("secret_key", "stripe_secret_key", "stripe_webhook_secret", mode="after")
    @classmethod
    def _placeholder_is_unset(cls, value: str) -> str:
        """`<YOUR_...>` values copied from .env.example count as not set."""
        value = value.strip()
        return "" if value.startswith("<") and value.endswith(">") else value


@lru_cache
def get_settings() -> Settings:
    return Settings()
