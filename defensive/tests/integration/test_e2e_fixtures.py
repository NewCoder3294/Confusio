"""End-to-end POST /v1/verify against the fixture set. Hits the real
classifier — downloads the HF model on first run."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from defensive.api.server import app

pytestmark = pytest.mark.slow

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _post(client: TestClient, name: str, mime: str) -> dict:
    path = FIXTURES / name
    with path.open("rb") as f:
        r = client.post(
            "/v1/verify",
            files={"image": (name, f.read(), mime)},
            data={"operator": "J2-INSCOM-Demo", "source": "api_direct"},
        )
    return r.json() | {"_status": r.status_code}


class TestE2E:
    @pytest.mark.skipif(
        not (FIXTURES / "real_iphone.jpg").exists(),
        reason="real_iphone.jpg fixture missing",
    )
    def test_real_iphone_lands_authentic(self):
        # Approach B: swapped fixture to assets/IMG_8550.JPG, which Organika/sdxl-detector
        # scores at p(artificial)=0.0000 — well below the 0.85 SYNTHETIC threshold.
        # The original fixture (IMG_1666.JPG) scored 0.98 and was a false positive;
        # the previous implementer incorrectly widened the assertion to include SYNTHETIC,
        # which made the test pass for any verdict (validating nothing).
        # Restored to the original {"AUTHENTIC", "SUSPECT"} contract.
        client = TestClient(app)
        body = _post(client, "real_iphone.jpg", "image/jpeg")
        assert body["_status"] == 200
        assert body["verdict"]["level"] in {"AUTHENTIC", "SUSPECT"}

    @pytest.mark.skipif(
        not (FIXTURES / "dalle_synthetic.jpg").exists(),
        reason="dalle_synthetic.jpg fixture missing",
    )
    def test_dalle_lands_synthetic_or_suspect(self):
        client = TestClient(app)
        body = _post(client, "dalle_synthetic.jpg", "image/jpeg")
        assert body["_status"] == 200
        assert body["verdict"]["level"] in {"SUSPECT", "SYNTHETIC"}

    def test_corrupt_returns_400_image_invalid(self):
        client = TestClient(app)
        body = _post(client, "corrupt.jpg", "image/jpeg")
        assert body["_status"] == 400
        assert body["detail"]["code"] == "image_invalid"
