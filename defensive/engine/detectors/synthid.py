"""SynthID watermark detector (Google Imagen). Wraps src/mendacity/google_wm."""
from __future__ import annotations

import time

from mendacity.google_wm import verify_google_watermark

from defensive.engine.verdict import DetectorSignal, Severity

NAME = "synthid"


def run(image_bytes: bytes) -> DetectorSignal:
    """Severity:
      pass — n/a (absence is the norm; never returned)
      warn — watermark absent or detector unavailable (no GCP creds)
      fail — watermark detected (i.e., image was Google-generated)
    """
    started = time.monotonic()
    report = verify_google_watermark(image_bytes)
    elapsed_ms = int((time.monotonic() - started) * 1000)

    status = report.get("status")
    if status != "ok":
        return DetectorSignal(
            detector=NAME, severity=Severity.warn, score=None,
            evidence=f"detector unavailable: {status or 'unknown'}",
            latency_ms=elapsed_ms,
        )

    decision = (report.get("decision") or "").upper()
    if decision == "WATERMARK_DETECTED":
        return DetectorSignal(
            detector=NAME, severity=Severity.fail, score=None,
            evidence="SynthID watermark detected (Google-generated)",
            latency_ms=elapsed_ms,
        )
    return DetectorSignal(
        detector=NAME, severity=Severity.warn, score=None,
        evidence="absent", latency_ms=elapsed_ms,
    )
