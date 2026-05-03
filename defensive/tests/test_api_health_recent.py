"""Tests for GET /v1/health and GET /v1/recent."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from defensive.api.server import app


@pytest.fixture(autouse=True)
def _patch_warmup(monkeypatch):
    """Prevent the lifespan warm-up from downloading the HF model."""
    from defensive.api import server
    monkeypatch.setattr(server, "_warmup_classifier", lambda: None)


# ---------------------------------------------------------------------------
# /v1/health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_returns_200_ok_shape(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEFENSIVE_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
        client = TestClient(app)
        r = client.get("/v1/health")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert isinstance(body["classifier_warm"], bool)
        assert "detectors" in body
        assert len(body["detectors"]) == 7
        assert isinstance(body["audit_count"], int)

    def test_audit_count_counts_lines(self, monkeypatch, tmp_path):
        audit_file = tmp_path / "audit.jsonl"
        # Write 3 fake JSONL lines
        for i in range(3):
            audit_file.write_text(
                "\n".join(
                    json.dumps({"artifact_id": f"a{j}", "sha256": "x", "ts": "t",
                                "operator": "op", "source": "verify_tab",
                                "verdict_level": "AUTHENTIC", "verdict_confidence": 0.9,
                                "verdict_summary": "ok", "signals": []})
                    for j in range(i + 1)
                ) + "\n",
                encoding="utf-8",
            )
            # re-count; just test final state
        monkeypatch.setenv("DEFENSIVE_AUDIT_PATH", str(audit_file))
        client = TestClient(app)
        r = client.get("/v1/health")
        assert r.status_code == 200
        assert r.json()["audit_count"] == 3  # last write had 3 lines

    def test_audit_count_zero_when_file_missing(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEFENSIVE_AUDIT_PATH", str(tmp_path / "nonexistent.jsonl"))
        client = TestClient(app)
        r = client.get("/v1/health")
        assert r.status_code == 200
        assert r.json()["audit_count"] == 0

    def test_classifier_warm_false_when_pipeline_none(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEFENSIVE_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
        from defensive.engine.detectors import ai_classifier as _ai_mod
        original = _ai_mod._pipeline
        _ai_mod._pipeline = None
        try:
            client = TestClient(app)
            r = client.get("/v1/health")
            assert r.json()["classifier_warm"] is False
        finally:
            _ai_mod._pipeline = original


# ---------------------------------------------------------------------------
# /v1/recent
# ---------------------------------------------------------------------------

def _make_audit_file(path, n: int) -> None:
    """Write n JSONL rows to path, timestamps like 2026-01-01T00:00:0NZ."""
    rows = []
    for i in range(n):
        rows.append(json.dumps({
            "ts": f"2026-01-01T00:00:{i:02d}+00:00",
            "artifact_id": f"aid-{i}",
            "sha256": f"sha{i:04x}",
            "operator": "J2-INSCOM-Demo",
            "source": "verify_tab",
            "verdict_level": "AUTHENTIC",
            "verdict_confidence": 0.9,
            "verdict_summary": "ok",
            "signals": [],
        }))
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


class TestRecent:
    def test_returns_empty_when_no_audit_file(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DEFENSIVE_AUDIT_PATH", str(tmp_path / "nope.jsonl"))
        client = TestClient(app)
        r = client.get("/v1/recent")
        assert r.status_code == 200
        assert r.json() == {"items": []}

    def test_returns_items_newest_first(self, monkeypatch, tmp_path):
        audit_file = tmp_path / "audit.jsonl"
        _make_audit_file(audit_file, 5)
        monkeypatch.setenv("DEFENSIVE_AUDIT_PATH", str(audit_file))
        client = TestClient(app)
        r = client.get("/v1/recent?limit=5")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 5
        # Newest first: last written row (aid-4) should come first
        assert items[0]["artifact_id"] == "aid-4"
        assert items[-1]["artifact_id"] == "aid-0"

    def test_limit_caps_results(self, monkeypatch, tmp_path):
        audit_file = tmp_path / "audit.jsonl"
        _make_audit_file(audit_file, 20)
        monkeypatch.setenv("DEFENSIVE_AUDIT_PATH", str(audit_file))
        client = TestClient(app)
        r = client.get("/v1/recent?limit=3")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 3

    def test_default_limit_is_ten(self, monkeypatch, tmp_path):
        audit_file = tmp_path / "audit.jsonl"
        _make_audit_file(audit_file, 15)
        monkeypatch.setenv("DEFENSIVE_AUDIT_PATH", str(audit_file))
        client = TestClient(app)
        r = client.get("/v1/recent")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 10

    def test_item_fields_present(self, monkeypatch, tmp_path):
        audit_file = tmp_path / "audit.jsonl"
        _make_audit_file(audit_file, 1)
        monkeypatch.setenv("DEFENSIVE_AUDIT_PATH", str(audit_file))
        client = TestClient(app)
        r = client.get("/v1/recent?limit=1")
        item = r.json()["items"][0]
        for field in ("ts", "artifact_id", "sha256", "operator", "source",
                      "verdict_level", "verdict_confidence", "verdict_summary"):
            assert field in item, f"missing field: {field}"
