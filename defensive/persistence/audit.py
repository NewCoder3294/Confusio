"""Append-only audit log for defensive verifications."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from defensive.engine.verdict import Verdict


def default_path() -> Path:
    override = os.environ.get("DEFENSIVE_AUDIT_PATH")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "audit.jsonl"


def append(
    *,
    log_path: Path | None = None,
    artifact_id: str,
    sha256: str,
    operator: str,
    source: str,
    verdict: Verdict,
) -> None:
    path = log_path or default_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "artifact_id": artifact_id,
        "sha256": sha256,
        "operator": operator,
        "source": source,
        "verdict_level": verdict.level.value,
        "verdict_confidence": verdict.confidence,
        "verdict_summary": verdict.summary,
        "signals": [
            {"detector": s.detector, "severity": s.severity.value,
             "score": s.score, "evidence": s.evidence}
            for s in verdict.signals
        ],
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
