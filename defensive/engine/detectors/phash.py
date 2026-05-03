"""Perceptual-hash lookup against a local stock-corpus."""
from __future__ import annotations

import io
import time
from pathlib import Path

import imagehash
from PIL import Image

from defensive.engine.verdict import DetectorSignal, Severity

NAME = "phash"
CORPUS_DIR = Path(__file__).parent / "_phash_corpus"
HAMMING_PARTIAL_MAX = 8


def run(image_bytes: bytes) -> DetectorSignal:
    started = time.monotonic()
    target = imagehash.phash(Image.open(io.BytesIO(image_bytes)))

    best_distance: int | None = None
    best_path: Path | None = None
    if CORPUS_DIR.exists():
        for entry in CORPUS_DIR.iterdir():
            if entry.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                continue
            try:
                ref = imagehash.phash(Image.open(entry))
            except Exception:
                continue
            d = target - ref
            if best_distance is None or d < best_distance:
                best_distance = d
                best_path = entry

    elapsed_ms = int((time.monotonic() - started) * 1000)

    if best_distance is None:
        return DetectorSignal(
            detector=NAME, severity=Severity.pass_, score=None,
            evidence="no stock-corpus match (corpus empty)",
            latency_ms=elapsed_ms,
        )
    if best_distance == 0:
        return DetectorSignal(
            detector=NAME, severity=Severity.fail, score=float(best_distance),
            evidence=f"exact match: {best_path.name if best_path else '?'}",
            latency_ms=elapsed_ms,
        )
    if best_distance <= HAMMING_PARTIAL_MAX:
        return DetectorSignal(
            detector=NAME, severity=Severity.warn, score=float(best_distance),
            evidence=f"partial match (d={best_distance}): {best_path.name if best_path else '?'}",
            latency_ms=elapsed_ms,
        )
    return DetectorSignal(
        detector=NAME, severity=Severity.pass_, score=float(best_distance),
        evidence="no stock-corpus match",
        latency_ms=elapsed_ms,
    )
