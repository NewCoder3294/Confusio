"""Preserve Apple MakerNote during EXIF transplant.

Apple's MakerNote is a proprietary EXIF block (tag 0x927C in the Exif IFD) that
contains iPhone-specific telemetry: focus distance, lens model identifier,
HDR/SmartHDR flags, image stabilisation state, etc. Forensic analysts inspect
it because:

- A genuine iPhone JPEG always has one.
- The fields inside are internally consistent (e.g. focus distance plausible
  given focal length).
- It contains an ``ApplePhotosOriginatingSignature`` field on iOS 17+ that's
  cryptographically tied to the device.

A naive EXIF transplant that uses ``piexif.dump`` round-trip preserves
MakerNote bytes verbatim — this module exposes that as an explicit step and
adds a verification helper.

Note: we do NOT forge new MakerNote contents. We copy the donor's verbatim.
This means the MakerNote describes a real iPhone capture; the lens / focus
fields won't match the synthetic image's apparent composition. A *trained*
iPhone forensic analyst can spot the mismatch (e.g. MakerNote claims macro
mode but the synthetic image is a wide landscape). This module gets us past
"is there a MakerNote at all?" not "is the MakerNote semantically consistent?"
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import piexif


MAKERNOTE_TAG = piexif.ExifIFD.MakerNote  # 0x927C


def extract_makernote(jpeg_path: Path) -> Optional[bytes]:
    """Return the raw MakerNote bytes from ``jpeg_path``, or None if absent."""
    jpeg_path = Path(jpeg_path)
    try:
        exif_dict = piexif.load(str(jpeg_path))
    except Exception:
        return None
    return exif_dict.get("Exif", {}).get(MAKERNOTE_TAG)


def apply_makernote(jpeg_path: Path, makernote: bytes, output_path: Path | None = None) -> Path:
    """Inject ``makernote`` bytes into the Exif IFD of ``jpeg_path``.

    Writes to ``output_path`` if given; otherwise overwrites in place.
    Preserves all other EXIF entries.
    """
    jpeg_path = Path(jpeg_path)
    out = Path(output_path) if output_path else jpeg_path

    try:
        exif_dict = piexif.load(str(jpeg_path))
    except Exception:
        exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "Interop": {}, "1st": {}, "thumbnail": None}

    exif_dict.setdefault("Exif", {})[MAKERNOTE_TAG] = makernote
    new_exif = piexif.dump(exif_dict)

    if out != jpeg_path:
        # Read pixels and re-save with new EXIF.
        from PIL import Image

        with Image.open(jpeg_path) as im:
            im.load()
            im.save(out, format="JPEG", exif=new_exif, quality="keep")
    else:
        piexif.insert(new_exif, str(jpeg_path))

    return out


def transplant_from_donor(donor_jpeg: Path, target_jpeg: Path, output_path: Path | None = None) -> Path:
    """Copy donor's MakerNote into target. Returns written path."""
    mn = extract_makernote(donor_jpeg)
    if not mn:
        raise ValueError(f"donor {donor_jpeg} has no MakerNote to transplant")
    return apply_makernote(target_jpeg, mn, output_path)


def has_makernote(jpeg_path: Path) -> bool:
    return extract_makernote(jpeg_path) is not None
