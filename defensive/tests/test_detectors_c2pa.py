"""Tests for the c2pa detector."""
from unittest.mock import patch

import pytest

from defensive.engine.detectors.c2pa import run as c2pa_run
from defensive.engine.verdict import Severity


class TestC2pa:
    def test_no_manifest_returns_na(self, tiny_jpeg_bytes):
        # Absence of a C2PA manifest is the norm — should not poison verdict.
        with patch(
            "defensive.engine.detectors.c2pa.read_c2pa",
            return_value={"status": "manifest_not_found"},
        ):
            sig = c2pa_run(tiny_jpeg_bytes, mime_type="image/jpeg")
        assert sig.detector == "c2pa"
        assert sig.severity is Severity.na
        assert "manifest" in sig.evidence.lower()

    def test_valid_manifest_returns_pass(self, tiny_jpeg_bytes):
        with patch(
            "defensive.engine.detectors.c2pa.read_c2pa",
            return_value={
                "status": "ok",
                "validation_state": "Valid",
                "active_manifest": {},
            },
        ):
            sig = c2pa_run(tiny_jpeg_bytes, mime_type="image/jpeg")
        assert sig.severity is Severity.pass_

    def test_invalid_validation_returns_fail(self, tiny_jpeg_bytes):
        with patch(
            "defensive.engine.detectors.c2pa.read_c2pa",
            return_value={
                "status": "ok",
                "validation_state": "Invalid",
                "active_manifest": {},
            },
        ):
            sig = c2pa_run(tiny_jpeg_bytes, mime_type="image/jpeg")
        assert sig.severity is Severity.fail
