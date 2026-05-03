"""Shared detector helpers — error isolation, timing."""
from __future__ import annotations

import time
from typing import Callable

from defensive.engine.verdict import DetectorSignal, Severity


def safe_run(
    name: str,
    fn: Callable[..., DetectorSignal],
    image_bytes: bytes,
    *args,
    **kwargs,
) -> DetectorSignal:
    """Run a detector function; on exception, return an n/a signal.

    The composite engine MUST never let one detector kill the request.
    """
    started = time.monotonic()
    try:
        return fn(image_bytes, *args, **kwargs)
    except Exception as e:  # noqa: BLE001 — intentional broad catch
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return DetectorSignal(
            detector=name,
            severity=Severity.na,
            score=None,
            evidence=type(e).__name__,
            latency_ms=elapsed_ms,
        )
