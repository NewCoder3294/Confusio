"""Shared verdict dataclasses. Pure data, no I/O, no side effects."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    pass_ = "pass"   # `pass` is reserved
    warn = "warn"
    fail = "fail"
    na = "n/a"


class VerdictLevel(str, Enum):
    AUTHENTIC = "AUTHENTIC"
    SUSPECT = "SUSPECT"
    SYNTHETIC = "SYNTHETIC"


@dataclass(frozen=True)
class DetectorSignal:
    detector: str
    severity: Severity
    score: float | None
    evidence: str
    latency_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "detector": self.detector,
            "severity": self.severity.value,
            "score": self.score,
            "evidence": self.evidence,
            "latency_ms": self.latency_ms,
        }


@dataclass(frozen=True)
class Verdict:
    level: VerdictLevel
    confidence: float
    summary: str
    signals: list[DetectorSignal] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level.value,
            "confidence": self.confidence,
            "summary": self.summary,
            "signals": [s.to_dict() for s in self.signals],
        }
