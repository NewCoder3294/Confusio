"""Demo helpers: side-by-side comparison + parameter sweep.

For live demos against judges:

  - :func:`side_by_side` produces a labeled before/after PNG with detector
    scores rendered onto each panel — single-image deliverable that tells the
    whole story.

  - :func:`sweep` runs a small grid of laundering parameter sets and reports
    which combination yields the lowest p_ai across one or more surrogate
    detectors. Use it 5 minutes before stage time to lock in the params for
    your specific demo image.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from . import rephoto, spectrum, selfcheck


def _load_font(size: int = 20):
    for name in ("Arial.ttf", "Helvetica.ttc", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def side_by_side(
    before_path: Path,
    after_path: Path,
    output_path: Path,
    score_before: Optional[selfcheck.DetectionResult] = None,
    score_after: Optional[selfcheck.DetectionResult] = None,
    panel_max_dim: int = 700,
) -> Path:
    """Compose a labeled before/after comparison PNG with detector scores."""
    before_path = Path(before_path)
    after_path = Path(after_path)
    output_path = Path(output_path)

    if score_before is None:
        score_before = selfcheck.detect(before_path)
    if score_after is None:
        score_after = selfcheck.detect(after_path)

    def _fit(im: Image.Image) -> Image.Image:
        im = im.copy()
        im.thumbnail((panel_max_dim, panel_max_dim), Image.Resampling.LANCZOS)
        return im

    a = _fit(Image.open(before_path).convert("RGB"))
    b = _fit(Image.open(after_path).convert("RGB"))
    panel_w = max(a.width, b.width)
    panel_h = max(a.height, b.height)

    label_h = 90
    canvas = Image.new("RGB", (panel_w * 2 + 30, panel_h + label_h + 20), color=(20, 20, 20))
    canvas.paste(a, (10 + (panel_w - a.width) // 2, label_h))
    canvas.paste(b, (20 + panel_w + (panel_w - b.width) // 2, label_h))

    draw = ImageDraw.Draw(canvas)
    title_font = _load_font(28)
    body_font = _load_font(18)

    def _render_panel_label(x_offset: int, title: str, score: selfcheck.DetectionResult):
        draw.text((x_offset + 12, 12), title, fill=(255, 255, 255), font=title_font)
        line = f"{score.model}: p_ai = {score.p_ai * 100:.1f}%  ({score.raw_label})"
        draw.text((x_offset + 12, 50), line, fill=(180, 220, 255), font=body_font)

    _render_panel_label(0, "BEFORE", score_before)
    _render_panel_label(panel_w + 20, "AFTER", score_after)

    # Bottom-center: delta summary.
    delta = score_after.p_ai - score_before.p_ai
    summary = f"Δ p_ai = {delta * 100:+.1f}%  •  surrogate: {score_before.backend}"
    bbox = draw.textbbox((0, 0), summary, font=body_font)
    text_w = bbox[2] - bbox[0]
    draw.text(((canvas.width - text_w) // 2, panel_h + label_h + 2), summary,
              fill=(200, 200, 200), font=body_font)

    canvas.save(output_path, format="PNG", optimize=True)
    return output_path


def _build_grid():
    """Cross product of rephoto strength × spectrum blend × seed.

    Empirical observation on the sdxl-detector vs umm-maybe pair: heavy rephoto
    excites umm-maybe (recognises the noise/blur as "fake"), heavy spectrum
    push without rephoto helps Organika. The sweet spot for both is *light
    rephoto + high blend*. Grid below scans both axes plus seed variation
    (sensor noise is stochastic; different seeds hit different decision
    boundaries on each detector).
    """
    grid = []
    rephoto_levels = [
        # (psf, chroma, noise, sharpen, jpeg_q1, jpeg_q2)
        (0.4, 0.6, 1.0, 0.3, 92, 94),    # very light
        (0.6, 1.0, 1.5, 0.5, 90, 92),    # light
        (0.9, 1.5, 2.2, 0.7, 87, 90),    # medium
        (1.2, 2.0, 2.8, 0.9, 85, 88),    # heavy
    ]
    blends = [0.4, 0.6, 0.8, 0.95]
    seeds = [42, 99]

    for psf, ch, ns, sh, q1, q2 in rephoto_levels:
        for blend in blends:
            for seed in seeds:
                grid.append({
                    "psf_sigma": psf, "chroma_strength": ch, "sensor_noise": ns,
                    "sharpen_amount": sh, "jpeg_q1": q1, "jpeg_q2": q2,
                    "blend": blend, "seed": seed,
                })
    return grid


_DEFAULT_GRID = _build_grid()


def sweep(
    target: Path,
    output_dir: Path,
    param_grid: Optional[List[dict]] = None,
) -> List[dict]:
    """Run laundering across a small param grid; return scored results sorted by p_ai ascending."""
    target = Path(target)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if param_grid is None:
        param_grid = _DEFAULT_GRID

    score_before = selfcheck.detect(target)
    results = []
    for i, p in enumerate(param_grid):
        out = output_dir / f"sweep_{i:02d}.jpg"
        rp = rephoto.RephotoParams(
            psf_sigma=p["psf_sigma"],
            chroma_strength=p["chroma_strength"],
            sensor_noise=p["sensor_noise"],
            sharpen_amount=p["sharpen_amount"],
            jpeg_q1=p["jpeg_q1"],
            jpeg_q2=p["jpeg_q2"],
            seed=p.get("seed", 42),
        )
        sp = spectrum.SpectrumParams(blend=p["blend"])

        work = out.with_suffix(".rp.jpg")
        rephoto.rephoto(target, work, params=rp)
        spectrum.launder(work, out, params=sp)
        work.unlink(missing_ok=True)

        score = selfcheck.detect(out)
        results.append({
            "index": i,
            "params": p,
            "output": str(out),
            "p_ai_before": score_before.p_ai,
            "p_ai_after": score.p_ai,
            "delta_p_ai": score.p_ai - score_before.p_ai,
            "label_after": score.raw_label,
            "model": score.model,
        })

    results.sort(key=lambda r: r["p_ai_after"])
    return results


def multi_sweep(
    target: Path,
    output_dir: Path,
    param_grid: Optional[List[dict]] = None,
) -> List[dict]:
    """Score every laundering candidate against EVERY surrogate detector.

    Selection criterion is **minimax**: pick the param set whose worst-detector
    p_ai is lowest. A param set that wins one detector but excites another is
    correctly penalised.

    Returns list of result dicts sorted by `worst_p_ai` ascending. Each entry
    contains per-model scores and the worst.
    """
    target = Path(target)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if param_grid is None:
        param_grid = _DEFAULT_GRID

    before_all = selfcheck.detect_all(target)
    if not before_all:
        # No torch surrogates available — fall back to single-model sweep.
        return sweep(target, output_dir, param_grid)

    results = []
    for i, p in enumerate(param_grid):
        out = output_dir / f"multisweep_{i:02d}.jpg"
        rp = rephoto.RephotoParams(
            psf_sigma=p["psf_sigma"],
            chroma_strength=p["chroma_strength"],
            sensor_noise=p["sensor_noise"],
            sharpen_amount=p["sharpen_amount"],
            jpeg_q1=p["jpeg_q1"],
            jpeg_q2=p["jpeg_q2"],
            seed=p.get("seed", 42),
        )
        sp = spectrum.SpectrumParams(blend=p["blend"])

        work = out.with_suffix(".rp.jpg")
        rephoto.rephoto(target, work, params=rp)
        spectrum.launder(work, out, params=sp)
        work.unlink(missing_ok=True)

        after_all = selfcheck.detect_all(out)

        per_model = []
        worst_after = 0.0
        for s_after in after_all:
            s_before = next((b for b in before_all if b.model == s_after.model), None)
            before_p = s_before.p_ai if s_before else None
            per_model.append({
                "model": s_after.model,
                "p_ai_before": before_p,
                "p_ai_after": s_after.p_ai,
                "label_after": s_after.raw_label,
                "delta_p_ai": (s_after.p_ai - before_p) if before_p is not None else None,
            })
            worst_after = max(worst_after, s_after.p_ai)

        results.append({
            "index": i,
            "params": p,
            "output": str(out),
            "per_model": per_model,
            "worst_p_ai": worst_after,
            "mean_p_ai": sum(m["p_ai_after"] for m in per_model) / max(len(per_model), 1),
        })

    results.sort(key=lambda r: (r["worst_p_ai"], r["mean_p_ai"]))
    return results
