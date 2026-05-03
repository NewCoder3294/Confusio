"""Tests for _shared.safe_run — detector-error isolation."""
import time

import pytest

from defensive.engine.detectors._shared import safe_run
from defensive.engine.verdict import DetectorSignal, Severity


def _ok_detector(image_bytes: bytes) -> DetectorSignal:
    return DetectorSignal(
        detector="dummy", severity=Severity.pass_, score=0.0,
        evidence="ok", latency_ms=0,
    )


def _raising_detector(image_bytes: bytes) -> DetectorSignal:
    raise ValueError("boom")


class TestSafeRun:
    def test_passes_through_successful_signal(self):
        sig = safe_run("dummy", _ok_detector, b"")
        assert sig.severity is Severity.pass_
        assert sig.evidence == "ok"

    def test_returns_na_signal_on_exception(self):
        sig = safe_run("dummy", _raising_detector, b"")
        assert sig.detector == "dummy"
        assert sig.severity is Severity.na
        assert sig.evidence == "ValueError"
        assert sig.score is None

    def test_records_latency_even_on_exception(self):
        def slow_raise(_):
            time.sleep(0.05)
            raise RuntimeError("slow boom")
        sig = safe_run("dummy", slow_raise, b"")
        assert sig.latency_ms >= 50
