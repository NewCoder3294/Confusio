"""Re-photograph simulation: digitally model the analog hole.

A real photo of a real scene picks up many independent signals during capture
that AI generators do not produce: lens point-spread function, chromatic
aberration from refractive-index dispersion, sensor read noise, demosaicing
trails, sharpening from the on-device ISP, and one or two rounds of JPEG
compression.

Stacking AI-generated pixels through a digital simulation of those signals
breaks the fingerprint a CNN classifier learned from raw generator output.
The image still looks like the same content, but the underlying spectral
and statistical structure shifts toward "captured" rather than "synthesized".

Pipeline (all stages parameterised so we can dial intensity for the demo):

    1. Lens PSF             — small Gaussian blur (sigma 0.5-1.5px)
    2. Chromatic aberration — radial per-channel offset (R outward, B inward)
    3. Sensor noise         — additive Gaussian on luma
    4. ISP sharpening       — unsharp mask (compensates step 1, adds high-freq)
    5. JPEG round 1         — quality 85-92 (matches phone-camera output)
    6. JPEG round 2         — quality 88-94 (simulates Photos-app re-encode)

All steps are deterministic given a seed; the seed is mixed from a strength
parameter so demos are reproducible.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageFilter
from scipy.ndimage import gaussian_filter, map_coordinates


@dataclass
class RephotoParams:
    psf_sigma: float = 0.7         # lens blur stddev in pixels
    chroma_strength: float = 1.2    # radial aberration in pixels at frame edge
    sensor_noise: float = 1.8       # Gaussian noise stddev on luma
    sharpen_amount: float = 0.6     # unsharp mask amount
    jpeg_q1: int = 88
    jpeg_q2: int = 92
    seed: int = 0


def _lens_blur(arr: np.ndarray, sigma: float) -> np.ndarray:
    if sigma <= 0:
        return arr
    return np.stack([gaussian_filter(arr[..., c], sigma=sigma) for c in range(arr.shape[-1])], axis=-1)


def _chromatic_aberration(arr: np.ndarray, strength: float) -> np.ndarray:
    """Apply radial per-channel offset.

    R channel is pushed slightly outward from the optical center, B inward.
    Magnitude scales linearly with radius; ``strength`` is the offset in pixels
    at the corner of the frame.
    """
    if strength <= 0:
        return arr
    H, W, _ = arr.shape
    cy, cx = (H - 1) / 2, (W - 1) / 2
    diag = np.hypot(cy, cx)

    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    dy = yy - cy
    dx = xx - cx
    radius = np.sqrt(dx * dx + dy * dy)
    scale = radius / max(diag, 1.0)  # 0 at center, 1 at corner

    out = arr.astype(np.float32).copy()
    for ch, sign in ((0, +1.0), (2, -1.0)):  # R outward, B inward
        offset = sign * strength * scale
        coords_y = yy + offset * dy / np.maximum(radius, 1e-3)
        coords_x = xx + offset * dx / np.maximum(radius, 1e-3)
        out[..., ch] = map_coordinates(arr[..., ch].astype(np.float32), [coords_y, coords_x], order=1, mode="reflect")
    return out


def _sensor_noise(arr: np.ndarray, sigma: float, rng: np.random.Generator) -> np.ndarray:
    if sigma <= 0:
        return arr
    # Apply mostly to luma to mimic real sensor noise (chrominance is usually denoised on-device).
    rgb = arr.astype(np.float32)
    luma = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
    noise = rng.standard_normal(luma.shape).astype(np.float32) * sigma
    rgb[..., 0] += noise
    rgb[..., 1] += noise
    rgb[..., 2] += noise
    return np.clip(rgb, 0, 255).astype(np.float32)


def _unsharp(arr: np.ndarray, amount: float, sigma: float = 1.2) -> np.ndarray:
    if amount <= 0:
        return arr
    blurred = _lens_blur(arr, sigma=sigma)
    return np.clip(arr.astype(np.float32) + amount * (arr.astype(np.float32) - blurred), 0, 255)


def _jpeg_roundtrip(arr: np.ndarray, quality: int) -> np.ndarray:
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=int(quality), subsampling="4:2:0")
    buf.seek(0)
    return np.asarray(Image.open(buf).convert("RGB"), dtype=np.float32)


def rephoto(
    image_path: Path,
    output_path: Path,
    params: Optional[RephotoParams] = None,
    preserve_exif: bool = True,
) -> dict:
    """Apply the full re-photograph chain to ``image_path`` and write to ``output_path``.

    Returns a dict of params used and basic stats on the transformation.
    """
    params = params or RephotoParams()
    image_path = Path(image_path)
    output_path = Path(output_path)

    rng = np.random.default_rng(params.seed)

    with Image.open(image_path) as im:
        im.load()
        if im.mode != "RGB":
            im = im.convert("RGB")
        rgb = np.asarray(im, dtype=np.float32)
        exif_blob = im.info.get("exif") if preserve_exif else None
        icc_blob = im.info.get("icc_profile")

    work = rgb.copy()
    work = _lens_blur(work, params.psf_sigma)
    work = _chromatic_aberration(work, params.chroma_strength)
    work = _sensor_noise(work, params.sensor_noise, rng)
    work = _unsharp(work, params.sharpen_amount)
    work = _jpeg_roundtrip(work, params.jpeg_q1)
    work = _jpeg_roundtrip(work, params.jpeg_q2)

    final = np.clip(work, 0, 255).astype(np.uint8)

    save_kwargs = {"format": "JPEG", "quality": params.jpeg_q2, "subsampling": "4:2:0"}
    if exif_blob:
        save_kwargs["exif"] = exif_blob
    if icc_blob:
        save_kwargs["icc_profile"] = icc_blob
    Image.fromarray(final, "RGB").save(output_path, **save_kwargs)

    rmse = float(np.sqrt(((rgb - final.astype(np.float32)) ** 2).mean()))
    return {
        "params": asdict(params),
        "rmse_vs_input": rmse,
        "output": str(output_path),
    }
