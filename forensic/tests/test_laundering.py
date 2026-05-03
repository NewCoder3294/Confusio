"""Unit tests for forensic.laundering."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from forensic.laundering import rephoto, spectrum, selfcheck, full_launder


def _make_test_image(path: Path, shape=(256, 256, 3), seed: int = 0):
    rng = np.random.default_rng(seed)
    arr = np.zeros(shape, dtype=np.uint8)
    arr[..., 0] = (rng.uniform(0, 255, shape[:2])).astype(np.uint8)
    arr[..., 1] = 100
    arr[..., 2] = (rng.uniform(50, 200, shape[:2])).astype(np.uint8)
    Image.fromarray(arr, "RGB").save(path, format="PNG")
    return path


def test_rephoto_runs_and_produces_jpeg(tmp_path):
    src = _make_test_image(tmp_path / "in.png")
    out = tmp_path / "out.jpg"
    stats = rephoto.rephoto(src, out)
    assert out.exists()
    assert stats["rmse_vs_input"] > 0
    with Image.open(out) as im:
        assert im.format == "JPEG"


def test_rephoto_changes_pixels(tmp_path):
    src = _make_test_image(tmp_path / "in.png", shape=(128, 128, 3))
    out = tmp_path / "out.jpg"
    rephoto.rephoto(src, out, params=rephoto.RephotoParams(psf_sigma=1.0, chroma_strength=2.0, sensor_noise=3.0))
    before = np.asarray(Image.open(src).convert("RGB"))
    after = np.asarray(Image.open(out).convert("RGB"))
    assert before.shape == after.shape
    assert not np.array_equal(before, after)


def test_rephoto_zero_params_is_near_identity(tmp_path):
    # Use a smooth gradient so JPEG can preserve it; pure-noise inputs lose
    # heavy detail through any JPEG round and would mask the test signal.
    yy, xx = np.mgrid[0:128, 0:128].astype(np.float32) / 127.0
    arr = np.stack([yy * 255, xx * 255, ((yy + xx) / 2) * 255], axis=-1).astype(np.uint8)
    src = tmp_path / "in.png"
    Image.fromarray(arr, "RGB").save(src, format="PNG")

    out = tmp_path / "out.jpg"
    rephoto.rephoto(
        src, out,
        params=rephoto.RephotoParams(
            psf_sigma=0, chroma_strength=0, sensor_noise=0, sharpen_amount=0, jpeg_q1=98, jpeg_q2=98
        ),
    )
    before = np.asarray(Image.open(src).convert("RGB"), dtype=np.float32)
    after = np.asarray(Image.open(out).convert("RGB"), dtype=np.float32)
    rmse = float(np.sqrt(((before - after) ** 2).mean()))
    assert rmse < 5.0, f"smooth-image identity RMSE was {rmse:.2f}"


def test_radial_spectrum_decreases_with_radius(tmp_path):
    # Use a smooth gradient (natural-image-like) so the 1/f decay holds.
    yy, xx = np.mgrid[0:128, 0:128].astype(np.float32) / 127.0
    arr = ((yy + xx) * 127).astype(np.float32)
    radii, pow_ = spectrum._radial_power_spectrum_fast(arr)
    assert pow_[1] > pow_[len(pow_) // 2]


def test_spectrum_launder_runs(tmp_path):
    src = _make_test_image(tmp_path / "in.png", shape=(256, 256, 3))
    out = tmp_path / "out.jpg"
    stats = spectrum.launder(src, out)
    assert out.exists()
    assert "mean_correction_db_per_channel" in stats
    assert len(stats["mean_correction_db_per_channel"]) == 3


def test_spectrum_launder_with_reference(tmp_path):
    src = _make_test_image(tmp_path / "src.png", seed=1)
    ref = _make_test_image(tmp_path / "ref.png", seed=2)
    out = tmp_path / "out.jpg"
    stats = spectrum.launder(src, out, reference_image=ref)
    assert out.exists()
    assert stats["rmse_vs_input"] >= 0


def test_selfcheck_heuristic_runs(tmp_path):
    src = _make_test_image(tmp_path / "in.png")
    r = selfcheck.detect(src, force_heuristic=True)
    assert r.backend == "spectral_heuristic"
    assert 0.0 <= r.p_ai <= 1.0
    assert 0.0 <= r.p_real <= 1.0


def test_selfcheck_compare_heuristic(tmp_path):
    a = _make_test_image(tmp_path / "a.png", seed=1)
    b = _make_test_image(tmp_path / "b.png", seed=2)
    cmp = selfcheck.compare(a, b, force_heuristic=True)
    assert "before" in cmp and "after" in cmp and "delta_p_ai" in cmp


def test_full_launder_pipeline(tmp_path):
    src = _make_test_image(tmp_path / "in.png", shape=(128, 128, 3))
    out = tmp_path / "out.jpg"
    result = full_launder(src, out, score_before_after=True, force_heuristic_score=True)
    assert out.exists()
    assert "rephoto" in result
    assert "spectrum" in result
    assert "surrogate_detector" in result
    sd = result["surrogate_detector"]
    assert sd["backend"] == "spectral_heuristic"
    assert "before" in sd and "after" in sd
