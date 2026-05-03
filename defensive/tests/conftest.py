"""Shared test fixtures."""
from __future__ import annotations


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "slow: integration tests that load the real ML model (skip with -m \"not slow\")",
    )

import io
from pathlib import Path

import pytest
from PIL import Image

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def tiny_jpeg_bytes() -> bytes:
    """A 32×32 solid grey JPEG. No EXIF, no C2PA. Used by detectors that
    need *some* valid image bytes but don't care about content."""
    img = Image.new("RGB", (32, 32), color=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def corrupt_image_bytes() -> bytes:
    """Bytes that are not a valid image."""
    return b"this is not an image"


def fixture_path(name: str) -> Path:
    """Return a path inside defensive/tests/fixtures/."""
    return FIXTURE_DIR / name


def fixture_bytes(name: str) -> bytes:
    """Read a fixture file as bytes. Used by integration tests."""
    return fixture_path(name).read_bytes()
