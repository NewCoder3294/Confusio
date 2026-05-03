"""CNN-detector laundering: re-photograph simulation + spectrum rebalancing.

Targets the pixel-level CNN classifier family (Hive AI, Optic, AI or Not,
Reality Defender, SynthID v2). Run AFTER signature-match + PRNU injection;
the laundering chain reshapes pixel-level statistics so detector confidence
falls without breaking the watermark/forensic work.

Pipeline order in :func:`full_launder`:

  1. rephoto.rephoto()  — analog-hole simulation (PSF, chromatic aberration,
                          sensor noise, ISP sharpening, double JPEG)
  2. spectrum.launder() — radial-power-spectrum rebalance toward natural
                          1/f baseline
  3. selfcheck.detect() — surrogate AI-detector probability before/after

The first two transformations always run. The third is optional but is the
demo-relevant component: it produces concrete numbers ("detector says 99% AI
before, 35% AI after") that judges can verify live.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Optional

from . import rephoto, spectrum, selfcheck, cascade


def full_launder(
    target: Path,
    output: Path,
    rephoto_params: Optional[rephoto.RephotoParams] = None,
    spectrum_params: Optional[spectrum.SpectrumParams] = None,
    spectrum_reference: Optional[Path] = None,
    score_before_after: bool = True,
    force_heuristic_score: bool = False,
) -> dict:
    """Run rephoto + spectrum laundering, optionally with surrogate-detector scoring.

    Returns a dict with per-stage stats and (if scored) before/after detector
    probabilities.
    """
    target = Path(target)
    output = Path(output)
    work = output.with_suffix(".rephoto.jpg")

    score_before = None
    if score_before_after:
        score_before = selfcheck.detect(target, force_heuristic=force_heuristic_score)

    rephoto_stats = rephoto.rephoto(target, work, params=rephoto_params)
    spectrum_stats = spectrum.launder(work, output, reference_image=spectrum_reference, params=spectrum_params)
    work.unlink(missing_ok=True)

    result = {
        "rephoto": rephoto_stats,
        "spectrum": spectrum_stats,
    }
    if score_before_after:
        score_after = selfcheck.detect(output, force_heuristic=force_heuristic_score)
        result["surrogate_detector"] = {
            "model": score_before.model,
            "backend": score_before.backend,
            "before": {"p_ai": score_before.p_ai, "p_real": score_before.p_real, "raw_label": score_before.raw_label},
            "after": {"p_ai": score_after.p_ai, "p_real": score_after.p_real, "raw_label": score_after.raw_label},
            "delta_p_ai": score_after.p_ai - score_before.p_ai,
            "note": score_before.note or score_after.note or "",
        }
    return result


__all__ = ["rephoto", "spectrum", "selfcheck", "cascade", "full_launder"]
