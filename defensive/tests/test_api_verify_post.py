"""Tests for POST /v1/verify."""
import io
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from defensive.api.server import app
from defensive.engine.verdict import (
    DetectorSignal,
    Severity,
    Verdict,
    VerdictLevel,
)


@pytest.fixture(autouse=True)
def _patch_warmup(monkeypatch):
    """Prevent the lifespan warm-up from downloading the HF model in every test."""
    from defensive.api import server
    monkeypatch.setattr(server, "_warmup_classifier", lambda: None)


def _png_bytes() -> bytes:
    img = Image.new("RGB", (16, 16), color=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _stub_verdict() -> Verdict:
    return Verdict(
        level=VerdictLevel.AUTHENTIC, confidence=0.92,
        summary="ok",
        signals=[DetectorSignal("c2pa", Severity.pass_, None, "ok", 1)],
    )


class TestPostVerify:
    def test_returns_200_with_verdict_shape(self):
        client = TestClient(app)
        with patch("defensive.api.server.composite_run", return_value=_stub_verdict()):
            r = client.post(
                "/v1/verify",
                files={"image": ("x.png", _png_bytes(), "image/png")},
                data={"operator": "J2-INSCOM-Demo", "source": "verify_tab"},
            )
        assert r.status_code == 200
        body = r.json()
        assert "artifact_id" in body
        assert body["verdict"]["level"] == "AUTHENTIC"
        assert body["verdict"]["confidence"] == 0.92
        assert body["operator"] == "J2-INSCOM-Demo"
        assert body["submitted_via"] == "verify_tab"
        assert body["sha256"]
        assert "submitted_at" in body

    def test_records_audit_row(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DEFENSIVE_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
        client = TestClient(app)
        with patch("defensive.api.server.composite_run", return_value=_stub_verdict()):
            client.post(
                "/v1/verify",
                files={"image": ("x.png", _png_bytes(), "image/png")},
                data={"operator": "J2-INSCOM-Demo", "source": "verify_tab"},
            )
        assert (tmp_path / "audit.jsonl").exists()


class TestStartup:
    def test_lifespan_calls_warmup(self):
        from defensive.api import server
        with patch.object(server, "_warmup_classifier") as mock:
            with TestClient(server.app):
                pass
        mock.assert_called_once()
