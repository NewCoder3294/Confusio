"""Detector modules — each exposes a NAME constant and a run(image_bytes) function."""
from defensive.engine.detectors import (  # noqa: F401
    ai_classifier,
    ai_classifier_v2,
    c2pa,
    ela,
    exif,
    phash,
    synthid,
    titan,
)
