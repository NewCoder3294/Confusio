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
                ("c2pa", "titan", "ai_classifier", "gemini_visual", "openai_visual", "exif", "ela", "phash")]
        v = reduce(sigs)
        assert v.level is VerdictLevel.AUTHENTIC

    def test_lone_classifier_fail_is_outvoted_by_other_passes(self):
        # ai_classifier is the noisy detector — modern phone HDR / WebP
        # re-encoding can flip it false-positive. When the higher-weight
        # detectors (gemini_visual, exif, ela, phash) all pass, the verdict
        # should not flip to SYNTHETIC on that one signal alone. The new
        # weighted-vote rule lands this in the AUTHENTIC band:
        # pass_w (gemini.30 + c2pa.15 + titan.05 + exif.15 + ela.10 + phash.05)
        # = 0.80 minus fail_w (ai_classifier.20) = +0.60 → AUTHENTIC.
        sigs = [_sig(d, Severity.pass_) for d in
                ("c2pa", "titan", "gemini_visual", "openai_visual", "exif", "ela", "phash")]
        sigs.append(_sig("ai_classifier", Severity.fail, 0.94))
        v = reduce(sigs)
        assert v.level is VerdictLevel.AUTHENTIC

    def test_realistic_synthetic_image_lands_synthetic(self):
        # Realistic synthetic image: c2pa/titan absent (na), exif missing
        # (warn), ai_classifier and gemini_visual both fail; ela and phash
        # pass. Net weight = +0.15 (ela.10 + phash.05) − 0.50 (gemini.30 +
        # ai.20) = −0.35 → SYNTHETIC.
        sigs = [
            _sig("c2pa", Severity.na),
            _sig("titan", Severity.na),
            _sig("ai_classifier", Severity.fail, 0.94),
            _sig("gemini_visual", Severity.fail, 0.92),
            _sig("exif", Severity.warn),
            _sig("ela", Severity.pass_),
            _sig("phash", Severity.pass_),
        ]
        v = reduce(sigs)
        assert v.level is VerdictLevel.SYNTHETIC

    def test_warns_without_fails_lands_in_suspect_band(self):
        # warns contribute zero to the weighted vote, so a campaign whose
        # only non-pass signal is a warn stays AUTHENTIC if the pass weight
        # is dominant. Use a true ambiguous case (mixed pass+warn around
        # the threshold) to assert SUSPECT.
        sigs = [
            _sig("c2pa", Severity.warn),
            _sig("titan", Severity.warn),
            _sig("ai_classifier", Severity.warn, 0.55),
            _sig("gemini_visual", Severity.warn, 0.5),
            _sig("exif", Severity.warn),
            _sig("ela", Severity.warn),
            _sig("phash", Severity.warn),
        ]
        v = reduce(sigs)
        # net = 0 (all warns) → SUSPECT
        assert v.level is VerdictLevel.SUSPECT

    def test_only_na_signals_is_suspect(self):
        # All detectors unable to check → net 0 → SUSPECT (honest "we
        # could not assess"), not AUTHENTIC by absence-of-evidence.
        sigs = [_sig(d, Severity.na) for d in
                ("c2pa", "titan", "ai_classifier", "gemini_visual", "openai_visual", "exif", "ela", "phash")]
        v = reduce(sigs)
        assert v.level is VerdictLevel.SUSPECT
        assert v.confidence == 0.0


class TestReduceConfidence:
    def test_all_pass_high_confidence(self):
        sigs = [_sig(d, Severity.pass_) for d in
                ("c2pa", "titan", "ai_classifier", "gemini_visual", "openai_visual", "exif", "ela", "phash")]
        v = reduce(sigs)
        assert v.confidence == pytest.approx(1.0, abs=0.001)

    def test_strong_synthetic_high_confidence(self):
        # Strong SYNTHETIC: both vision auditors fail, classifier fails,
        # exif missing. Under the 8-detector weights this lands clearly
        # negative (gemini.25 + openai.25 + ai.10 + exif.10 = 0.70 fail vs
        # ela.05 + phash.05 = 0.10 pass).
        sigs = [
            _sig("c2pa", Severity.na),
            _sig("titan", Severity.na),
            _sig("ai_classifier", Severity.fail, 0.94),
            _sig("gemini_visual", Severity.fail, 0.92),
            _sig("openai_visual", Severity.fail, 0.90),
            _sig("exif", Severity.fail),
            _sig("ela", Severity.pass_),
            _sig("phash", Severity.pass_),
        ]
        v = reduce(sigs)
        assert v.level is VerdictLevel.SYNTHETIC
        # Confidence reflects strength: fail weights agreeing minus pass
        # weights disagreeing × 0.5.
        assert v.confidence > 0.4

    def test_confidence_clamped_zero(self):
        # Mostly disagreement should not go negative.
        sigs = [
            _sig("c2pa", Severity.pass_),
            _sig("gemini_visual", Severity.fail),
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
            _sig("titan", Severity.warn),
            _sig("ai_classifier", Severity.fail, 0.94),
            _sig("gemini_visual", Severity.warn),
            _sig("exif", Severity.fail),
            _sig("ela", Severity.pass_),
            _sig("phash", Severity.pass_),
        ]
        v = reduce(sigs)
        assert "ai_classifier" in v.summary or "exif" in v.summary


# ---------------------------------------------------------------------------
# TestRun — composite.run() parallel dispatch
# ---------------------------------------------------------------------------

from unittest.mock import patch

from defensive.engine.composite import run as composite_run


class TestRun:
    def test_returns_one_signal_per_detector(self, tiny_jpeg_bytes):
        with patch("defensive.engine.detectors.titan.detect_titan_watermark",
                   side_effect=RuntimeError("no creds")), \
             patch("defensive.engine.detectors.ai_classifier._classify",
                   return_value=0.10), \
             patch("defensive.engine.detectors.gemini_visual._call_gemini",
                   return_value={"verdict": "authentic", "synthid_detected": False,
                                 "confidence": 0.9, "reasoning": "clean"}), \
             patch("defensive.engine.detectors.openai_visual._call_openai",
                   return_value={"verdict": "authentic",
                                 "confidence": 0.9, "reasoning": "clean"}), \
             patch("defensive.engine.detectors.c2pa.read_c2pa",
                   return_value={"status": "manifest_not_found"}):
            verdict = composite_run(tiny_jpeg_bytes, mime_type="image/jpeg")
        names = sorted(s.detector for s in verdict.signals)
        assert names == sorted(
            ["c2pa", "titan", "ai_classifier", "gemini_visual", "openai_visual", "exif", "ela", "phash"]
        )

    def test_one_detector_failing_does_not_kill_request(self, tiny_jpeg_bytes):
        with patch("defensive.engine.detectors.ai_classifier._classify",
                   side_effect=RuntimeError("model missing")), \
             patch("defensive.engine.detectors.gemini_visual._call_gemini",
                   return_value={"verdict": "authentic", "synthid_detected": False,
                                 "confidence": 0.9, "reasoning": "clean"}), \
             patch("defensive.engine.detectors.openai_visual._call_openai",
                   return_value={"verdict": "authentic",
                                 "confidence": 0.9, "reasoning": "clean"}), \
             patch("defensive.engine.detectors.titan.detect_titan_watermark",
                   side_effect=RuntimeError("no creds")), \
             patch("defensive.engine.detectors.c2pa.read_c2pa",
                   return_value={"status": "manifest_not_found"}):
            verdict = composite_run(tiny_jpeg_bytes, mime_type="image/jpeg")
        ai = next(s for s in verdict.signals if s.detector == "ai_classifier")
        from defensive.engine.verdict import Severity
        assert ai.severity is Severity.na
        # Other six still produced signals.
        assert len(verdict.signals) == 8
