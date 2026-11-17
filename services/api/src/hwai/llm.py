"""Shared LLM plumbing: lazy Anthropic client (the injection point) and image helpers."""

import base64
import io
from typing import Any

from PIL import Image

from hwai.config import get_settings
from hwai.errors import ApiError

MAX_IMAGE_EDGE = 1200


class LazyLlmClient:
    """Resolves the real Anthropic client on first use, so a missing key only raises the
    503 when a model call is actually needed (after ownership/readiness/file checks)."""

    def __init__(self) -> None:
        self._client: Any = None

    @property
    def messages(self) -> Any:
        if self._client is None:
            settings = get_settings()
            if not settings.anthropic_api_key:
                raise ApiError(503, "agent_not_configured", "The chat assistant is not set up yet.")
            import anthropic

            self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        return self._client.messages


def get_llm_client() -> Any:
    """FastAPI dependency and injection point. Tests override it with a scripted fake.
    Never raises: the 503 is deferred to first use of `.messages`."""
    return LazyLlmClient()


def downscale(img: Image.Image, max_edge: int = MAX_IMAGE_EDGE) -> Image.Image:
    """Long edge <= max_edge, aspect kept (never upscales)."""
    scale = max_edge / max(img.size)
    if scale >= 1:
        return img
    return img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))))


def image_block(img: Image.Image, max_edge: int = MAX_IMAGE_EDGE) -> dict[str, Any]:
    buf = io.BytesIO()
    downscale(img.convert("RGB"), max_edge).save(buf, format="PNG", optimize=True)
    data = base64.b64encode(buf.getvalue()).decode()
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}}
