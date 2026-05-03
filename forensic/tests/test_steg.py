"""Unit tests for forensic.steg."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from forensic.steg import embed as steg_embed
from forensic.steg import extract as steg_extract
from forensic.steg import analyze as steg_analyze


def _make_cover(path: Path, shape=(256, 256, 3), seed: int = 7):
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 256, shape, dtype=np.uint8)
    Image.fromarray(arr, "RGB").save(path, format="PNG")
    return path


def test_embed_extract_roundtrip(tmp_path):
    cover = _make_cover(tmp_path / "cover.png")
    payload = b"next contact: dead-drop alpha-7 @ 21:00 UTC"
    key = b"OPS_KEY_2026"
    out, _meta = steg_embed.embed(cover, payload, key, tmp_path / "stego.png")

    recovered = steg_extract.extract(out, key)
    assert recovered == payload


def test_extract_with_wrong_key_fails(tmp_path):
    cover = _make_cover(tmp_path / "cover.png")
    out, _ = steg_embed.embed(cover, b"hello", b"correct", tmp_path / "stego.png")
    with pytest.raises(steg_extract.StegExtractError):
        steg_extract.extract(out, b"wrong")


def test_payload_too_large_rejected(tmp_path):
    cover = _make_cover(tmp_path / "cover.png", shape=(64, 64, 3))
    huge = b"x" * 10_000  # 80,000 bits, exceeds 5% of 64*64*3 = 614 bits cap
    with pytest.raises(ValueError, match="payload too large"):
        steg_embed.embed(cover, huge, b"key", tmp_path / "stego.png")


def test_embed_metadata_reports_capacity(tmp_path):
    cover = _make_cover(tmp_path / "cover.png", shape=(256, 256, 3))
    out, meta = steg_embed.embed(cover, b"abc", b"key", tmp_path / "stego.png")
    assert meta["capacity_bits"] == 256 * 256 * 3
    assert meta["used_bits"] > 0
    assert meta["fraction_used"] < 0.05


def test_steg_output_is_png_even_if_jpg_requested(tmp_path):
    cover = _make_cover(tmp_path / "cover.png")
    out, _ = steg_embed.embed(cover, b"x", b"key", tmp_path / "stego.jpg")
    assert out.suffix == ".png"


def test_chi_squared_clean_image(tmp_path):
    cover = _make_cover(tmp_path / "cover.png", shape=(256, 256, 3))
    p = steg_analyze.chi_squared_lsb(cover)
    assert 0.0 <= p <= 1.0


def test_compare_cover_vs_stego(tmp_path):
    cover = _make_cover(tmp_path / "cover.png", shape=(512, 512, 3))
    stego, _ = steg_embed.embed(cover, b"covert msg", b"key", tmp_path / "stego.png")
    cmp = steg_analyze.compare(cover, stego)
    assert "cover" in cmp and "stego" in cmp and "delta" in cmp
    # Permuted-placement low-payload embed shouldn't massively shift chi-squared.
    assert cmp["stego"]["rs_rate"] < 0.2


def test_embed_jpeg_stub_raises(tmp_path):
    cover = _make_cover(tmp_path / "cover.png")
    with pytest.raises(NotImplementedError):
        steg_embed.embed_jpeg(cover, b"x", b"k", tmp_path / "out.jpg")
