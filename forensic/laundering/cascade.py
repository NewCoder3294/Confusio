"""Cascade laundering: two-pass + color jitter to defeat detectors that
survive a single pass.

Empirical discovery (2026-05-03 sweep on `image-9fab1a24`):

  * A single laundering pass plateaus at ~37% on `umm-maybe/AI-image-detector`
    even when `Organika/sdxl-detector` is dropped to 4-15% AI.
  * The umm-maybe model appears to key on color/saturation statistics that the
    rephoto+spectrum chain doesn't displace — natural photos have specific
    color histograms that AI generators typically over-saturate.
  * A second laundering pass with a *different seed* + a slight desaturation /
    contrast reduction breaks the umm-maybe lock without re-exciting Organika.

Default params here are the best discovered across that sweep:

  Pass 1: light rephoto (psf 0.5), high spectrum blend (0.95)
  Pass 2: very light rephoto (psf 0.4), moderate spectrum blend (0.6),
          different seed
  Jitter: saturation × 0.92, contrast × 0.95

Result on the test fixture: worst-detector p_ai dropped from 0.39 → 0.25
(~75% undetectable on both surrogates simultaneously, both labels "human").

PSNR cost: ~22 dB (vs 28-29 dB single-pass) — visible softening but content
intact. If image fidelity is more important than the last 10pp of evasion,
disable jitter or reduce its strength.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

from PIL import Image, ImageEnhance

from . import rephoto, spectrum, selfcheck


@dataclass
class CascadeParams:
    pass1: rephoto.RephotoParams = field(default_factory=lambda: rephoto.RephotoParams(
        psf_sigma=0.5, chroma_strength=0.9, sensor_noise=1.6, sharpen_amount=0.5,
        jpeg_q1=90, jpeg_q2=92, seed=42,
    ))
    blend1: float = 0.95
    pass2: rephoto.RephotoParams = field(default_factory=lambda: rephoto.RephotoParams(
        psf_sigma=0.4, chroma_strength=0.5, sensor_noise=1.0, sharpen_amount=0.3,
        jpeg_q1=92, jpeg_q2=94, seed=13,
    ))
    blend2: float = 0.6
    saturation: float = 0.92
    contrast: float = 0.95


def cascade(
    target: Path,
    output: Path,
    params: Optional[CascadeParams] = None,
    score_before_after: bool = True,
) -> dict:
    """Run two-pass laundering + color jitter. Returns full per-stage stats.

    Output is JPEG. Both intermediate stages are deleted; only the final JPEG
    persists at ``output``.
    """
    target = Path(target)
    output = Path(output)
    params = params or CascadeParams()

    score_before_all = selfcheck.detect_all(target) if score_before_after else []

    work1 = output.with_suffix(".pass1.jpg")
    work_rp = output.with_suffix(".rp.jpg")

    rephoto.rephoto(target, work_rp, params=params.pass1)
    spectrum.launder(work_rp, work1, params=spectrum.SpectrumParams(blend=params.blend1))
    work_rp.unlink(missing_ok=True)

    work2 = output.with_suffix(".pass2.jpg")
    rephoto.rephoto(work1, work_rp, params=params.pass2)
    spectrum.launder(work_rp, work2, params=spectrum.SpectrumParams(blend=params.blend2))
    work_rp.unlink(missing_ok=True)
    work1.unlink(missing_ok=True)

    img = Image.open(work2).convert("RGB")
    img = ImageEnhance.Color(img).enhance(params.saturation)
    img = ImageEnhance.Contrast(img).enhance(params.contrast)
    img.save(output, format="JPEG", quality=92, subsampling="4:2:0")
    work2.unlink(missing_ok=True)

    result = {"output": str(output), "params": {
        "pass1": asdict(params.pass1), "blend1": params.blend1,
        "pass2": asdict(params.pass2), "blend2": params.blend2,
        "saturation": params.saturation, "contrast": params.contrast,
    }}

    if score_before_after:
        score_after_all = selfcheck.detect_all(output)
        per_model = []
        worst_after = 0.0
        for s_after in score_after_all:
            s_before = next((b for b in score_before_all if b.model == s_after.model), None)
            per_model.append({
                "model": s_after.model,
                "p_ai_before": s_before.p_ai if s_before else None,
                "p_ai_after": s_after.p_ai,
                "label_after": s_after.raw_label,
            })
            worst_after = max(worst_after, s_after.p_ai)
        result["surrogate_detectors"] = per_model
        result["worst_p_ai"] = worst_after
        result["undetectable_pct"] = (1.0 - worst_after) * 100.0

    return result
