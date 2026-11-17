"""Renderer contract. The One-DM renderer (Prompt 4) fills in the same interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from PIL import Image


@dataclass(frozen=True)
class StyleRef:
    """One reference word cut-out from the user's own handwriting."""

    text: str
    image: Image.Image


@dataclass(frozen=True)
class WordImage:
    """RGBA word image on a transparent background plus the baseline offset.

    `baseline_px` is the distance in pixels from the top of the image to the baseline.
    """

    image: Image.Image
    baseline_px: int


class Renderer(ABC):
    @abstractmethod
    def render_word(
        self, word: str, style_refs: list[StyleRef], seed: int, size_px: int
    ) -> WordImage:
        """Render `word` as handwriting. Must be deterministic for a given seed."""
