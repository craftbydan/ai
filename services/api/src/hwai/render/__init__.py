"""Handwriting renderers. Choose one with `get_renderer()` (env `RENDERER=fake|onedm`)."""

from hwai.config import get_settings
from hwai.render.base import Renderer, StyleRef, WordImage

__all__ = ["Renderer", "StyleRef", "WordImage", "get_renderer"]


def get_renderer() -> Renderer:
    name = get_settings().renderer
    if name == "fake":
        from hwai.render.fake import FakeRenderer

        return FakeRenderer()
    if name == "onedm":
        from hwai.render.onedm import get_onedm_renderer

        return get_onedm_renderer()
    raise ValueError(f"Unknown RENDERER: {name!r} (expected 'fake' or 'onedm')")
