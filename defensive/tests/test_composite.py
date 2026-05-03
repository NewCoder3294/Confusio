"""Truth-table tests for composite.reduce()."""
import pytest

from defensive.engine.composite import reduce
from defensive.engine.verdict import (
    DetectorSignal,
    Severity,
    VerdictLevel,
)


def _sig(detector: str, sev: Severity, score: float | None = None) -> DetectorSignal:
    return DetectorSignal(
        detector=detector, severity=sev, score=score,
        evidence="x", latency_ms=1,
    )


class TestReduceLevel:
    def test_all_pass_is_authentic(self):
        sigs = [_sig(d, Severity.pass_) for d in
                ("c2pa", "synthid", "titan", "ai_classifier", "exif", "ela", "phash")]
        v = reduce(sigs)
        assert v.level is VerdictLevel.AUTHENTIC

    def test_any_fail_is_synthetic(self):
        sigs = [_sig(d, Severity.pass_) for d in
                ("c2pa", "synthid", "titan", "exif", "ela", "phash")]
        sigs.append(_sig("ai_classifier", Severity.fail, 0.94))
        v = reduce(sigs)
        assert v.level is VerdictLevel.SYNTHETIC

    def test_any_warn_without_fail_is_suspect(self):
        sigs = [_sig(d, Severity.pass_) for d in
                ("c2pa", "synthid", "titan", "ai_classifier", "ela", "phash")]
        sigs.append(_sig("exif", Severity.warn))
        v = reduce(sigs)
        assert v.level is VerdictLevel.SUSPECT

    def test_only_na_signals_is_authentic_low_confidence(self):
        sigs = [_sig(d, Severity.na) for d in
                ("c2pa", "synthid", "titan", "ai_classifier", "exif", "ela", "phash")]
        v = reduce(sigs)
        assert v.level is VerdictLevel.AUTHENTIC
        assert v.confidence == 0.0


class TestReduceConfidence:
    def test_all_pass_high_confidence(self):
        sigs = [_sig(d, Severity.pass_) for d in
                ("c2pa", "synthid", "titan", "ai_classifier", "exif", "ela", "phash")]
        v = reduce(sigs)
        assert v.confidence == pytest.approx(1.0, abs=0.001)

    def test_strong_synthetic_high_confidence(self):
        sigs = [
            _sig("c2pa", Severity.warn),
            _sig("synthid", Severity.warn),
            _sig("titan", Severity.warn),
            _sig("ai_classifier", Severity.fail, 0.94),
            _sig("exif", Severity.fail),
            _sig("ela", Severity.pass_),
            _sig("phash", Severity.pass_),
        ]
        v = reduce(sigs)
        assert v.level is VerdictLevel.SYNTHETIC
        # ai_classifier (0.30) + exif (0.20) backing the SYNTHETIC level,
        # ela (0.10) and phash (0.05) backing AUTHENTIC ⇒ subtract halves.
        # 0.50 - (0.10 + 0.05) * 0.5 = 0.425
        assert 0.3 < v.confidence < 0.6

    def test_confidence_clamped_zero(self):
        # Mostly disagreement should not go negative.
        sigs = [
            _sig("c2pa", Severity.pass_),
            _sig("synthid", Severity.fail),
            _sig("titan", Severity.fail),
            _sig("ai_classifier", Severity.pass_),
            _sig("exif", Severity.pass_),
            _sig("ela", Severity.pass_),
            _sig("phash", Severity.pass_),
        ]
        v = reduce(sigs)
        assert 0.0 <= v.confidence <= 1.0


class TestReduceSummary:
    def test_summary_mentions_top_signals(self):
        sigs = [
            _sig("c2pa", Severity.warn),
            _sig("synthid", Severity.warn),
            _sig("titan", Severity.warn),
            _sig("ai_classifier", Severity.fail, 0.94),
            _sig("exif", Severity.fail),
            _sig("ela", Severity.pass_),
            _sig("phash", Severity.pass_),
        ]
        v = reduce(sigs)
        assert "ai_classifier" in v.summary or "exif" in v.summary
