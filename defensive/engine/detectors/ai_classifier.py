"""HuggingFace AI-image-detector wrapper. Lazy-loaded, warmable at boot."""
from __future__ import annotations

import io
import time
from typing import Any

from PIL import Image

from defensive.engine.verdict import DetectorSignal, Severity

NAME = "ai_classifier"
MODEL_ID = "Organika/sdxl-detector"

_pipeline: Any = None


def _get_pipeline() -> Any:
    """Lazy-load the HF image-classification pipeline."""
    global _pipeline
    if _pipeline is None:
        from transformers import pipeline as hf_pipeline  # local import: heavy
        _pipeline = hf_pipeline("image-classification", model=MODEL_ID)
    return _pipeline


def warmup() -> None:
    """Trigger model load. Called at API server boot to avoid first-request slowness."""
    _get_pipeline()


def _classify(image_bytes: bytes) -> float:
    """Return P(artificial) ∈ [0, 1]."""
    pipe = _get_pipeline()
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    results = pipe(img)
    # Pipeline returns list of {"label": str, "score": float}.
    # The artificial-class label varies per model: "artificial", "AI", "fake", "Synthetic".
    artificial_keywords = {"artificial", "ai", "fake", "synthetic", "generated"}
    for r in results:
        label = str(r.get("label", "")).strip().lower()
        if any(kw in label for kw in artificial_keywords):
            return float(r.get("score", 0.0))
    # Fall back to 1 - max("real"/"human") score.
    real_keywords = {"real", "human", "natural", "authentic"}
    for r in results:
        label = str(r.get("label", "")).strip().lower()
        if any(kw in label for kw in real_keywords):
            return 1.0 - float(r.get("score", 0.0))
    return 0.0


def run(image_bytes: bytes) -> DetectorSignal:
    started = time.monotonic()
    p = _classify(image_bytes)
    elapsed_ms = int((time.monotonic() - started) * 1000)

    if p < 0.5:
        sev = Severity.pass_
    elif p < 0.85:
        sev = Severity.warn
    else:
        sev = Severity.fail

    return DetectorSignal(
        detector=NAME, severity=sev, score=round(p, 4),
        evidence=f"p(artificial)={p:.2f}", latency_ms=elapsed_ms,
    )
