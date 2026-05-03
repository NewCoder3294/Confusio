"""PRNU (Photo Response Non-Uniformity) sensor-fingerprint synthesis.

Two-step capability:
  1. extract.py  — estimate a PRNU pattern from a corpus of reference photos.
  2. inject.py   — multiplicatively blend that pattern into a synthetic image.

Together they cause PRNU correlation tests to score the synthetic image as
"sensor-consistent" with the claimed device class. State-of-tradecraft for
signature management.
"""
from __future__ import annotations

from . import extract, inject

__all__ = ["extract", "inject"]
