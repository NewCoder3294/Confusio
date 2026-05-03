"""Amazon Titan watermark detector. Wraps src/mendacity/titan."""
from __future__ import annotations

import time

from mendacity.titan import detect_titan_watermark

from defensive.engine.verdict import DetectorSignal, Severity

NAME = "titan"


def run(image_bytes: bytes) -> DetectorSignal:
    """Severity:
      pass — n/a (absence is the norm; never returned)
      warn — watermark absent or detector unavailable (no AWS creds)
      fail — watermark detected (i.e., image was Titan-generated)
    """
    started = time.monotonic()
    try:
        report = detect_titan_watermark(image_bytes)
    except RuntimeError as e:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return DetectorSignal(
            detector=NAME, severity=Severity.na, score=None,
            evidence=f"detector unavailable: {type(e).__name__}",
            latency_ms=elapsed_ms,
        )
    elapsed_ms = int((time.monotonic() - started) * 1000)

    decision = (report.get("detection") or "").upper()
    if decision == "WATERMARK_DETECTED":
        return DetectorSignal(
            detector=NAME, severity=Severity.fail, score=None,
            evidence="Titan watermark detected", latency_ms=elapsed_ms,
        )
    return DetectorSignal(
        detector=NAME, severity=Severity.warn, score=None,
        evidence="absent", latency_ms=elapsed_ms,
    )
