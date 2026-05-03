"""Unit tests for forensic.prnu."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from forensic.prnu import extract as prnu_extract
from forensic.prnu import inject as prnu_inject


def _synthesize_corpus(tmp_path: Path, n: int = 8, shape=(128, 128), seed: int = 42, sensor_pattern=None):
    """Build a synthetic 'camera' corpus: scenes + a fixed sensor noise pattern."""
    rng = np.random.default_rng(seed)
    if sensor_pattern is None:
        sensor_pattern = rng.standard_normal(shape).astype(np.float32) * 2.0
    paths = []
    for i in range(n):
        scene = (rng.uniform(50, 200, shape) + rng.standard_normal(shape) * 5).astype(np.float32)
        captured = scene * (1.0 + 0.04 * sensor_pattern)
        captured = np.clip(captured, 0, 255).astype(np.uint8)
        p = tmp_path / f"corpus_{i}.png"
        Image.fromarray(captured, mode="L").save(p)
        paths.append(p)
    return paths, sensor_pattern


def test_wavelet_denoise_reduces_noise():
    rng = np.random.default_rng(0)
    clean = np.full((64, 64), 128.0, dtype=np.float32)
    noisy = clean + rng.standard_normal((64, 64)).astype(np.float32) * 5.0
    denoised = prnu_extract.wavelet_denoise(noisy, sigma=5.0)
    denoised = denoised[: clean.shape[0], : clean.shape[1]]
    assert np.std(denoised - clean) < np.std(noisy - clean)


def test_extract_prnu_recovers_pattern_correlation(tmp_path):
    paths, true_pattern = _synthesize_corpus(tmp_path, n=12, shape=(128, 128))
    estimated = prnu_extract.extract_prnu(paths, target_shape=(128, 128))

    # Estimated PRNU should correlate with the injected sensor pattern.
    a = (estimated - estimated.mean()).flatten()
    b = (true_pattern - true_pattern.mean()).flatten()
    rho = float((a * b).sum() / (np.sqrt((a * a).sum() * (b * b).sum()) + 1e-12))
    assert rho > 0.05, f"PRNU recovery correlation too low: {rho:.4f}"


def test_save_load_prnu_roundtrip(tmp_path):
    arr = np.random.default_rng(0).standard_normal((32, 32)).astype(np.float32)
    p = tmp_path / "prnu.npy"
    prnu_extract.save_prnu(arr, p)
    loaded = prnu_extract.load_prnu(p)
    assert np.allclose(loaded, arr)


def test_inject_prnu_increases_correlation(tmp_path):
    rng = np.random.default_rng(0)
    H = W = 256
    prnu = rng.standard_normal((H, W)).astype(np.float32)

    target_path = tmp_path / "synthetic.png"
    synth = (rng.uniform(50, 200, (H, W, 3))).astype(np.uint8)
    Image.fromarray(synth, "RGB").save(target_path)

    rho_before = prnu_inject.correlate(target_path, prnu)

    out_path = tmp_path / "injected.jpg"
    prnu_inject.inject_prnu(target_path, prnu, out_path, alpha=0.05)

    rho_after = prnu_inject.correlate(out_path, prnu)
    assert rho_after > rho_before, f"injection didn't raise correlation: {rho_before:.4f} -> {rho_after:.4f}"
    assert rho_after > 0.005, f"post-injection correlation suspiciously low: {rho_after:.4f}"


def test_inject_prnu_visually_minimal(tmp_path):
    rng = np.random.default_rng(0)
    H = W = 128
    prnu = rng.standard_normal((H, W)).astype(np.float32)

    target_path = tmp_path / "synthetic.png"
    synth = np.full((H, W, 3), 128, dtype=np.uint8)
    synth += rng.integers(-5, 5, synth.shape, dtype=np.int8).astype(np.uint8)
    Image.fromarray(synth, "RGB").save(target_path)

    out_path = tmp_path / "injected.jpg"
    prnu_inject.inject_prnu(target_path, prnu, out_path, alpha=0.025)

    before = np.asarray(Image.open(target_path).convert("RGB"), dtype=np.float32)
    after = np.asarray(Image.open(out_path).convert("RGB"), dtype=np.float32)
    rmse = float(np.sqrt(((before - after) ** 2).mean()))
    # at alpha=0.025, expected RMSE ~ 1-3 grey levels for noise-textured input
    assert rmse < 12.0, f"injection too visible: rmse={rmse:.2f}"
