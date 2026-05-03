"""Anti-detection chain for the mission engine.

Single entry point that runs the full evasion stack on one image:

    cascade laundering   →  PRNU injection  →  signature match  →  self-check

Each step is optional based on what the caller supplies. Only cascade
laundering and the self-check are enabled by default; PRNU and signature
match light up when their reference inputs are provided.

Order rationale
---------------

    1. Cascade laundering FIRST. It re-encodes JPEG twice and rebuilds
       pixel statistics. Anything written before it (donor headers, PRNU)
       gets nuked, so we run it on the raw stripped artifact.

    2. PRNU injection SECOND. Adds device-class sensor noise on top of
       laundered pixels. PRNU is high-frequency and laundering would
       partially smear it; injecting after laundering preserves the
       per-radial correlation that PRNU detectors look for.

    3. Signature match LAST. Transplants the donor JPEG's quantization
       tables, ICC profile, MakerNote, and thumbnail onto our pixel data.
       Because this is a JPEG-header rewrite that doesn't reshape pixels
       beyond a single re-quantization, it survives as the final layer.

    4. Self-check runs against the output. If the worst surrogate
       detector still scores above ``max_p_ai``, the chain aborts unless
       ``strict=False``.

This module owns no IO contracts of its own; it just orchestrates the
existing forensic submodules. Returns a single dict suitable for embedding
in a mission StageRecord detail.
"""
from __future__ import annotations

import logging
import shutil
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Optional

from . import laundering
from .laundering import cascade as cascade_mod
from .laundering import selfcheck

log = logging.getLogger(__name__)


class AntiDetectionAbort(RuntimeError):
    """Raised when self-check refuses the output."""

    def __init__(self, message: str, *, report: dict[str, Any]) -> None:
        super().__init__(message)
        self.report = report


@dataclass
class AntiDetectionOptions:
    cascade: bool = True
    """Run two-pass rephoto + spectrum + color-jitter."""

    prnu_pattern: Optional[Path] = None
    """Path to a .npy PRNU pattern. If None, PRNU step is skipped."""

    prnu_alpha: float = 0.025
    """PRNU injection strength."""

    donor_jpeg: Optional[Path] = None
    """Real-camera JPEG used for signature match. If None, signature step is skipped."""

    self_check: bool = True
    """Run multi-detector surrogate scoring on the final output."""

    max_p_ai: float = 0.40
    """If self-check's worst-detector p_ai exceeds this, abort (when strict)."""

    strict: bool = True
    """Raise AntiDetectionAbort when max_p_ai is exceeded. False = log and pass."""

    cascade_params: Optional[cascade_mod.CascadeParams] = None
    """Override the default cascade params. None = use defaults."""


def apply_anti_detection_chain(
    input_path: Path,
    output_path: Path,
    options: Optional[AntiDetectionOptions] = None,
) -> dict[str, Any]:
    """Run the full anti-detection chain.

    Parameters
    ----------
    input_path:
        The image to process. Typically the post-watermark-strip artifact.
    output_path:
        Where to write the final image (JPEG).
    options:
        Per-step toggles. See ``AntiDetectionOptions``.

    Returns
    -------
    dict with keys: ``stages`` (list of per-stage reports), ``self_check``
    (final score), ``input_score`` (baseline before chain ran), and
    ``output`` (path written).

    Raises
    ------
    AntiDetectionAbort
        When ``self_check`` runs in ``strict`` mode and the worst-detector
        score exceeds ``max_p_ai``.
    FileNotFoundError, ValueError
        Bubbles up from underlying forensic modules on bad inputs.
    """
    options = options or AntiDetectionOptions()
    input_path = Path(input_path)
    output_path = Path(output_path)
    if not input_path.exists():
        raise FileNotFoundError(f"anti-detection input missing: {input_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "stages": [],
        "input": str(input_path),
        "output": str(output_path),
        "options": {
            "cascade": options.cascade,
            "prnu_pattern": str(options.prnu_pattern) if options.prnu_pattern else None,
            "prnu_alpha": options.prnu_alpha,
            "donor_jpeg": str(options.donor_jpeg) if options.donor_jpeg else None,
            "self_check": options.self_check,
            "max_p_ai": options.max_p_ai,
            "strict": options.strict,
        },
    }

    # Optional baseline score for the demo "before/after" line.
    if options.self_check:
        t0 = time.monotonic()
        scores = selfcheck.detect_all(input_path)
        report["input_score"] = _serialize_scores(scores)
        report["input_score_ms"] = int((time.monotonic() - t0) * 1000)

    work = output_path.with_suffix(".chain-work.jpg")
    current = input_path

    # ── Stage 1: cascade laundering ────────────────────────────────────
    if options.cascade:
        t0 = time.monotonic()
        params = options.cascade_params or cascade_mod.CascadeParams()
        _ = cascade_mod.cascade(current, work, params=params, score_before_after=False)
        report["stages"].append({
            "name": "cascade_launder",
            "ok": True,
            "ms": int((time.monotonic() - t0) * 1000),
            "params": _cascade_params_dict(params),
        })
        current = work
    else:
        report["stages"].append({"name": "cascade_launder", "ok": True, "skipped": True})

    # ── Stage 2: PRNU injection ────────────────────────────────────────
    if options.prnu_pattern is not None:
        prnu_path = Path(options.prnu_pattern)
        if not prnu_path.exists():
            report["stages"].append({
                "name": "prnu_inject",
                "ok": False,
                "skipped": True,
                "reason": f"PRNU pattern not found: {prnu_path}",
            })
        else:
            from .prnu import extract as prnu_extract
            from .prnu import inject as prnu_inject
            t0 = time.monotonic()
            prnu = prnu_extract.load_prnu(prnu_path)
            prnu_out = output_path.with_suffix(".chain-prnu.jpg")
            prnu_inject.inject_prnu(current, prnu, prnu_out, alpha=options.prnu_alpha)
            corr = prnu_inject.correlate(prnu_out, prnu)
            if current != input_path and current.exists() and current != prnu_out:
                current.unlink(missing_ok=True)
            current = prnu_out
            report["stages"].append({
                "name": "prnu_inject",
                "ok": True,
                "ms": int((time.monotonic() - t0) * 1000),
                "alpha": options.prnu_alpha,
                "correlation": float(corr),
            })
    else:
        report["stages"].append({"name": "prnu_inject", "ok": True, "skipped": True})

    # ── Stage 3: signature match ───────────────────────────────────────
    if options.donor_jpeg is not None:
        donor = Path(options.donor_jpeg)
        if not donor.exists():
            report["stages"].append({
                "name": "signature_match",
                "ok": False,
                "skipped": True,
                "reason": f"donor JPEG not found: {donor}",
            })
            shutil.copy2(current, output_path)
        else:
            from .signature import full_signature_match
            t0 = time.monotonic()
            sig_status = full_signature_match(current, donor, output_path)
            report["stages"].append({
                "name": "signature_match",
                "ok": True,
                "ms": int((time.monotonic() - t0) * 1000),
                "donor": str(donor),
                **{k: v for k, v in sig_status.items()},
            })
            if current != input_path and current.exists() and current != output_path:
                current.unlink(missing_ok=True)
    else:
        # No donor — promote current → output as-is.
        report["stages"].append({"name": "signature_match", "ok": True, "skipped": True})
        if current != output_path:
            shutil.copy2(current, output_path)
            if current != input_path:
                current.unlink(missing_ok=True)

    # ── Stage 4: self-check (multi-detector minimax) ───────────────────
    if options.self_check:
        t0 = time.monotonic()
        scores = selfcheck.detect_all(output_path)
        worst_p_ai = max((s.p_ai for s in scores), default=0.0)
        report["self_check"] = {
            "ms": int((time.monotonic() - t0) * 1000),
            "scores": _serialize_scores(scores),
            "worst_p_ai": worst_p_ai,
            "worst_detector": _worst_model(scores),
            "threshold": options.max_p_ai,
            "passed": worst_p_ai <= options.max_p_ai,
        }
        report["stages"].append({
            "name": "self_check",
            "ok": True,
            "ms": report["self_check"]["ms"],
            "worst_p_ai": worst_p_ai,
            "passed": worst_p_ai <= options.max_p_ai,
        })

        if worst_p_ai > options.max_p_ai:
            msg = (
                f"self-check refused output: worst surrogate p_ai="
                f"{worst_p_ai:.3f} > threshold={options.max_p_ai:.3f} "
                f"(detector={report['self_check']['worst_detector']})"
            )
            if options.strict:
                raise AntiDetectionAbort(msg, report=report)
            log.warning(msg)
    else:
        report["stages"].append({"name": "self_check", "ok": True, "skipped": True})

    return report


# ─────────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────────


def _serialize_scores(scores: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "model": s.model,
            "backend": s.backend,
            "p_ai": float(s.p_ai),
            "p_real": float(s.p_real),
            "raw_label": s.raw_label,
        }
        for s in scores
    ]


def _worst_model(scores: list[Any]) -> Optional[str]:
    if not scores:
        return None
    worst = max(scores, key=lambda s: s.p_ai)
    return worst.model


def _cascade_params_dict(params: cascade_mod.CascadeParams) -> dict[str, Any]:
    """Best-effort serialization of CascadeParams."""
    out: dict[str, Any] = {}
    for f in ("blend1", "blend2", "saturation", "contrast"):
        if hasattr(params, f):
            out[f] = getattr(params, f)
    if hasattr(params, "pass1"):
        try:
            out["pass1"] = asdict(params.pass1)
        except TypeError:
            pass
    if hasattr(params, "pass2"):
        try:
            out["pass2"] = asdict(params.pass2)
        except TypeError:
            pass
    return out


# Keep `laundering` import used (suppresses lint, also documents dependency).
_ = laundering


__all__ = [
    "AntiDetectionOptions",
    "AntiDetectionAbort",
    "apply_anti_detection_chain",
]
