"""Composite engine — orchestrates detectors and reduces signals to a Verdict."""
from __future__ import annotations

from defensive.engine.verdict import (
    DetectorSignal,
    Severity,
    Verdict,
    VerdictLevel,
)

WEIGHTS: dict[str, float] = {
    "ai_classifier": 0.30,
    "exif":          0.20,
    "c2pa":          0.15,
    "synthid":       0.10,
    "titan":         0.10,
    "ela":           0.10,
    "phash":         0.05,
}


def _level(signals: list[DetectorSignal]) -> VerdictLevel:
    severities = {s.severity for s in signals}
    if Severity.fail in severities:
        return VerdictLevel.SYNTHETIC
    if Severity.warn in severities:
        return VerdictLevel.SUSPECT
    return VerdictLevel.AUTHENTIC


def _confidence(signals: list[DetectorSignal], level: VerdictLevel) -> float:
    """Confidence = strength of evidence backing `level`.
    Each detector contributes +weight if its severity agrees with `level`,
    0 if warn or n/a, −weight × 0.5 if it disagrees.
    Clamped to [0, 1].
    """
    score = 0.0
    for s in signals:
        w = WEIGHTS.get(s.detector, 0.0)
        agrees = (
            (level is VerdictLevel.AUTHENTIC and s.severity is Severity.pass_)
            or (level is VerdictLevel.SYNTHETIC and s.severity is Severity.fail)
            or (level is VerdictLevel.SUSPECT and s.severity is Severity.warn)
        )
        disagrees = (
            (level is VerdictLevel.AUTHENTIC and s.severity is Severity.fail)
            or (level is VerdictLevel.SYNTHETIC and s.severity is Severity.pass_)
        )
        if agrees:
            score += w
        elif disagrees:
            score -= w * 0.5
    return max(0.0, min(1.0, score))


def _summary(signals: list[DetectorSignal], level: VerdictLevel) -> str:
    """One-line operator-readable conclusion. Mentions the load-bearing signals."""
    by_sev: dict[Severity, list[DetectorSignal]] = {}
    for s in signals:
        by_sev.setdefault(s.severity, []).append(s)

    if level is VerdictLevel.AUTHENTIC:
        passes = [s.detector for s in by_sev.get(Severity.pass_, [])]
        if passes:
            return f"All confirming signals consistent ({', '.join(sorted(passes))})."
        return "No positive evidence; verdict by absence of contrary signals."

    fails = [s for s in by_sev.get(Severity.fail, [])]
    warns = [s for s in by_sev.get(Severity.warn, [])]

    if fails:
        loud = max(fails, key=lambda s: WEIGHTS.get(s.detector, 0.0))
        others = [s.detector for s in fails if s.detector != loud.detector]
        prefix = f"{loud.detector}: {loud.evidence}"
        if others:
            return prefix + f"; also flagged by {', '.join(sorted(others))}."
        return prefix + "."

    # SUSPECT: warns only
    detectors = sorted(s.detector for s in warns)
    return f"Ambiguous signals from {', '.join(detectors)}."


def reduce(signals: list[DetectorSignal]) -> Verdict:
    level = _level(signals)
    confidence = _confidence(signals, level)
    summary = _summary(signals, level)
    return Verdict(
        level=level, confidence=round(confidence, 4),
        summary=summary, signals=list(signals),
    )
