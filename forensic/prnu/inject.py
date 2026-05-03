"""Additively inject a PRNU sensor fingerprint into a synthetic image.

Given a target (synthetic) image I and a PRNU pattern K, the injected output is
roughly:

    I' = I * (1 + alpha * K)

where alpha is scaled so the injected energy matches the natural sensor-noise
variance of the claimed device class (typically alpha ~= 0.01 — 0.05 for 8-bit
images, equivalent to per-pixel noise in the 1-3 LSB range).

The forensic test the adversary will run (PRNU correlation) computes:

    rho = corr(noise_residual(I'), I' * K)

and compares to a threshold. Injection is successful if rho exceeds threshold
without visibly altering I.
"""
from __future__ import annotations

from pathlib import Path
from typing import Tuple

import numpy as np
from PIL import Image

from .extract import noise_residual, _to_grayscale_float


def _resize_prnu(prnu: np.ndarray, shape: Tuple[int, int]) -> np.ndarray:
    """Resize PRNU pattern to ``shape`` (H, W) using bilinear interpolation."""
    if prnu.shape == shape:
        return prnu
    H, W = shape
    im = Image.fromarray(prnu)
    im = im.resize((W, H), Image.Resampling.BILINEAR)
    return np.asarray(im, dtype=np.float32)


def inject_prnu(
    image_path: Path,
    prnu: np.ndarray,
    output_path: Path,
    alpha: float = 0.025,
    preserve_exif: bool = True,
) -> Path:
    """Multiplicatively blend ``prnu`` into ``image_path``, writing JPEG to ``output_path``.

    Args:
        image_path: synthetic image (any PIL-readable format).
        prnu: float32 PRNU pattern (H, W) — will be resized to image dimensions.
        output_path: where to write the result (JPEG).
        alpha: injection strength. 0.025 = roughly 0.6 LSB per pixel of added
            noise on 8-bit; matches DSLR sensor-noise scale. Range typically
            0.01-0.05.
        preserve_exif: copy EXIF blob from input.
    """
    image_path = Path(image_path)
    output_path = Path(output_path)

    with Image.open(image_path) as im:
        im.load()
        if im.mode != "RGB":
            im = im.convert("RGB")
        exif_blob = im.info.get("exif") if preserve_exif else None
        icc_blob = im.info.get("icc_profile")
        rgb = np.asarray(im, dtype=np.float32)

    H, W, _ = rgb.shape
    k = _resize_prnu(prnu, (H, W))

    # Apply per-channel: I' = I * (1 + alpha * K)
    factor = 1.0 + alpha * k[..., None]
    out = rgb * factor
    out = np.clip(out, 0.0, 255.0).astype(np.uint8)

    save_kwargs = {"format": "JPEG", "quality": 92, "subsampling": "4:2:0"}
    if exif_blob:
        save_kwargs["exif"] = exif_blob
    if icc_blob:
        save_kwargs["icc_profile"] = icc_blob

    Image.fromarray(out).save(output_path, **save_kwargs)
    return output_path


def correlate(image_path: Path, prnu: np.ndarray, sigma: float = 5.0) -> float:
    """PRNU correlation test — what an adversary's forensic tool computes.

    Returns Pearson correlation between the image's noise residual and the
    expected PRNU signature (image * prnu). Values > ~0.01 typically indicate
    a real PRNU match; < 0.005 indicate absence.

    Use this as a self-grade after injection: if correlation is too low,
    increase alpha; if image quality degrades, decrease alpha.
    """
    image_path = Path(image_path)
    with Image.open(image_path) as im:
        gray = _to_grayscale_float(im)

    k = _resize_prnu(prnu, gray.shape)
    expected = gray * k
    residual = noise_residual(gray, sigma=sigma)

    expected = expected - expected.mean()
    residual = residual - residual.mean()
    num = float((expected * residual).sum())
    den = float(np.sqrt((expected ** 2).sum() * (residual ** 2).sum()) + 1e-12)
    return num / den
