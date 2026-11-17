"""One-DM renderer (https://github.com/dailenson/One-DM, MIT code, ECCV 2024).

Wraps One-DM's real inference pieces as `test.py` in the vendored repo uses them:
`parse_config.cfg`, `models.unet.UNetModel`, `models.diffusion.Diffusion.ddim_sample`,
`data_loader.loader.ContentData` and the Stable Diffusion `AutoencoderKL` VAE.

torch, diffusers and One-DM are imported ONLY inside `_Engine`; importing this module never
imports torch. The array maths (`prepare_style`, `gray_to_rgba`, ...) is pure numpy so it is
unit-tested without a GPU.
"""

from __future__ import annotations

import contextlib
import os
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from hwai.config import get_settings
from hwai.errors import ApiError
from hwai.render.base import Renderer, StyleRef, WordImage
from hwai.render.jitter import apply_jitter

# --- Constants taken from One-DM (data_loader/loader.py, configs/IAM64.yml) -------------------
# Character set the content encoder knows (index = position in this string).
ONEDM_LETTERS = "_Only thewigsofrcvdampbkuq.A-210xT5'MDL,RYHJ\"ISPWENj&BC93VGFKz();#:!7U64Q8?+*ZX/%"
STYLE_HEIGHT = 64  # IMG_H: style and output images are 64 px tall
STYLE_MIN_WIDTH = 128  # Random_StyleIAMDataset only accepts style images wider than 128 px
STYLE_MAX_WIDTH = 352  # style_len
CHAR_WIDTH = 32  # each content character yields 32 output pixels (latent 4 * VAE factor 8)
_LAPLACE_KERNEL = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
_PROJECT_ROOT = Path(__file__).resolve().parents[5]
INK_RGB = (25, 25, 45)  # dark blue-black, same family as FakeRenderer


# --- Pure array helpers (no torch) -------------------------------------------------------------
def prepare_style(image: Image.Image) -> tuple[np.ndarray, np.ndarray]:
    """Style crop -> (style, laplace) float32 arrays of shape (64, W), W in [128, 352].

    style: greyscale in [0, 1], white paper = 1, ink dark (what One-DM reads with cv2 /255).
    laplace: high-frequency map in [0, 1], 0 on flat paper.
    NOTE: One-DM ships the laplace images pre-computed in its dataset download and its repo
    does not contain the code that made them. The kernel below is the one defined in its
    loader.py; matching the dataset's exact recipe is UNVERIFIED (needs a GPU run).
    """
    rgba = image.convert("RGBA")
    flat = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    flat.alpha_composite(rgba)
    gray_in = np.asarray(flat.convert("L"), dtype=np.uint8)
    h, w = gray_in.shape
    if h < 1 or w < 1:
        raise ApiError(422, "bad_style_ref", "The style image is empty.")
    new_w = max(1, round(w * STYLE_HEIGHT / h))
    gray: np.ndarray = cv2.resize(gray_in, (new_w, STYLE_HEIGHT), interpolation=cv2.INTER_AREA)
    style = gray.astype(np.float32) / 255.0
    if style.shape[1] > STYLE_MAX_WIDTH:
        style = style[:, :STYLE_MAX_WIDTH]
    elif style.shape[1] < STYLE_MIN_WIDTH:
        pad = np.ones((STYLE_HEIGHT, STYLE_MIN_WIDTH - style.shape[1]), dtype=np.float32)
        style = np.concatenate([style, pad], axis=1)
    lap = np.abs(cv2.filter2D(style, -1, _LAPLACE_KERNEL, borderType=cv2.BORDER_REPLICATE))
    return style, np.clip(lap, 0.0, 1.0).astype(np.float32)


def validate_word(word: str) -> None:
    bad = sorted({c for c in word if c not in ONEDM_LETTERS or c == "_"})
    if bad:
        raise ApiError(
            422,
            "unsupported_character",
            f"One-DM cannot write these characters: {''.join(bad)!r}",
        )


def estimate_baseline(alpha: np.ndarray) -> int:
    """Baseline row of a cropped word: bottom of the dense body of ink.

    Descenders (g, y, p) are thin, so the last row holding >= 35% of the busiest row's ink
    is the baseline; falls back to the bottom row for blank input.
    """
    rows = alpha.astype(np.float32).sum(axis=1)
    if rows.size == 0 or rows.max() <= 0:
        return int(alpha.shape[0])
    dense = np.nonzero(rows >= 0.35 * rows.max())[0]
    return int(dense[-1]) + 1


def gray_to_rgba(arr: np.ndarray, scale: float = 1.0) -> WordImage:
    """Model output (H, W) greyscale in [0, 1] (white = paper) -> transparent RGBA word.

    Ink = darkness. The paper level is estimated from the brightest 20% of pixels and removed,
    faint haze below 8% darkness is dropped, then the image is cropped to the ink and scaled.
    """
    g = np.asarray(arr, dtype=np.float32)
    if g.ndim == 3:  # (H, W, C) or (C, H, W) colour output: average channels
        g = g.mean(axis=2 if g.shape[2] in (1, 3, 4) else 0)
    if g.ndim != 2:
        raise ValueError(f"expected a 2-D greyscale array, got shape {arr.shape}")
    if g.size == 0:
        return WordImage(Image.new("RGBA", (1, 1), (0, 0, 0, 0)), 0)
    g = np.clip(g, 0.0, 1.0)
    paper = float(np.percentile(g, 80))
    span = max(paper - float(g.min()), 1e-3)
    darkness = np.clip((paper - g) / span, 0.0, 1.0)
    darkness = np.where(darkness < 0.08, 0.0, darkness)
    alpha = (darkness * 255.0).round().astype(np.uint8)
    ys, xs = np.nonzero(alpha)
    if ys.size == 0:
        return WordImage(Image.new("RGBA", (1, 1), (0, 0, 0, 0)), 0)
    top, bottom, left, right = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    alpha = alpha[top:bottom, left:right]
    baseline = estimate_baseline(alpha)
    rgba = np.zeros((*alpha.shape, 4), dtype=np.uint8)
    rgba[:, :, 0], rgba[:, :, 1], rgba[:, :, 2] = INK_RGB
    rgba[:, :, 3] = alpha
    img = Image.fromarray(rgba, "RGBA")
    if abs(scale - 1.0) > 1e-3:
        new = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
        img = img.resize(new, Image.Resampling.LANCZOS)
        baseline = round(baseline * scale)
    return WordImage(image=img, baseline_px=max(0, min(baseline, img.height)))


# --- Renderer ----------------------------------------------------------------------------------
class OneDMRenderer(Renderer):
    """Real handwriting via One-DM. The model loads on the first render call."""

    def __init__(self) -> None:
        self._engine: _Engine | None = None
        self._lock = threading.Lock()

    def render_word(
        self, word: str, style_refs: list[StyleRef], seed: int, size_px: int
    ) -> WordImage:
        return self.render_words([word], style_refs, seed, size_px)[0]

    def render_words(
        self, words: list[str], style_refs: list[StyleRef], seed: int, size_px: int = 64
    ) -> list[WordImage]:
        """Render several words in GPU batches. Word i uses seed `seed + i`.

        All words share one style sample (picked from `style_refs` by `seed`). Words of
        different length are padded with One-DM's blank content token and trimmed afterwards;
        they are sorted by length so padding stays small.
        """
        if not style_refs:
            raise ApiError(
                422,
                "no_style_ref",
                "No style reference: add handwriting samples before rendering with One-DM.",
            )
        for w in words:
            validate_word(w)
        results: list[WordImage | None] = [None] * len(words)
        todo = [i for i, w in enumerate(words) if w.strip() and size_px >= 1]
        for i in range(len(words)):
            if i not in todo:
                results[i] = WordImage(Image.new("RGBA", (1, 1), (0, 0, 0, 0)), 0)
        if todo:
            ref = style_refs[seed % len(style_refs)]
            style, laplace = prepare_style(ref.image)
            todo.sort(key=lambda i: len(words[i]))
            batch_size = get_settings().onedm_batch_size
            engine = self._get_engine()
            for start in range(0, len(todo), batch_size):
                chunk = todo[start : start + batch_size]
                outs = engine.sample(
                    style, laplace, [words[i] for i in chunk], [seed + i for i in chunk]
                )
                for i, out in zip(chunk, outs, strict=True):
                    word_img = gray_to_rgba(out, scale=size_px / STYLE_HEIGHT)
                    jittered = apply_jitter(word_img.image, seed + i, strength=0.5)
                    results[i] = WordImage(jittered, word_img.baseline_px)
        return [r for r in results if r is not None]

    def _get_engine(self) -> _Engine:
        with self._lock:
            if self._engine is None:
                self._engine = _Engine(get_settings())
            return self._engine


_singleton: OneDMRenderer | None = None


def get_onedm_renderer() -> OneDMRenderer:
    """Process-wide instance so the model is loaded once."""
    global _singleton
    if _singleton is None:
        _singleton = OneDMRenderer()
    return _singleton


@contextlib.contextmanager
def _in_dir(path: Path) -> Iterator[None]:
    """One-DM loads config and `data/unifont.pickle` by relative path."""
    old = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


class _Engine:
    """Holds the loaded torch models. All torch/One-DM imports happen in here."""

    def __init__(self, settings: Any) -> None:
        repo = Path(settings.onedm_repo_dir)
        if not repo.is_absolute() and not repo.exists():
            repo = _PROJECT_ROOT / repo  # default ./vendor/One-DM is relative to the repo root
        repo = repo.resolve()
        weights = Path(settings.onedm_weights_path) if settings.onedm_weights_path else None
        if not (repo / "test.py").is_file():
            raise ApiError(
                503,
                "onedm_not_installed",
                f"One-DM repo not found at {repo}. Clone it into vendor/One-DM (see CLAUDE.md).",
            )
        if weights is None or not weights.is_file():
            raise ApiError(
                503,
                "onedm_weights_missing",
                "Set ONEDM_WEIGHTS_PATH to the One-DM English checkpoint (One-DM-ckpt.pt).",
            )
        try:
            import torch
        except ImportError as exc:
            raise ApiError(
                503, "ml_not_installed", "torch is missing. Run `make install-ml`."
            ) from exc
        if not torch.cuda.is_available():
            raise ApiError(503, "no_gpu", "One-DM needs an NVIDIA GPU with CUDA.")

        self.torch = torch
        self.device = "cuda"
        self.steps = settings.onedm_sampling_steps
        if str(repo) not in sys.path:
            sys.path.insert(0, str(repo))
        with _in_dir(repo):
            from data_loader.loader import ContentData
            from diffusers import AutoencoderKL
            from models.diffusion import Diffusion
            from models.unet import UNetModel
            from parse_config import assert_and_infer_cfg, cfg, cfg_from_file

            cfg_from_file("configs/IAM64.yml")
            assert_and_infer_cfg()
            self.content = ContentData()
            self.diffusion = Diffusion(device=self.device)
            unet = UNetModel(
                in_channels=cfg.MODEL.IN_CHANNELS,
                model_channels=cfg.MODEL.EMB_DIM,
                out_channels=cfg.MODEL.OUT_CHANNELS,
                num_res_blocks=cfg.MODEL.NUM_RES_BLOCKS,
                attention_resolutions=(1, 1),
                channel_mult=(1, 1),
                num_heads=cfg.MODEL.NUM_HEADS,
                context_dim=cfg.MODEL.EMB_DIM,
            ).to(self.device)
            unet.load_state_dict(torch.load(str(weights), map_location="cpu"))
            unet.eval()
            self.unet = unet
            vae = AutoencoderKL.from_pretrained(settings.onedm_vae_path, subfolder="vae")
            vae = vae.to(self.device)
            vae.requires_grad_(False)
            self.vae = vae

    def sample(
        self, style: np.ndarray, laplace: np.ndarray, words: list[str], seeds: list[int]
    ) -> list[np.ndarray]:
        """Run DDIM for a batch of words in one style. Returns (64, W) greyscale arrays."""
        torch = self.torch
        n = len(words)
        max_len = max(len(w) for w in words)
        contents = []
        for w in words:
            c = self.content.get_content(w)[0]  # (len, 16, 16), already inverted (1 - glyph)
            if len(w) < max_len:  # pad with blank glyphs, as One-DM's PAD_TOKEN does
                pad = torch.ones((max_len - len(w), *c.shape[1:]), dtype=c.dtype)
                c = torch.cat([c, pad], dim=0)
            contents.append(c)
        text_ref = torch.stack(contents).to(self.device)
        style_t = torch.from_numpy(style)[None, None].repeat(n, 1, 1, 1).to(self.device)
        lap_t = torch.from_numpy(laplace)[None, None].repeat(n, 1, 1, 1).to(self.device)
        noises = []
        for s in seeds:
            gen = torch.Generator(device="cpu").manual_seed(int(s) & 0x7FFFFFFF)
            noises.append(
                torch.randn((4, STYLE_HEIGHT // 8, (max_len * CHAR_WIDTH) // 8), generator=gen)
            )
        x = torch.stack(noises).to(self.device)
        with torch.no_grad():
            out = self.diffusion.ddim_sample(
                self.unet, self.vae, n, x, style_t, lap_t, text_ref, self.steps, 0
            )
        arrs: list[np.ndarray] = []
        for i, w in enumerate(words):
            a = out[i].mean(dim=0).cpu().numpy()  # (64, max_len*32), channels averaged
            arrs.append(a[:, : len(w) * CHAR_WIDTH])  # drop the blank padding columns
        return arrs
