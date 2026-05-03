"""Tests for the exif detector."""
import io

from PIL import Image

from defensive.engine.detectors.exif import (
    GENERATOR_SOFTWARE_KEYWORDS,
    run as exif_run,
)
from defensive.engine.verdict import Severity


def _jpeg_with_software(software: str) -> bytes:
    """Build a minimal JPEG with EXIF Software tag set."""
    img = Image.new("RGB", (16, 16), color=(0, 0, 0))
    buf = io.BytesIO()
    exif = img.getexif()
    exif[0x0131] = software  # 0x0131 = Software tag
    img.save(buf, format="JPEG", exif=exif.tobytes())
    return buf.getvalue()


class TestExif:
    def test_no_exif_returns_warn(self, tiny_jpeg_bytes):
        # tiny_jpeg_bytes is built without an EXIF block
        sig = exif_run(tiny_jpeg_bytes)
        assert sig.detector == "exif"
        assert sig.severity is Severity.warn
        assert "exif" in sig.evidence.lower()

    def test_clean_exif_returns_pass(self):
        bytes_ = _jpeg_with_software("Apple iPhone 14 Pro")
        sig = exif_run(bytes_)
        assert sig.severity is Severity.pass_

    def test_stable_diffusion_software_returns_fail(self):
        bytes_ = _jpeg_with_software("Stable Diffusion")
        sig = exif_run(bytes_)
        assert sig.severity is Severity.fail
        assert "stable diffusion" in sig.evidence.lower()

    def test_midjourney_software_returns_fail(self):
        bytes_ = _jpeg_with_software("Midjourney v6")
        sig = exif_run(bytes_)
        assert sig.severity is Severity.fail

    def test_known_keyword_set(self):
        # Document the keyword list — changes here change behavior
        assert "stable diffusion" in GENERATOR_SOFTWARE_KEYWORDS
        assert "midjourney" in GENERATOR_SOFTWARE_KEYWORDS
        assert "dall-e" in GENERATOR_SOFTWARE_KEYWORDS
        assert "imagen" in GENERATOR_SOFTWARE_KEYWORDS
        assert "firefly" in GENERATOR_SOFTWARE_KEYWORDS
