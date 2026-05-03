"""Regenerate the EXIF-embedded thumbnail to match the host image.

The most embarrassing forensic catch in a naive EXIF transplant is the embedded
thumbnail. EXIF blocks contain a ~160x120 JPEG thumbnail; if you transplant EXIF
from a donor photo, the thumbnail still shows the *donor's* image, not yours.
A two-line ``exiftool -b -ThumbnailImage out.jpg | open -a Preview -f`` reveals
the original.

This module replaces the embedded thumbnail with a fresh downsize of the host
image, so the thumbnail and the full image agree.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Tuple

import piexif
from PIL import Image

THUMBNAIL_SIZE: Tuple[int, int] = (160, 120)


def _make_thumbnail_bytes(image: Image.Image, size: Tuple[int, int] = THUMBNAIL_SIZE) -> bytes:
    """Return JPEG bytes of a thumbnail of ``image`` sized to ``size`` (cover-fit)."""
    thumb = image.copy()
    thumb.thumbnail(size, Image.Resampling.LANCZOS)
    if thumb.mode != "RGB":
        thumb = thumb.convert("RGB")
    buf = io.BytesIO()
    thumb.save(buf, format="JPEG", quality=70)
    return buf.getvalue()


def regenerate_thumbnail(jpeg_path: Path, output_path: Path | None = None) -> Path:
    """Regenerate the embedded thumbnail of ``jpeg_path`` from its own pixels.

    Writes to ``output_path`` if given; otherwise overwrites ``jpeg_path`` in place.
    Returns the written path. No-ops cleanly if the JPEG has no EXIF block.
    """
    jpeg_path = Path(jpeg_path)
    out_path = Path(output_path) if output_path else jpeg_path

    with Image.open(jpeg_path) as im:
        im.load()
        thumb_bytes = _make_thumbnail_bytes(im)
        exif_blob = im.info.get("exif")
        is_jpeg = im.format == "JPEG"
        qtables = getattr(im, "quantization", None) if is_jpeg else None
        icc_blob = im.info.get("icc_profile")

    if not exif_blob:
        exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "Interop": {}, "1st": {}, "thumbnail": None}
    else:
        exif_dict = piexif.load(exif_blob)

    exif_dict["thumbnail"] = thumb_bytes
    new_exif = piexif.dump(exif_dict)

    with Image.open(jpeg_path) as im:
        im.load()
        save_kwargs = {"format": "JPEG", "exif": new_exif}
        if qtables:
            save_kwargs["qtables"] = {int(k): list(v) for k, v in qtables.items()}
            save_kwargs["subsampling"] = "4:2:0"
        else:
            save_kwargs["quality"] = 95
        if icc_blob:
            save_kwargs["icc_profile"] = icc_blob
        im.save(out_path, **save_kwargs)

    return out_path


def thumbnail_matches_host(jpeg_path: Path, tolerance: float = 0.20) -> bool:
    """Cheap consistency check: does the embedded thumbnail visually resemble the host?

    Compares mean-RGB of host (downsized) and embedded thumbnail. Returns True if
    the per-channel difference is below ``tolerance`` (0..1). Used as a self-test;
    not a forensic-grade comparison.
    """
    import numpy as np

    jpeg_path = Path(jpeg_path)
    with Image.open(jpeg_path) as im:
        exif_blob = im.info.get("exif")
        host_thumb = im.copy()
        host_thumb.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
        if host_thumb.mode != "RGB":
            host_thumb = host_thumb.convert("RGB")
        host_mean = np.array(host_thumb).reshape(-1, 3).mean(axis=0) / 255.0

    if not exif_blob:
        return False
    exif_dict = piexif.load(exif_blob)
    thumb_bytes = exif_dict.get("thumbnail")
    if not thumb_bytes:
        return False

    embedded = Image.open(io.BytesIO(thumb_bytes)).convert("RGB")
    emb_mean = np.array(embedded).reshape(-1, 3).mean(axis=0) / 255.0

    return bool((abs(host_mean - emb_mean) < tolerance).all())
