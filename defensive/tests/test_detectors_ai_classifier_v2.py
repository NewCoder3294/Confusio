"""Tests for the ai_classifier_v2 detector."""
from unittest.mock import patch

from defensive.engine.detectors.ai_classifier_v2 import (
    run as ai_v2_run,
    warmup,
)
from defensive.engine.verdict import Severity


class TestAiClassifierV2:
    def test_low_probability_returns_pass(self, tiny_jpeg_bytes):
        with patch(
            "defensive.engine.detectors.ai_classifier_v2._classify",
            return_value=0.10,
        ):
            sig = ai_v2_run(tiny_jpeg_bytes)
        assert sig.detector == "ai_classifier_v2"
        assert sig.severity is Severity.pass_
        assert sig.score == 0.10

    def test_mid_probability_returns_warn(self, tiny_jpeg_bytes):
        with patch(
            "defensive.engine.detectors.ai_classifier_v2._classify",
            return_value=0.62,
        ):
            sig = ai_v2_run(tiny_jpeg_bytes)
        assert sig.severity is Severity.warn
        assert sig.score == 0.62

    def test_high_probability_returns_fail(self, tiny_jpeg_bytes):
        with patch(
            "defensive.engine.detectors.ai_classifier_v2._classify",
            return_value=0.94,
        ):
            sig = ai_v2_run(tiny_jpeg_bytes)
        assert sig.severity is Severity.fail
        assert sig.score == 0.94
        assert "0.94" in sig.evidence

    def test_warmup_invokes_classifier_loader(self):
        with patch(
            "defensive.engine.detectors.ai_classifier_v2._get_pipeline",
        ) as mock_loader:
            warmup()
        mock_loader.assert_called_once()
