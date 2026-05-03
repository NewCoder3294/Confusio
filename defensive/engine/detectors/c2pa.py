"""C2PA / Content-Credentials detector. Wraps src/mendacity/c2pa_report."""
from __future__ import annotations

import time

from mendacity.c2pa_report import read_c2pa  # read-only import

from defensive.engine.verdict import DetectorSignal, Severity

NAME = "c2pa"


def run(image_bytes: bytes, *, mime_type: str = "image/jpeg") -> DetectorSignal:
    """Severity:
      pass — valid manifest with passing validation
      na   — manifest absent (the norm; absence is not evidence)
      fail — manifest present but validation failed
    """
    started = time.monotonic()
    report = read_c2pa(mime_type, image_bytes)
    elapsed_ms = int((time.monotonic() - started) * 1000)

    status = report.get("status")
    if status == "manifest_not_found":
        return DetectorSignal(
            detector=NAME, severity=Severity.na, score=None,
            evidence="no manifest", latency_ms=elapsed_ms,
        )
    if status == "error":
        return DetectorSignal(
            detector=NAME, severity=Severity.na, score=None,
            evidence=f"reader error: {report.get('error_type', 'unknown')}",
            latency_ms=elapsed_ms,
        )

    validation = (report.get("validation_state") or "").lower()
    if validation and validation != "valid":
        return DetectorSignal(
            detector=NAME, severity=Severity.fail, score=None,
            evidence=f"validation_state={validation}", latency_ms=elapsed_ms,
        )
    return DetectorSignal(
        detector=NAME, severity=Severity.pass_, score=None,
        evidence="manifest valid", latency_ms=elapsed_ms,
    )
