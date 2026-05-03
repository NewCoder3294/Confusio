"""Match JPEG quantization tables to a donor device.

Every camera vendor uses a recognizable set of quantization tables in the JPEG
encoder. iPhone tables differ from Pixel tables differ from libjpeg-turbo
defaults. Forensic tools (e.g. ``exiftool -DQT``, jpeg-quality estimators) read
these tables and infer the encoder.

After EXIF transplant the metadata claims "iPhone X" but the quant tables are
whatever PIL emitted. Re-encoding the host image using the donor's exact quant
tables closes that mismatch.

PIL/Pillow exposes ``qtables=`` in JPEG save; we extract donor tables via PIL's
internal ``quantization`` attribute (populated on ``Image.open`` of a JPEG).
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Dict, List

from PIL import Image


def extract_qtables(jpeg_path: Path) -> Dict[int, List[int]]:
    """Return the donor's JPEG quantization tables keyed by table index (0/1).

    Each value is a 64-entry list of zig-zag-ordered quantization coefficients.
    Pillow exposes them on ``Image.quantization`` for JPEG inputs.
    """
    jpeg_path = Path(jpeg_path)
    with Image.open(jpeg_path) as im:
        if im.format != "JPEG":
            raise ValueError(f"{jpeg_path} is not a JPEG (format={im.format})")
        im.load()
        qt = getattr(im, "quantization", None)
        if not qt:
            raise ValueError(f"{jpeg_path} has no quantization tables")
        # Pillow returns dict[int, list[int]] (already 64 entries each).
        return {int(k): list(v) for k, v in qt.items()}


def reencode_with_qtables(
    image_path: Path,
    qtables: Dict[int, List[int]],
    output_path: Path,
    preserve_exif: bool = True,
) -> Path:
    """Re-encode ``image_path`` to JPEG using ``qtables`` as quantization tables.

    Preserves the EXIF block from the input by default. Writes to ``output_path``.
    ``qtables`` shape matches :func:`extract_qtables` output.
    """
    image_path = Path(image_path)
    output_path = Path(output_path)

    with Image.open(image_path) as im:
        im.load()
        if im.mode != "RGB":
            im = im.convert("RGB")
        exif_blob = im.info.get("exif") if preserve_exif else None

    save_kwargs = {"format": "JPEG", "qtables": qtables, "subsampling": "4:2:0"}
    if exif_blob:
        save_kwargs["exif"] = exif_blob

    with Image.open(image_path) as im:
        im.load()
        if im.mode != "RGB":
            im = im.convert("RGB")
        im.save(output_path, **save_kwargs)

    return output_path


def match_to_donor(
    image_path: Path,
    donor_jpeg: Path,
    output_path: Path,
    preserve_exif: bool = True,
) -> Path:
    """Convenience: extract donor tables and re-encode ``image_path`` with them."""
    qtables = extract_qtables(donor_jpeg)
    return reencode_with_qtables(image_path, qtables, output_path, preserve_exif=preserve_exif)


def qtables_match(a: Path, b: Path, tolerance: int = 0) -> bool:
    """True if quant tables of two JPEGs match within per-coefficient ``tolerance``."""
    qa = extract_qtables(a)
    qb = extract_qtables(b)
    if set(qa.keys()) != set(qb.keys()):
        return False
    for k in qa:
        if len(qa[k]) != len(qb[k]):
            return False
        for x, y in zip(qa[k], qb[k]):
            if abs(x - y) > tolerance:
                return False
    return True
