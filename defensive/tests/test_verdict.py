"""Tests for Verdict, DetectorSignal, Severity."""
from defensive.engine.verdict import (
    DetectorSignal,
    Severity,
    Verdict,
    VerdictLevel,
)


class TestSeverity:
    def test_values(self):
        assert {s.value for s in Severity} == {"pass", "warn", "fail", "n/a"}


class TestVerdictLevel:
    def test_values(self):
        assert {v.value for v in VerdictLevel} == {"AUTHENTIC", "SUSPECT", "SYNTHETIC"}


class TestDetectorSignal:
    def test_construct(self):
        sig = DetectorSignal(
            detector="c2pa",
            severity=Severity.warn,
            score=None,
            evidence="no manifest",
            latency_ms=38,
        )
        assert sig.detector == "c2pa"
        assert sig.severity is Severity.warn

    def test_to_dict_serialises_severity_as_string(self):
        sig = DetectorSignal(
            detector="ai_classifier",
            severity=Severity.fail,
            score=0.94,
            evidence="p(artificial)=0.94",
            latency_ms=1480,
        )
        assert sig.to_dict() == {
            "detector": "ai_classifier",
            "severity": "fail",
            "score": 0.94,
            "evidence": "p(artificial)=0.94",
            "latency_ms": 1480,
        }


class TestVerdict:
    def test_to_dict(self):
        sig = DetectorSignal(
            detector="ela", severity=Severity.pass_, score=0.12,
            evidence="within nominal", latency_ms=89,
        )
        v = Verdict(
            level=VerdictLevel.AUTHENTIC,
            confidence=0.92,
            summary="No synthesis indicators.",
            signals=[sig],
        )
        d = v.to_dict()
        assert d["level"] == "AUTHENTIC"
        assert d["confidence"] == 0.92
        assert d["summary"] == "No synthesis indicators."
        assert d["signals"] == [sig.to_dict()]
