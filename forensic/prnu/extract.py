"""Extract a PRNU (Photo Response Non-Uniformity) sensor fingerprint from a corpus.

PRNU is the per-pixel sensitivity variation introduced by silicon-process
imperfections during sensor manufacturing. It is:
  - Unique per physical sensor (per-unit, not per-model).
  - Multiplicative on the captured signal (additive in log domain).
  - Stable across the lifetime of the sensor.
  - Survives JPEG compression at the levels used in consumer phones.

Forensic tools (Amped Authenticate, PRNU correlation in academic toolchains)
test for the presence of a PRNU pattern; if absent, the image is flagged as
synthetic. This module estimates a PRNU pattern from a corpus of reference
photos taken with the claimed device class.

Method (Lukas-Fridrich-Goljan 2006, simplified):
  1. For each corpus image I:  W_i = I - denoise(I)   (residual = noise)
  2. Aggregate: K = sum(W_i * I_i) / sum(I_i^2)        (max-likelihood estimate)
  3. Zero-mean per row/column to suppress non-PRNU artifacts.
  4. Return K (float32 array, same HxW as corpus images).

Denoising uses a wavelet-domain Wiener filter (BM3D would be better but
heavier; wavelet is the canonical choice in the original PRNU literature).
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional, Tuple

import numpy as np
import pywt
from PIL import Image


def _to_grayscale_float(img: Image.Image) -> np.ndarray:
    if img.mode != "L":
        img = img.convert("L")
    return np.asarray(img, dtype=np.float32)


def wavelet_denoise(image: np.ndarray, sigma: float = 5.0, wavelet: str = "db8", levels: int = 4) -> np.ndarray:
    """Wavelet-domain Wiener filter — the canonical PRNU denoiser.

    Decomposes ``image`` with ``wavelet`` to ``levels``, applies an MMSE Wiener
    estimator to each detail subband (assuming Gaussian noise of stddev ``sigma``),
    then reconstructs.
    """
    coeffs = pywt.wavedec2(image, wavelet, level=levels)
    new_coeffs = [coeffs[0]]
    var_n = sigma ** 2
    for detail in coeffs[1:]:
        new_detail = []
        for band in detail:
            var_y = np.mean(band ** 2)
            var_x = max(var_y - var_n, 0.0)
            attenuation = var_x / (var_x + var_n + 1e-12)
            new_detail.append(band * attenuation)
        new_coeffs.append(tuple(new_detail))
    return pywt.waverec2(new_coeffs, wavelet)


def noise_residual(image: np.ndarray, sigma: float = 5.0) -> np.ndarray:
    """W = I - denoise(I), trimmed to original shape."""
    den = wavelet_denoise(image, sigma=sigma)
    den = den[: image.shape[0], : image.shape[1]]
    return image - den


def _zero_mean_rows_cols(k: np.ndarray) -> np.ndarray:
    """Subtract row and column means — kills non-PRNU artifacts (CFA, JPEG blockiness)."""
    k = k - k.mean(axis=0, keepdims=True)
    k = k - k.mean(axis=1, keepdims=True)
    return k


def extract_prnu(
    corpus: Iterable[Path],
    target_shape: Optional[Tuple[int, int]] = None,
    sigma: float = 5.0,
    max_images: int = 50,
) -> np.ndarray:
    """Estimate a PRNU pattern from a corpus of images.

    Args:
        corpus: iterable of image paths.
        target_shape: (H, W) to resize all images to before estimation. If None,
            uses the shape of the first image in the corpus.
        sigma: noise std-dev for the wavelet denoiser.
        max_images: cap on corpus size used for stability.

    Returns:
        np.ndarray (H, W), float32 — the maximum-likelihood PRNU estimate.
    """
    paths = list(corpus)[:max_images]
    if not paths:
        raise ValueError("empty PRNU corpus")

    H = W = None
    if target_shape is not None:
        H, W = target_shape

    numerator = None
    denominator = None
    used = 0

    for p in paths:
        try:
            with Image.open(p) as im:
                if (H, W) != (None, None):
                    im = im.resize((W, H), Image.Resampling.LANCZOS)
                gray = _to_grayscale_float(im)
        except Exception:
            continue

        if numerator is None:
            H, W = gray.shape
            numerator = np.zeros((H, W), dtype=np.float64)
            denominator = np.zeros((H, W), dtype=np.float64)

        if gray.shape != (H, W):
            from PIL import Image as _PIL
            gray_im = _PIL.fromarray(gray.astype(np.uint8))
            gray_im = gray_im.resize((W, H), Image.Resampling.LANCZOS)
            gray = np.asarray(gray_im, dtype=np.float32)

        w = noise_residual(gray, sigma=sigma)
        numerator += w * gray
        denominator += gray ** 2
        used += 1

    if used == 0:
        raise ValueError("no usable images in PRNU corpus")

    k = numerator / np.maximum(denominator, 1.0)
    k = _zero_mean_rows_cols(k)
    return k.astype(np.float32)


def save_prnu(prnu: np.ndarray, path: Path) -> None:
    np.save(path, prnu)


def load_prnu(path: Path) -> np.ndarray:
    return np.load(path)
