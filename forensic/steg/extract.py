"""Extract a payload embedded by :mod:`forensic.steg.embed`.

Symmetric to embed.py — derives the same permutation from the key, reads bits
at those indices, validates magic + length + HMAC, and returns the raw payload
bytes.
"""
from __future__ import annotations

import hashlib
import hmac
import struct
from pathlib import Path

import numpy as np
from PIL import Image

from .embed import MAGIC, HMAC_LEN, HEADER_LEN, _placement_permutation


class StegExtractError(Exception):
    pass


def _bits_to_bytes(bits: np.ndarray) -> bytes:
    n = (bits.size // 8) * 8
    return np.packbits(bits[:n].astype(np.uint8), bitorder="big").tobytes()


def extract(stego_path: Path, key: bytes) -> bytes:
    """Recover the embedded payload bytes from ``stego_path`` using ``key``.

    Raises StegExtractError if the magic header, length, or HMAC don't validate.
    """
    stego_path = Path(stego_path)

    with Image.open(stego_path) as im:
        im.load()
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGB")
        rgb = np.asarray(im, dtype=np.uint8)

    H, W, C = rgb.shape
    capacity_bits = H * W * C
    perm = _placement_permutation(key, capacity_bits)
    flat = rgb.reshape(-1)

    # Read header first (magic 4B + length 4B = 64 bits).
    header_bits = (flat[perm[: HEADER_LEN * 8]] & 1).astype(np.uint8)
    header = _bits_to_bytes(header_bits)
    if header[:4] != MAGIC:
        raise StegExtractError(
            f"magic mismatch — expected {MAGIC!r}, got {header[:4]!r}. "
            f"Wrong key or no embedded payload."
        )
    payload_len = struct.unpack(">I", header[4:8])[0]

    total_bits = (HEADER_LEN + payload_len + HMAC_LEN) * 8
    if total_bits > capacity_bits:
        raise StegExtractError(f"declared payload length {payload_len} exceeds image capacity")

    body_bits = (flat[perm[:total_bits]] & 1).astype(np.uint8)
    body = _bits_to_bytes(body_bits)

    framed = body[: HEADER_LEN + payload_len]
    payload = framed[HEADER_LEN:]
    tag = body[HEADER_LEN + payload_len : HEADER_LEN + payload_len + HMAC_LEN]

    expected = hmac.new(key, framed, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected):
        raise StegExtractError("HMAC validation failed — payload tampered or wrong key")

    return payload
