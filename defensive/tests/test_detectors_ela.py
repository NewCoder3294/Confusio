"""Tests for the ela detector."""
import io

from PIL import Image

from defensive.engine.detectors.ela import run as ela_run
from defensive.engine.verdict import Severity


def _solid_jpeg(quality: int = 95) -> bytes:
    img = Image.new("RGB", (64, 64), color=(80, 120, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


class TestEla:
    def test_solid_image_returns_pass(self):
        # Solid colour ⇒ no compression artefacts to expose ⇒ very low ELA.
        sig = ela_run(_solid_jpeg())
        assert sig.detector == "ela"
        assert sig.severity is Severity.pass_
        assert sig.score is not None
        assert 0.0 <= sig.score <= 0.2

    def test_score_in_range(self):
        sig = ela_run(_solid_jpeg())
        assert sig.score is not None
        assert 0.0 <= sig.score <= 1.0
