"""Frequency-domain laundering toward natural-image spectral statistics.

Generative models leave characteristic radial-power-spectrum signatures: a
"shoulder" of excess high-frequency energy in certain bands (depends on the
model family — diffusion checkerboards, GAN regular cycles), and an
unnaturally sharp roll-off compared to natural photographs which follow
roughly a 1/f^alpha (alpha ≈ 1.8–2.2) power-law decay.

This module:

  1. Computes the radial power spectrum of the input.
  2. Computes a target spectrum either from a reference photo (if supplied)
     or from a synthetic 1/f^alpha baseline.
  3. Builds a multiplicative correction mask in the frequency domain that
     pushes the input spectrum toward the target.
  4. Applies the mask conservatively (clipped, blended) and inverse-transforms.

The correction is intentionally mild — strong rebalancing visibly damages
the image (haloing, blockiness). The goal is to defeat detectors that key on
a *specific* spectral shoulder, not to fully match natural photo statistics.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
from PIL import Image


@dataclass
class SpectrumParams:
    target_alpha: float = 2.0          # 1/f^alpha exponent for natural-image baseline
    blend: float = 0.5                  # how strongly to apply correction (0..1)
    clip_db: float = 6.0                # max correction in dB per radial bin
    high_freq_only: bool = True         # only correct the high-freq shoulder where AI tells live


def _radial_power_spectrum(channel: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Return (radii, mean power per radial bin) for a 2D real channel."""
    F = np.fft.fft2(channel)
    F = np.fft.fftshift(F)
    P = np.abs(F) ** 2
    H, W = channel.shape
    cy, cx = H // 2, W // 2
    yy, xx = np.indices((H, W))
    r = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2).astype(np.int32)

    n_bins = min(H, W) // 2
    radii = np.arange(n_bins)
    radial = np.zeros(n_bins, dtype=np.float64)
    counts = np.zeros(n_bins, dtype=np.int64)
    for i in range(H):
        for j in range(W):
            ri = r[i, j]
            if ri < n_bins:
                radial[ri] += P[i, j]
                counts[ri] += 1
    radial = radial / np.maximum(counts, 1)
    return radii, radial


def _radial_power_spectrum_fast(channel: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    F = np.fft.fft2(channel)
    F = np.fft.fftshift(F)
    P = np.abs(F) ** 2
    H, W = channel.shape
    cy, cx = H // 2, W // 2
    yy, xx = np.indices((H, W))
    r = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2).astype(np.int32)
    n_bins = min(H, W) // 2
    flat_r = r.ravel()
    flat_p = P.ravel()
    mask = flat_r < n_bins
    radial = np.bincount(flat_r[mask], weights=flat_p[mask], minlength=n_bins)
    counts = np.bincount(flat_r[mask], minlength=n_bins)
    radial = radial / np.maximum(counts, 1)
    return np.arange(n_bins), radial


def _natural_baseline(radii: np.ndarray, alpha: float, anchor: float) -> np.ndarray:
    """1/f^alpha baseline anchored to ``anchor`` at radius=1."""
    safe = np.maximum(radii.astype(np.float64), 1.0)
    return anchor / (safe ** alpha)


def _correction_mask_2d(shape: Tuple[int, int], radii: np.ndarray, factor: np.ndarray) -> np.ndarray:
    """Build a 2D multiplicative correction array of FFT-shifted shape."""
    H, W = shape
    cy, cx = H // 2, W // 2
    yy, xx = np.indices((H, W))
    r = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2).astype(np.float64)
    bins = np.clip(np.round(r).astype(np.int32), 0, len(factor) - 1)
    return factor[bins].astype(np.float64)


def launder(
    image_path: Path,
    output_path: Path,
    reference_image: Optional[Path] = None,
    params: Optional[SpectrumParams] = None,
    preserve_exif: bool = True,
) -> dict:
    """Apply spectrum laundering to ``image_path`` and write to ``output_path``.

    If ``reference_image`` is provided, its radial spectrum is used as the
    target. Otherwise a 1/f^alpha synthetic baseline is used.
    """
    params = params or SpectrumParams()
    image_path = Path(image_path)
    output_path = Path(output_path)

    with Image.open(image_path) as im:
        im.load()
        if im.mode != "RGB":
            im = im.convert("RGB")
        rgb = np.asarray(im, dtype=np.float32)
        exif_blob = im.info.get("exif") if preserve_exif else None
        icc_blob = im.info.get("icc_profile")

    H, W, _ = rgb.shape
    out = np.zeros_like(rgb)

    if reference_image is not None:
        with Image.open(reference_image) as ref_im:
            if ref_im.mode != "RGB":
                ref_im = ref_im.convert("RGB")
            ref_im = ref_im.resize((W, H), Image.Resampling.LANCZOS)
            ref_rgb = np.asarray(ref_im, dtype=np.float32)

    delta_db_summary = []
    for c in range(3):
        ch = rgb[..., c]
        radii, src_pow = _radial_power_spectrum_fast(ch)
        if reference_image is not None:
            _, tgt_pow = _radial_power_spectrum_fast(ref_rgb[..., c])
        else:
            anchor = max(src_pow[1], 1e-3)
            tgt_pow = _natural_baseline(radii, params.target_alpha, anchor)

        ratio = tgt_pow / np.maximum(src_pow, 1e-6)
        ratio_amp = np.sqrt(ratio)  # amplitude correction (we'll multiply on FFT magnitudes)

        # Limit per-bin correction to ±clip_db.
        max_lin = 10 ** (params.clip_db / 20.0)
        ratio_amp = np.clip(ratio_amp, 1.0 / max_lin, max_lin)

        # Optionally only correct the high-frequency shoulder.
        if params.high_freq_only:
            mid = len(ratio_amp) // 4
            mask = np.ones_like(ratio_amp)
            mask[:mid] = 0.0
            mask[mid:2 * mid] = np.linspace(0, 1, mid)
            ratio_amp = 1.0 + (ratio_amp - 1.0) * mask

        ratio_amp = 1.0 + params.blend * (ratio_amp - 1.0)

        delta_db_summary.append(float(20 * np.log10(np.mean(ratio_amp) + 1e-9)))

        F = np.fft.fftshift(np.fft.fft2(ch))
        mask2d = _correction_mask_2d(ch.shape, radii, ratio_amp)
        F_corr = F * mask2d
        ch_out = np.real(np.fft.ifft2(np.fft.ifftshift(F_corr)))
        out[..., c] = ch_out

    out = np.clip(out, 0, 255).astype(np.uint8)

    save_kwargs = {"format": "JPEG", "quality": 92, "subsampling": "4:2:0"}
    if exif_blob:
        save_kwargs["exif"] = exif_blob
    if icc_blob:
        save_kwargs["icc_profile"] = icc_blob
    Image.fromarray(out, "RGB").save(output_path, **save_kwargs)

    rmse = float(np.sqrt(((rgb - out.astype(np.float32)) ** 2).mean()))
    return {
        "params": asdict(params),
        "rmse_vs_input": rmse,
        "mean_correction_db_per_channel": delta_db_summary,
        "output": str(output_path),
    }
