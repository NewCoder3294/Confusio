"""Tests for the audit wrapper."""
import json
from pathlib import Path

from defensive.persistence.audit import append, default_path
from defensive.engine.verdict import Severity, Verdict, VerdictLevel, DetectorSignal


def _verdict() -> Verdict:
    return Verdict(
        level=VerdictLevel.SUSPECT,
        confidence=0.81,
        summary="ai_classifier strongly positive",
        signals=[DetectorSignal("ai_classifier", Severity.fail, 0.94, "p=0.94", 1480)],
    )


class TestAuditAppend:
    def test_writes_one_jsonl_line(self, tmp_path):
        log = tmp_path / "audit.jsonl"
        append(
            log_path=log,
            artifact_id="ARTIFACT-1",
            sha256="4f3a",
            operator="J2-INSCOM-Demo",
            source="verify_tab",
            verdict=_verdict(),
        )
        line = log.read_text().strip()
        row = json.loads(line)
        assert row["artifact_id"] == "ARTIFACT-1"
        assert row["sha256"] == "4f3a"
        assert row["operator"] == "J2-INSCOM-Demo"
        assert row["source"] == "verify_tab"
        assert row["verdict_level"] == "SUSPECT"
        assert row["verdict_confidence"] == 0.81

    def test_appends_subsequent_calls(self, tmp_path):
        log = tmp_path / "audit.jsonl"
        for aid in ("A", "B"):
            append(
                log_path=log, artifact_id=aid, sha256="x",
                operator="op", source="api_direct", verdict=_verdict(),
            )
        assert len(log.read_text().splitlines()) == 2

    def test_default_path_respects_env_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEFENSIVE_AUDIT_PATH", str(tmp_path / "x.jsonl"))
        assert default_path() == tmp_path / "x.jsonl"

    def test_default_path_falls_back(self, monkeypatch):
        monkeypatch.delenv("DEFENSIVE_AUDIT_PATH", raising=False)
        p = default_path()
        assert p.name == "audit.jsonl"
