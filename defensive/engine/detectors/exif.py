"""EXIF forensics detector. Flags missing EXIF and known-generator software tags."""
from __future__ import annotations

import io
import time

import exifread

from defensive.engine.verdict import DetectorSignal, Severity

NAME = "exif"

GENERATOR_SOFTWARE_KEYWORDS: set[str] = {
    "stable diffusion",
    "midjourney",
    "dall-e",
    "dalle",
    "imagen",
    "firefly",
    "leonardo",
    "playground",
}


def run(image_bytes: bytes) -> DetectorSignal:
    started = time.monotonic()
    tags = exifread.process_file(io.BytesIO(image_bytes), details=False)
    elapsed_ms = int((time.monotonic() - started) * 1000)

    if not tags:
        return DetectorSignal(
            detector=NAME, severity=Severity.warn, score=None,
            evidence="EXIF block absent", latency_ms=elapsed_ms,
        )

    software = str(tags.get("Image Software", "")).strip().lower()
    for keyword in GENERATOR_SOFTWARE_KEYWORDS:
        if keyword in software:
            return DetectorSignal(
                detector=NAME, severity=Severity.fail, score=None,
                evidence=f'Software="{tags.get("Image Software")}"',
                latency_ms=elapsed_ms,
            )

    return DetectorSignal(
        detector=NAME, severity=Severity.pass_, score=None,
        evidence=f"{len(tags)} EXIF tags, no generator markers",
        latency_ms=elapsed_ms,
    )
