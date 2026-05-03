"""Second AI-image classifier — umm-maybe/AI-image-detector.

Older, lighter model than Organika/sdxl-detector. Independent signal in
the composite. Lazy-loaded, warmable at boot.
"""
from __future__ import annotations

import io
import time
from typing import Any

from PIL import Image

from defensive.engine.verdict import DetectorSignal, Severity

NAME = "ai_classifier_v2"
MODEL_ID = "umm-maybe/AI-image-detector"

_pipeline: Any = None


def _get_pipeline() -> Any:
    global _pipeline
    if _pipeline is None:
        from transformers import pipeline as hf_pipeline
        _pipeline = hf_pipeline("image-classification", model=MODEL_ID)
    return _pipeline


def warmup() -> None:
    _get_pipeline()


def _classify(image_bytes: bytes) -> float:
    pipe = _get_pipeline()
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    results = pipe(img)
    artificial_keywords = {"artificial", "ai", "fake", "synthetic", "generated"}
    for r in results:
        label = str(r.get("label", "")).strip().lower()
        if any(kw in label for kw in artificial_keywords):
            return float(r.get("score", 0.0))
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
        evidence=f"p(artificial)={p:.2f} (umm-maybe)", latency_ms=elapsed_ms,
    )
