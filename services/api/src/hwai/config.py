"""Environment settings. Config only through env vars (see .env.example)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_base_url: str = "http://localhost:8000"
    web_base_url: str = "http://localhost:3000"
    env: str = "dev"
    data_dir: Path = Path("./data")
    renderer: str = "fake"  # fake | onedm
    ocr: str = "fake"  # fake | trocr
    secret_key: str = ""

    anthropic_api_key: str = ""
    agent_model: str = "claude-haiku-5-5"

    onedm_repo_dir: Path = Path("./vendor/One-DM")
    onedm_weights_path: str = ""
    onedm_vae_path: str = "runwayml/stable-diffusion-v1-5"  # HF id or local dir with vae/
    onedm_sampling_steps: int = 50
    onedm_batch_size: int = 32
    gpu_cost_thb_per_hour: float = 0.0

    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    price_thb_per_document: int = 20
    max_pages_per_document: int = 10


@lru_cache
def get_settings() -> Settings:
    return Settings()
