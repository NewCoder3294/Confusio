"""
Apple Camera Roll / DCIM-style **disk filenames**.

On device, photos usually appear as ``IMG_<counter>.JPG`` inside folders like
``DCIM/100APPLE/``. Exported files often keep that basename with ``.JPG`` or ``.jpg``.
This module builds those names so scripts can write ``IMG_5842.JPG`` instead of long
generator-style names — independent of embedded TIFF DocumentName metadata.
"""

from __future__ import annotations

import hashlib
import random
from pathlib import Path


def normalize_img_stem(raw: str) -> str:
    """Normalize user input to ``IMG_<digits>`` (e.g. ``5842`` or ``IMG_5842``)."""
    s = raw.strip()
    if not s:
        raise ValueError("empty stem")
    up = s.upper()
    if up.startswith("IMG_"):
        tail = s[4:]
        if not tail.isdigit():
            raise ValueError(f"stem after IMG_ must be digits: {raw!r}")
        return f"IMG_{int(tail)}"
    if s.isdigit():
        return f"IMG_{int(s)}"
    raise ValueError(f"expected IMG_XXXX or digits, got {raw!r}")


def infer_stem_from_exif_jpeg(piexif, jpeg_bytes: bytes) -> str:
    """Derive ``IMG_<1000..8999>`` from DateTime EXIF or from bytes hash."""
    try:
        d = piexif.load(jpeg_bytes)
    except Exception:
        d = {}
    exif_ifd = d.get("Exif") or {}
    dt = None
    for tag in (
        piexif.ExifIFD.DateTimeOriginal,
        piexif.ExifIFD.DateTimeDigitized,
    ):
        if tag in exif_ifd:
            raw = exif_ifd[tag]
            if isinstance(raw, bytes):
                dt = raw.decode("utf-8", errors="replace")
            elif isinstance(raw, str):
                dt = raw
            break
    if dt is None:
        zeroth = d.get("0th") or {}
        if piexif.ImageIFD.DateTime in zeroth:
            raw = zeroth[piexif.ImageIFD.DateTime]
            dt = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
    if dt:
        h = int(hashlib.sha256(dt.encode()).hexdigest()[:8], 16)
        num = 1000 + (h % 9000)
        return f"IMG_{num}"
    h = int(hashlib.sha256(jpeg_bytes).hexdigest()[:8], 16)
    num = 1000 + (h % 9000)
    return f"IMG_{num}"


def infer_stem_random() -> str:
    return f"IMG_{random.randint(1000, 9999)}"


def infer_stem_png_bytes(raw_bytes: bytes) -> str:
    """PNG without EXIF: stable IMG_ number from file hash."""
    h = int(hashlib.sha256(raw_bytes).hexdigest()[:8], 16)
    num = 1000 + (h % 9000)
    return f"IMG_{num}"


def apple_roll_disk_filename(
    normalized_img_stem: str,
    *,
    extension: str = "JPG",
) -> str:
    """
    Build a DCIM-style filename: ``IMG_5842.JPG``.

    ``normalized_img_stem`` must look like ``IMG_5842`` (use ``normalize_img_stem``).
    ``extension`` is without dot, typically ``JPG`` (DCIM-style) or ``jpg``.
    """
    if not normalized_img_stem.upper().startswith("IMG_"):
        raise ValueError(f"expected stem like IMG_5842, got {normalized_img_stem!r}")
    ext = extension.lstrip(".").upper()
    if ext == "JPEG":
        ext = "JPG"
    return f"{normalized_img_stem}.{ext}"


def resolve_apple_roll_path(
    output_dir: Path,
    normalized_img_stem: str,
    *,
    extension: str = "JPG",
) -> Path:
    """Return ``output_dir / IMG_<digits>.<ext>``."""
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / apple_roll_disk_filename(normalized_img_stem, extension=extension)
