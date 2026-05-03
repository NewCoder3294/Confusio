"""Tests for the synthid detector."""
from unittest.mock import patch

from defensive.engine.detectors.synthid import run as synthid_run
from defensive.engine.verdict import Severity


class TestSynthid:
    def test_skipped_without_credentials_returns_warn(self, tiny_jpeg_bytes):
        with patch(
            "defensive.engine.detectors.synthid.verify_google_watermark",
            return_value={"status": "skipped", "detail": "no GCP project"},
        ):
            sig = synthid_run(tiny_jpeg_bytes)
        assert sig.detector == "synthid"
        assert sig.severity is Severity.warn

    def test_watermark_detected_returns_fail(self, tiny_jpeg_bytes):
        with patch(
            "defensive.engine.detectors.synthid.verify_google_watermark",
            return_value={"status": "ok", "decision": "WATERMARK_DETECTED"},
        ):
            sig = synthid_run(tiny_jpeg_bytes)
        assert sig.severity is Severity.fail
        assert "detected" in sig.evidence.lower()

    def test_watermark_not_detected_returns_warn(self, tiny_jpeg_bytes):
        with patch(
            "defensive.engine.detectors.synthid.verify_google_watermark",
            return_value={"status": "ok", "decision": "WATERMARK_NOT_DETECTED"},
        ):
            sig = synthid_run(tiny_jpeg_bytes)
        assert sig.severity is Severity.warn
        assert "absent" in sig.evidence.lower()
