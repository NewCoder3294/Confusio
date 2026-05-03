"""Unit tests for the gemini_visual detector."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from defensive.engine.detectors.gemini_visual import _parse_response, run
from defensive.engine.verdict import Severity


class TestGeminiVisualRun:
    def test_synthetic_verdict_returns_fail(self):
        fake = {
            "verdict": "synthetic",
            "synthid_detected": True,
            "confidence": 0.95,
            "reasoning": "clear AI artifacts",
        }
        with patch("defensive.engine.detectors.gemini_visual._call_gemini", return_value=fake):
            sig = run(b"fake-image-bytes")
        assert sig.severity is Severity.fail
        assert sig.score == pytest.approx(0.95)
        assert "SynthID detected" in sig.evidence
        assert "clear AI artifacts" in sig.evidence

    def test_authentic_verdict_returns_pass(self):
        fake = {
            "verdict": "authentic",
            "synthid_detected": False,
            "confidence": 0.88,
            "reasoning": "natural grain and lighting consistent with DSLR",
        }
        with patch("defensive.engine.detectors.gemini_visual._call_gemini", return_value=fake):
            sig = run(b"fake-image-bytes")
        assert sig.severity is Severity.pass_
        assert sig.score == pytest.approx(0.88)
        assert "natural grain" in sig.evidence

    def test_uncertain_verdict_returns_warn(self):
        fake = {
            "verdict": "uncertain",
            "synthid_detected": False,
            "confidence": 0.55,
            "reasoning": "mixed signals, possibly composited",
        }
        with patch("defensive.engine.detectors.gemini_visual._call_gemini", return_value=fake):
            sig = run(b"fake-image-bytes")
        assert sig.severity is Severity.warn
        assert sig.score == pytest.approx(0.55)


class TestParseResponse:
    def test_parse_response_strips_markdown_fences(self):
        raw = (
            "```json\n"
            '{"verdict":"authentic","synthid_detected":false,"confidence":0.9,"reasoning":"x"}\n'
            "```"
        )
        result = _parse_response(raw)
        assert result["verdict"] == "authentic"
        assert result["synthid_detected"] is False
        assert result["confidence"] == pytest.approx(0.9)
        assert result["reasoning"] == "x"

    def test_parse_response_plain_json(self):
        raw = '{"verdict":"synthetic","synthid_detected":true,"confidence":0.97,"reasoning":"obvious artifacts"}'
        result = _parse_response(raw)
        assert result["verdict"] == "synthetic"
        assert result["synthid_detected"] is True

    def test_parse_response_raises_on_no_json(self):
        with pytest.raises(ValueError, match="no JSON object"):
            _parse_response("This is plain prose with no JSON.")
