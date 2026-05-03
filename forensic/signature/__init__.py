"""Tier 1 device-signature matching: thumbnail, JPEG quant tables, ICC, MakerNote.

Closes the byte-level signature mismatches a 5-minute ExifTool audit catches.
Run after EXIF transplant; before provenance check.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Any

from . import thumbnail, quantization, icc_profile, makernote


def full_signature_match(
    target_jpeg: Path,
    donor_jpeg: Path,
    output_path: Path,
) -> Dict[str, Any]:
    """Run all four signature-match steps in order.

    Pipeline:
      1. Re-encode target with donor's JPEG quant tables (also preserves EXIF).
      2. Apply donor's ICC profile (with color conversion).
      3. Inject donor's Apple MakerNote.
      4. Regenerate the embedded thumbnail from target's own pixels.

    Returns a dict of per-step status flags.
    """
    target_jpeg = Path(target_jpeg)
    donor_jpeg = Path(donor_jpeg)
    output_path = Path(output_path)
    work = output_path.with_suffix(output_path.suffix + ".tmp")

    status: Dict[str, Any] = {}

    quantization.match_to_donor(target_jpeg, donor_jpeg, work, preserve_exif=True)
    status["quantization_matched"] = True

    try:
        icc_profile.match_to_donor(work, donor_jpeg, work)
        status["icc_matched"] = True
    except ValueError as e:
        status["icc_matched"] = False
        status["icc_error"] = str(e)

    try:
        makernote.transplant_from_donor(donor_jpeg, work, work)
        status["makernote_transplanted"] = True
    except ValueError as e:
        status["makernote_transplanted"] = False
        status["makernote_error"] = str(e)

    thumbnail.regenerate_thumbnail(work, output_path)
    status["thumbnail_regenerated"] = True
    status["thumbnail_consistent"] = thumbnail.thumbnail_matches_host(output_path)

    work.unlink(missing_ok=True)
    return status


__all__ = ["thumbnail", "quantization", "icc_profile", "makernote", "full_signature_match"]
