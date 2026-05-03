"""Error Level Analysis detector.

Re-saves the image at JPEG quality 90, computes mean per-pixel absolute
difference, normalises to [0, 1] by dividing by 255 * channel count.
Higher values suggest splice / edit boundaries.
"""
from __future__ import annotations

import io
import time

from PIL import Image, ImageChops

from defensive.engine.verdict import DetectorSignal, Severity

NAME = "ela"
RESAVE_QUALITY = 90


def run(image_bytes: bytes) -> DetectorSignal:
    started = time.monotonic()

    original = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    buf = io.BytesIO()
    original.save(buf, format="JPEG", quality=RESAVE_QUALITY)
    resaved = Image.open(io.BytesIO(buf.getvalue())).convert("RGB")

    diff = ImageChops.difference(original, resaved)
    pixels = list(diff.getdata()) if not hasattr(diff, "get_flattened_data") else list(diff.get_flattened_data())
    if not pixels:
        score = 0.0
    else:
        total = sum(sum(p) for p in pixels)
        max_val = 255 * 3 * len(pixels)
        score = total / max_val

    elapsed_ms = int((time.monotonic() - started) * 1000)

    if score <= 0.2:
        sev = Severity.pass_
        evidence = f"ELA={score:.3f} (within nominal)"
    elif score <= 0.4:
        sev = Severity.warn
        evidence = f"ELA={score:.3f} (elevated)"
    else:
        sev = Severity.fail
        evidence = f"ELA={score:.3f} (splice indicators)"

    return DetectorSignal(
        detector=NAME, severity=sev, score=round(score, 4),
        evidence=evidence, latency_ms=elapsed_ms,
    )
