"""Adaptive LSB steganography with key-derived seeded placement.

Design tradeoffs:

  - **Spatial-domain LSB on PNG output** is what we use for the demo. This
    survives only if the image is delivered as a PNG/lossless file (Telegram
    "send as document"). It does NOT survive Telegram photo-upload re-encoding.

  - For JPEG-survivable embedding (true J-UNIWARD-class), see notes in
    embed_jpeg() — that is a much heavier dependency (libjpeg coefficient access
    via jpeglib-python or piexif extension) and is stubbed but not yet
    implemented end-to-end. Both modes share the same payload framing and key
    schedule.

Payload framing:

    [4 bytes magic 'MNDC'] [4 bytes payload length BE] [payload bytes] [HMAC-SHA256(key, payload)]

Placement schedule:

    PRNG seeded with HMAC-SHA256(key, b"placement") yields a permutation of
    pixel-LSB indices. The first N indices receive the framed payload bits.
    Without the key, an adversary cannot tell which subset of LSBs carries the
    payload; statistical detection is harder than naive sequential LSB.

Adaptivity:

    To stay below steganalysis thresholds, we cap payload at 5% of LSB capacity
    by default. Embedding rate above ~10% is detectable by chi-squared tests on
    the LSB distribution; below 5% even trained CNN detectors lose accuracy
    sharply on standard benchmarks.

Out-of-scope:

    - True DCT-domain JPEG embedding (J-UNIWARD/HILL): would require building
      against libjpeg coefficient access. Stub provided; full implementation
      is research-grade.
    - Generative cover synthesis: not in scope.
"""
from __future__ import annotations

import hashlib
import hmac
import struct
from pathlib import Path
from typing import Tuple

import numpy as np
from PIL import Image


MAGIC = b"MNDC"
HMAC_LEN = 32
HEADER_LEN = 4 + 4  # magic + length
MAX_PAYLOAD_FRACTION = 0.05  # 5% of LSB capacity


def _placement_permutation(key: bytes, n: int) -> np.ndarray:
    """Return a deterministic permutation of [0, n) seeded by ``key``.

    Identical key + n always returns identical permutation (used by extract).
    """
    seed_bytes = hmac.new(key, b"placement", hashlib.sha256).digest()
    seed = int.from_bytes(seed_bytes[:8], "big") & 0xFFFFFFFFFFFFFFFF
    rng = np.random.default_rng(seed)
    return rng.permutation(n)


def _frame_payload(payload: bytes, key: bytes) -> bytes:
    """Wrap payload with magic + length + HMAC."""
    if len(payload) > 0xFFFFFFFF:
        raise ValueError("payload too large (>4GB)")
    framed = MAGIC + struct.pack(">I", len(payload)) + payload
    tag = hmac.new(key, framed, hashlib.sha256).digest()
    return framed + tag


def _bytes_to_bits(b: bytes) -> np.ndarray:
    arr = np.frombuffer(b, dtype=np.uint8)
    bits = np.unpackbits(arr, bitorder="big")
    return bits.astype(np.uint8)


def embed(
    cover_path: Path,
    payload: bytes,
    key: bytes,
    output_path: Path,
) -> Tuple[Path, dict]:
    """Embed ``payload`` into the LSBs of ``cover_path``, writing PNG to ``output_path``.

    Output is PNG (lossless) — this preserves LSBs. Use the JPEG-survivable
    variant if the carrier must round-trip through JPEG recompression.

    Returns (output_path, metadata) where metadata contains:
        capacity_bits, used_bits, fraction_used, magic, hmac_hex
    """
    cover_path = Path(cover_path)
    output_path = Path(output_path)
    output_path = output_path.with_suffix(".png")  # force PNG

    with Image.open(cover_path) as im:
        im.load()
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGB")
        rgb = np.asarray(im, dtype=np.uint8).copy()

    H, W, C = rgb.shape
    capacity_bits = H * W * C
    framed = _frame_payload(payload, key)
    bits = _bytes_to_bits(framed)
    needed = bits.size
    fraction = needed / capacity_bits

    if fraction > MAX_PAYLOAD_FRACTION:
        raise ValueError(
            f"payload too large: needs {fraction:.1%} of LSB capacity, "
            f"max is {MAX_PAYLOAD_FRACTION:.0%} (steganalysis threshold). "
            f"Capacity = {capacity_bits // 8} bytes; payload = {len(framed)} bytes."
        )

    perm = _placement_permutation(key, capacity_bits)
    indices = perm[:needed]

    flat = rgb.reshape(-1)
    flat[indices] = (flat[indices] & 0xFE) | bits
    out = flat.reshape(H, W, C)

    Image.fromarray(out).save(output_path, format="PNG", optimize=True)

    return output_path, {
        "capacity_bits": int(capacity_bits),
        "used_bits": int(needed),
        "fraction_used": float(fraction),
        "magic": MAGIC.decode(),
        "hmac_hex": framed[-HMAC_LEN:].hex() if False else "(in framed payload)",
    }


def embed_jpeg(cover_path: Path, payload: bytes, key: bytes, output_path: Path):
    """Stub: JPEG-DCT-coefficient embedding (survives JPEG recompression).

    Not implemented. Requires libjpeg coefficient access. The current ``embed``
    function with PNG output is the supported path.
    """
    raise NotImplementedError(
        "JPEG-DCT embedding not implemented. Use embed() with PNG output, or "
        "deliver as Telegram document to bypass JPEG recompression."
    )
