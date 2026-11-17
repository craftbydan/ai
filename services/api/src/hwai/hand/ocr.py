"""Handwriting OCR behind the `OcrEngine` interface. Chosen by env `OCR=fake|trocr`."""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from hwai.config import get_settings


@dataclass(frozen=True)
class OcrResult:
    text: str
    confidence: float


class OcrEngine(ABC):
    def start_page(self) -> None:  # noqa: B027  (optional hook)
        """Called before the lines of a new page are read, top to bottom."""

    @abstractmethod
    def read_line(self, image: Image.Image) -> OcrResult:
        """Read one line of handwriting."""


DEFAULT_TRUTH = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "hand_page_1.json"


class FakeOcr(OcrEngine):
    """Test double: returns the ground-truth lines of `hand_page_1.json` in order.

    Lines are served in reading order and restart at every `start_page()`. Only
    selected by `OCR=fake`; never used in a real OCR path.
    """

    def __init__(self, truth_path: Path | None = None) -> None:
        path = truth_path or get_settings().fake_ocr_truth_path or DEFAULT_TRUTH
        data = json.loads(Path(path).read_text())
        self._lines: list[str] = [str(line["text"]) for line in data["lines"]]
        self._next = 0

    def start_page(self) -> None:
        self._next = 0

    def read_line(self, image: Image.Image) -> OcrResult:
        if self._next >= len(self._lines):
            return OcrResult("", 0.0)
        text = self._lines[self._next]
        self._next += 1
        return OcrResult(text, 0.99)


class TrocrOcr(OcrEngine):
    """microsoft/trocr-base-handwritten via transformers (line-level). Needs `make install-ml`."""

    MODEL_ID = "microsoft/trocr-base-handwritten"

    def __init__(self) -> None:
        self._model: Any = None
        self._processor: Any = None

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            from transformers import TrOCRProcessor, VisionEncoderDecoderModel
        except ImportError as exc:
            from hwai.errors import ApiError

            raise ApiError(
                503, "ml_not_installed", "Handwriting OCR needs the ML extras (make install-ml)."
            ) from exc
        self._processor = TrOCRProcessor.from_pretrained(self.MODEL_ID)
        self._model = VisionEncoderDecoderModel.from_pretrained(self.MODEL_ID)
        self._model.eval()

    def read_line(self, image: Image.Image) -> OcrResult:
        self._load()
        import torch

        pixel_values = self._processor(
            images=image.convert("RGB"), return_tensors="pt"
        ).pixel_values
        with torch.no_grad():
            out = self._model.generate(
                pixel_values, max_new_tokens=64, output_scores=True, return_dict_in_generate=True
            )
        text = self._processor.batch_decode(out.sequences, skip_special_tokens=True)[0].strip()
        scores = self._model.compute_transition_scores(
            out.sequences, out.scores, normalize_logits=True
        )
        confidence = float(torch.exp(scores.mean())) if scores.numel() else 0.0
        return OcrResult(text, confidence)


def get_ocr() -> OcrEngine:
    name = get_settings().ocr
    if name == "fake":
        return FakeOcr()
    if name == "trocr":
        return TrocrOcr()
    raise ValueError(f"Unknown OCR: {name!r} (expected 'fake' or 'trocr')")
