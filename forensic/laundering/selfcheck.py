"""Surrogate AI-image-detector self-check.

Runs a public, pretrained AI-image classifier as a surrogate for what a judge
or adversary will run during evaluation. Reports a probability that the image
is AI-generated, computed before and after laundering so the demo can show a
concrete confidence drop.

**This is a SURROGATE, not a guarantee against commercial detectors.**
Public open-source AI-image classifiers (Hugging Face) are typically trained
on smaller datasets than commercial offerings (Hive AI, Optic, Reality
Defender). A drop on the surrogate is evidence that pixel-level signal has
been altered; transfer to a specific commercial detector is *probable but
not certain* and depends on architectural similarity.

Models used (in priority order, falls through if download fails):

  1. Organika/sdxl-detector  — ViT, ~80MB, current generation
  2. umm-maybe/AI-image-detector — older, lighter

Fallback (if torch/transformers unavailable or download fails):
  - spectral-residual heuristic: distance from natural-image 1/f baseline.
    Crude but deterministic and dependency-free.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np
from PIL import Image


SURROGATE_MODELS = [
    "Organika/sdxl-detector",
    "umm-maybe/AI-image-detector",
]


@dataclass
class DetectionResult:
    model: str
    p_ai: float                # probability label is AI
    p_real: float              # probability label is real
    raw_label: str
    backend: str               # "torch_surrogate" or "spectral_heuristic"
    note: str = ""


_PIPELINE_CACHE: dict = {}


def _load_pipeline(model_id: str):
    """Lazy-load the HF image-classification pipeline. Returns None on failure."""
    if model_id in _PIPELINE_CACHE:
        return _PIPELINE_CACHE[model_id]
    try:
        # Make HF as quiet and sandbox-friendly as we can.
        os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
        os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
        from transformers import pipeline as _hf_pipeline  # type: ignore
        pipe = _hf_pipeline("image-classification", model=model_id)
        _PIPELINE_CACHE[model_id] = pipe
        return pipe
    except Exception as e:
        _PIPELINE_CACHE[model_id] = None
        return None


def _score_one_pipeline(model_id: str, img: Image.Image) -> Optional[DetectionResult]:
    pipe = _load_pipeline(model_id)
    if pipe is None:
        return None
    try:
        preds = pipe(img)
    except Exception:
        return None
    ai_score = 0.0
    real_score = 0.0
    top_label = ""
    top_score = -1.0
    for p in preds:
        label = str(p["label"]).lower()
        score = float(p["score"])
        if score > top_score:
            top_score = score
            top_label = p["label"]
        if any(tok in label for tok in ("artificial", "ai", "generated", "fake", "synth")):
            ai_score = max(ai_score, score)
        elif any(tok in label for tok in ("human", "real", "natural", "photo")):
            real_score = max(real_score, score)
    if ai_score == 0.0 and real_score > 0.0:
        ai_score = max(0.0, 1.0 - real_score)
    if real_score == 0.0 and ai_score > 0.0:
        real_score = max(0.0, 1.0 - ai_score)
    return DetectionResult(
        model=model_id,
        p_ai=float(ai_score),
        p_real=float(real_score),
        raw_label=top_label,
        backend="torch_surrogate",
    )


def _torch_surrogate_score(image_path: Path) -> Optional[DetectionResult]:
    """Try each model in order; return first successful detection result, else None."""
    img = Image.open(image_path).convert("RGB")
    for model_id in SURROGATE_MODELS:
        result = _score_one_pipeline(model_id, img)
        if result is not None:
            return result
    return None


def detect_all(image_path: Path) -> List["DetectionResult"]:
    """Score the image against every available surrogate model.

    Returns a list of DetectionResult entries (one per loaded model). Empty if
    none load. Used by the multi-detector sweep optimiser.
    """
    img = Image.open(image_path).convert("RGB")
    results: List[DetectionResult] = []
    for model_id in SURROGATE_MODELS:
        r = _score_one_pipeline(model_id, img)
        if r is not None:
            results.append(r)
    return results


def _spectral_heuristic_score(image_path: Path) -> DetectionResult:
    """Fallback heuristic: compare radial spectrum to 1/f natural baseline."""
    from .spectrum import _radial_power_spectrum_fast

    img = Image.open(image_path).convert("L")
    arr = np.asarray(img, dtype=np.float32)
    radii, pow_ = _radial_power_spectrum_fast(arr)
    safe = np.maximum(pow_[1:], 1e-9)
    log_p = np.log10(safe)
    log_r = np.log10(np.maximum(radii[1:], 1.0))
    # Fit alpha in 1/f^alpha; natural images cluster around 1.8-2.2.
    A = np.vstack([log_r, np.ones_like(log_r)]).T
    slope, _ = np.linalg.lstsq(A, log_p, rcond=None)[0]
    alpha = -slope
    # Map distance from natural alpha to a probability.
    deviation = abs(alpha - 2.0)
    p_ai = float(min(1.0, deviation / 1.5))
    return DetectionResult(
        model="spectral_heuristic",
        p_ai=p_ai,
        p_real=1.0 - p_ai,
        raw_label=f"alpha={alpha:.2f}",
        backend="spectral_heuristic",
        note="surrogate model unavailable; using radial-spectrum 1/f^alpha distance",
    )


def detect(image_path: Path, force_heuristic: bool = False) -> DetectionResult:
    """Score one image. Tries torch surrogate first; falls back to heuristic."""
    if not force_heuristic:
        result = _torch_surrogate_score(Path(image_path))
        if result is not None:
            return result
    return _spectral_heuristic_score(Path(image_path))


def compare(before_path: Path, after_path: Path, force_heuristic: bool = False) -> dict:
    """Score before-vs-after laundering. Returns dict with both scores + delta."""
    before = detect(before_path, force_heuristic=force_heuristic)
    after = detect(after_path, force_heuristic=force_heuristic)
    return {
        "before": {
            "model": before.model,
            "backend": before.backend,
            "p_ai": before.p_ai,
            "p_real": before.p_real,
            "raw_label": before.raw_label,
        },
        "after": {
            "model": after.model,
            "backend": after.backend,
            "p_ai": after.p_ai,
            "p_real": after.p_real,
            "raw_label": after.raw_label,
        },
        "delta_p_ai": after.p_ai - before.p_ai,
        "note": before.note or after.note or "",
    }
