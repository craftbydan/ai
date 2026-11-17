"""Natural-variation maths. Pure and deterministic for a given seed."""

import cv2
import numpy as np
from PIL import Image


def apply_jitter(img: Image.Image, seed: int, strength: float = 1.0) -> Image.Image:
    """Small affine wobble, stroke-width variation and ink opacity noise on an RGBA image."""
    rgba = img.convert("RGBA")
    if strength <= 0 or rgba.width < 2 or rgba.height < 2:
        return rgba
    rng = np.random.default_rng(seed)
    arr = np.array(rgba)
    h, w = arr.shape[:2]

    # Stroke width: grow or shrink the alpha channel slightly.
    alpha = arr[:, :, 3]
    kernel = np.ones((2, 2), np.uint8)
    choice = rng.random()
    if choice < 0.25 * min(strength, 1.0):
        alpha = cv2.dilate(alpha, kernel)
    elif choice > 1.0 - 0.25 * min(strength, 1.0):
        alpha = cv2.erode(alpha, kernel)

    # Ink opacity noise (smooth, low frequency so it looks like pressure, not static).
    coarse = rng.normal(1.0, 0.06 * strength, size=(max(h // 8, 1) + 1, max(w // 8, 1) + 1))
    noise = cv2.resize(coarse.astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR)
    alpha = np.clip(alpha.astype(np.float32) * np.clip(noise, 0.7, 1.1), 0, 255).astype(np.uint8)
    arr[:, :, 3] = alpha

    # Small affine wobble (shear + scale + sub-pixel shift) about the centre.
    shear = float(rng.normal(0, 0.02 * strength))
    sx = 1.0 + float(rng.normal(0, 0.01 * strength))
    sy = 1.0 + float(rng.normal(0, 0.01 * strength))
    tx = float(rng.normal(0, 0.4 * strength))
    ty = float(rng.normal(0, 0.4 * strength))
    m = np.array(
        [[sx, shear, (1 - sx) * w / 2 - shear * h / 2 + tx], [0.0, sy, (1 - sy) * h / 2 + ty]],
        dtype=np.float32,
    )
    out = cv2.warpAffine(
        arr,
        m,
        (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )
    return Image.fromarray(out, "RGBA")
