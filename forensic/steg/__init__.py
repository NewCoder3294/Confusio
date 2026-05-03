"""Covert side-channel via key-permuted spatial-domain LSB.

Pipeline:
  embed.py   — wrap payload (magic + length + HMAC) and write to PNG LSBs.
  extract.py — symmetric recovery, validates HMAC.
  analyze.py — chi-squared + RS self-checks; cover vs stego comparison.

PNG output is required to preserve LSBs; deliver as Telegram document.
"""
from __future__ import annotations

from . import embed, extract, analyze

__all__ = ["embed", "extract", "analyze"]
