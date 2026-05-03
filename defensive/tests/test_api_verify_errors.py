"""Tests for POST /v1/verify error cases."""
import io

from fastapi.testclient import TestClient
from PIL import Image

from defensive.api.server import MAX_BYTES, app


def _png_bytes() -> bytes:
    img = Image.new("RGB", (8, 8), color=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestErrors:
    def test_unsupported_mime_returns_400(self):
        client = TestClient(app)
        r = client.post(
            "/v1/verify",
            files={"image": ("x.gif", b"GIF89a", "image/gif")},
            data={"operator": "op", "source": "verify_tab"},
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "unsupported_mime"

    def test_image_too_large_returns_400(self):
        client = TestClient(app)
        big = b"\x00" * (MAX_BYTES + 1)
        r = client.post(
            "/v1/verify",
            files={"image": ("big.png", big, "image/png")},
            data={"operator": "op", "source": "verify_tab"},
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "image_too_large"

    def test_image_invalid_returns_400(self):
        client = TestClient(app)
        r = client.post(
            "/v1/verify",
            files={"image": ("x.png", b"not an image", "image/png")},
            data={"operator": "op", "source": "verify_tab"},
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "image_invalid"
