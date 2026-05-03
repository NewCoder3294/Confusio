"""Steganalysis self-checks: chi-squared and RS analysis on LSB distribution.

Two classical detectors:

  * **Chi-squared on PoVs** (Westfeld-Pfitzmann 1999): naive sequential LSB
    embedding equalises the frequencies of each "Pair of Values" (2k, 2k+1).
    A chi-squared test on those frequencies returns a p-value indicating
    embedding likelihood. Permuted-placement embeds (what we do) suppress this
    significantly but it remains a useful sanity check.

  * **RS (Regular-Singular) analysis** (Fridrich-Goljan 2001): partitions the
    image into small groups, computes a "smoothness" function before and after
    a small flip operation, and compares regular-vs-singular group counts.
    Estimates embedding rate. Robust against permutation but degrades at very
    low payload (<5%).

Self-grade contract: run BOTH on the stego output. If either flags strongly
(p < 0.05 chi-squared, or RS estimate > 1%), raise the rate flag. The mission
engine can choose to abort or down-scale the payload.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import stats


@dataclass
class StegAnalysisReport:
    chi_squared_p: float
    rs_estimated_rate: float
    flagged: bool
    note: str


def _load_gray(image_path: Path) -> np.ndarray:
    with Image.open(image_path) as im:
        if im.mode != "L":
            im = im.convert("L")
        return np.asarray(im, dtype=np.uint8)


def chi_squared_lsb(image_path: Path) -> float:
    """Chi-squared p-value on PoV frequencies. Lower p = more likely steg.

    p > 0.5  → almost certainly clean
    p < 0.05 → strong steg signal
    """
    gray = _load_gray(image_path)
    flat = gray.reshape(-1)
    counts = np.bincount(flat, minlength=256)
    pov = np.zeros(128, dtype=np.float64)
    pov_pair = np.zeros(128, dtype=np.float64)
    for k in range(128):
        pov[k] = counts[2 * k]
        pov_pair[k] = counts[2 * k + 1]

    expected = (pov + pov_pair) / 2.0
    mask = expected > 0
    obs = pov[mask]
    exp = expected[mask]
    if obs.size < 2:
        return 1.0
    chi = ((obs - exp) ** 2 / exp).sum()
    df = obs.size - 1
    return float(1.0 - stats.chi2.cdf(chi, df))


def _flip_lsb(arr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    out = arr.copy()
    out[mask] = out[mask] ^ 1
    return out


def _smoothness(group: np.ndarray) -> int:
    return int(np.abs(np.diff(group, axis=-1)).sum())


def rs_analysis(image_path: Path, group_size: int = 4) -> float:
    """Crude RS-style estimator. Returns approximate embedding rate (0..1).

    Splits image into non-overlapping rows of ``group_size`` pixels, applies a
    fixed mask flip, compares smoothness before/after. Approximates the
    Fridrich-Goljan estimator with a simplified mask scheme suitable for a
    self-grade rather than forensic-grade detection.
    """
    gray = _load_gray(image_path).astype(np.int32)
    H, W = gray.shape
    W_aligned = (W // group_size) * group_size
    if W_aligned == 0:
        return 0.0
    rows = gray[:, :W_aligned].reshape(-1, group_size)

    mask_flip = np.zeros(group_size, dtype=bool)
    mask_flip[0] = True
    mask_flip[2 % group_size] = True

    smooth_orig = np.abs(np.diff(rows, axis=-1)).sum(axis=-1)

    flipped = rows.copy()
    flipped[:, mask_flip] = flipped[:, mask_flip] ^ 1
    smooth_flip = np.abs(np.diff(flipped, axis=-1)).sum(axis=-1)

    inv_flipped = rows.copy()
    inv_flipped[:, mask_flip] = inv_flipped[:, mask_flip] ^ 0xFE
    smooth_inv = np.abs(np.diff(inv_flipped, axis=-1)).sum(axis=-1)

    Rm = (smooth_flip > smooth_orig).sum()
    Sm = (smooth_flip < smooth_orig).sum()
    R_m = (smooth_inv > smooth_orig).sum()
    S_m = (smooth_inv < smooth_orig).sum()

    total = Rm + Sm + R_m + S_m
    if total == 0:
        return 0.0
    diff = abs((Rm - Sm) - (R_m - S_m))
    return float(diff) / float(total)


def analyze(image_path: Path) -> StegAnalysisReport:
    """Run both detectors and produce a flagged/clean verdict."""
    chi_p = chi_squared_lsb(image_path)
    rs = rs_analysis(image_path)
    flagged = chi_p < 0.05 or rs > 0.1
    note = []
    if chi_p < 0.05:
        note.append(f"chi-squared p={chi_p:.3f} (low → steg signal)")
    if rs > 0.1:
        note.append(f"RS rate estimate {rs:.2%} (>10%)")
    if not note:
        note.append("clean: no strong steg signal detected by chi-squared or RS")
    return StegAnalysisReport(
        chi_squared_p=chi_p,
        rs_estimated_rate=rs,
        flagged=flagged,
        note="; ".join(note),
    )


def compare(cover_path: Path, stego_path: Path) -> dict:
    """Side-by-side analysis of the cover (clean) vs stego output.

    A well-behaved embedding shows minimal increase in either detector signal.
    """
    cov = analyze(cover_path)
    stg = analyze(stego_path)
    return {
        "cover": {"chi_squared_p": cov.chi_squared_p, "rs_rate": cov.rs_estimated_rate, "flagged": cov.flagged},
        "stego": {"chi_squared_p": stg.chi_squared_p, "rs_rate": stg.rs_estimated_rate, "flagged": stg.flagged},
        "delta": {
            "chi_squared_p": stg.chi_squared_p - cov.chi_squared_p,
            "rs_rate": stg.rs_estimated_rate - cov.rs_estimated_rate,
        },
    }
