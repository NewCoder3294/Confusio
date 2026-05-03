"""Tests for GET /v1/verify/{artifact_id}."""
import io
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from defensive.api.server import app
from defensive.engine.verdict import (
    DetectorSignal,
    Severity,
    Verdict,
    VerdictLevel,
)


def _png() -> bytes:
    img = Image.new("RGB", (8, 8), color=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestGetVerify:
    def test_round_trip_after_post(self):
        client = TestClient(app)
        v = Verdict(
            VerdictLevel.AUTHENTIC, 0.91, "ok",
            [DetectorSignal("c2pa", Severity.pass_, None, "ok", 1)],
        )
        with patch("defensive.api.server.composite_run", return_value=v):
            posted = client.post(
                "/v1/verify",
                files={"image": ("x.png", _png(), "image/png")},
                data={"operator": "op", "source": "verify_tab"},
            ).json()

        r = client.get(f"/v1/verify/{posted['artifact_id']}")
        assert r.status_code == 200
        body = r.json()
        assert body["artifact_id"] == posted["artifact_id"]
        assert body["sha256"] == posted["sha256"]
        assert body["verdict"]["level"] == "AUTHENTIC"

    def test_unknown_id_returns_404(self):
        client = TestClient(app)
        r = client.get("/v1/verify/does-not-exist")
        assert r.status_code == 404
        assert r.json()["detail"]["code"] == "artifact_not_found"
