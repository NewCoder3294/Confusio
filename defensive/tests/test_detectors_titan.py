"""Tests for the titan detector."""
from unittest.mock import patch

from defensive.engine.detectors.titan import run as titan_run
from defensive.engine.verdict import Severity


class TestTitan:
    def test_credentials_missing_returns_na(self, tiny_jpeg_bytes):
        with patch(
            "defensive.engine.detectors.titan.detect_titan_watermark",
            side_effect=RuntimeError("No AWS credentials found"),
        ):
            sig = titan_run(tiny_jpeg_bytes)
        assert sig.detector == "titan"
        assert sig.severity is Severity.na
        assert "unavailable" in sig.evidence.lower()

    def test_watermark_detected_returns_fail(self, tiny_jpeg_bytes):
        with patch(
            "defensive.engine.detectors.titan.detect_titan_watermark",
            return_value={"detection": "WATERMARK_DETECTED", "confidence": 0.99},
        ):
            sig = titan_run(tiny_jpeg_bytes)
        assert sig.severity is Severity.fail
        assert "titan" in sig.evidence.lower()

    def test_watermark_absent_returns_warn(self, tiny_jpeg_bytes):
        with patch(
            "defensive.engine.detectors.titan.detect_titan_watermark",
            return_value={"detection": "WATERMARK_NOT_DETECTED"},
        ):
            sig = titan_run(tiny_jpeg_bytes)
        assert sig.severity is Severity.warn
        assert "absent" in sig.evidence.lower()
