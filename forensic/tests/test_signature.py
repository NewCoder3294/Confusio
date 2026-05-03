"""Unit tests for forensic.signature."""
from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image
import piexif

from forensic.signature import thumbnail, quantization, makernote


def _make_jpeg(path: Path, size=(640, 480), color=(120, 30, 200), with_exif=True, donor_thumb_color=(0, 255, 0)):
    img = Image.new("RGB", size, color=color)
    if with_exif:
        # Build an EXIF dict with a recognizable thumbnail (donor color).
        donor_thumb = Image.new("RGB", (160, 120), color=donor_thumb_color)
        thumb_buf = io.BytesIO()
        donor_thumb.save(thumb_buf, format="JPEG", quality=70)
        exif_dict = {
            "0th": {piexif.ImageIFD.Make: b"Apple", piexif.ImageIFD.Model: b"iPhone X"},
            "Exif": {piexif.ExifIFD.MakerNote: b"\x00\x01APPLE_FAKE_MAKERNOTE_BLOB"},
            "GPS": {},
            "Interop": {},
            "1st": {},
            "thumbnail": thumb_buf.getvalue(),
        }
        exif_bytes = piexif.dump(exif_dict)
        img.save(path, format="JPEG", exif=exif_bytes, quality=92)
    else:
        img.save(path, format="JPEG", quality=92)


def test_thumbnail_regenerate_overwrites_donor_thumb(tmp_path):
    src = tmp_path / "in.jpg"
    out = tmp_path / "out.jpg"
    _make_jpeg(src, donor_thumb_color=(0, 255, 0))  # green donor thumb
    thumbnail.regenerate_thumbnail(src, out)

    exif_dict = piexif.load(str(out))
    new_thumb = Image.open(io.BytesIO(exif_dict["thumbnail"])).convert("RGB")
    # The new thumb should reflect the host pixels (mostly purple), not donor green.
    px = list(new_thumb.getdata())[len(list(new_thumb.getdata())) // 2]
    assert px[1] < 100, f"thumb still mostly green {px}"


def test_thumbnail_consistency_check(tmp_path):
    src = tmp_path / "in.jpg"
    out = tmp_path / "out.jpg"
    _make_jpeg(src, donor_thumb_color=(0, 255, 0))
    thumbnail.regenerate_thumbnail(src, out)
    assert thumbnail.thumbnail_matches_host(out)


def test_thumbnail_no_exif_creates_one(tmp_path):
    src = tmp_path / "in.jpg"
    out = tmp_path / "out.jpg"
    _make_jpeg(src, with_exif=False)
    thumbnail.regenerate_thumbnail(src, out)
    exif_dict = piexif.load(str(out))
    assert exif_dict.get("thumbnail") is not None


def test_quantization_match(tmp_path):
    donor = tmp_path / "donor.jpg"
    target = tmp_path / "target.jpg"
    out = tmp_path / "out.jpg"
    _make_jpeg(donor, color=(255, 100, 50))
    _make_jpeg(target, color=(50, 100, 255))

    donor_qt = quantization.extract_qtables(donor)
    quantization.match_to_donor(target, donor, out)
    out_qt = quantization.extract_qtables(out)
    assert set(donor_qt.keys()) == set(out_qt.keys())
    for k in donor_qt:
        assert donor_qt[k] == out_qt[k]


def test_quantization_qtables_match_helper(tmp_path):
    a = tmp_path / "a.jpg"
    b = tmp_path / "b.jpg"
    _make_jpeg(a)
    _make_jpeg(b)
    # Both produced with default Pillow quality=92, so qtables should match.
    assert quantization.qtables_match(a, b)


def test_makernote_extract_and_apply(tmp_path):
    donor = tmp_path / "donor.jpg"
    target = tmp_path / "target.jpg"
    out = tmp_path / "out.jpg"
    _make_jpeg(donor)
    _make_jpeg(target, with_exif=False)

    mn = makernote.extract_makernote(donor)
    assert mn is not None
    assert b"APPLE_FAKE_MAKERNOTE_BLOB" in mn

    makernote.apply_makernote(target, mn, out)
    extracted = makernote.extract_makernote(out)
    assert extracted == mn
    assert makernote.has_makernote(out)


def test_full_signature_match_pipeline(tmp_path):
    from forensic.signature import full_signature_match

    donor = tmp_path / "donor.jpg"
    target = tmp_path / "target.jpg"
    out = tmp_path / "out.jpg"
    _make_jpeg(donor, color=(255, 100, 50), donor_thumb_color=(0, 255, 0))
    _make_jpeg(target, color=(50, 100, 255), with_exif=False)

    status = full_signature_match(target, donor, out)
    assert status["quantization_matched"] is True
    assert status["makernote_transplanted"] is True
    assert status["thumbnail_regenerated"] is True
    assert status["thumbnail_consistent"] is True

    assert quantization.qtables_match(out, donor)
    assert makernote.has_makernote(out)
