"""Tests for the mission orchestrator: spec parsing, schema validation,
provenance grading, result serialization. Network-free — no DALL-E,
no Telegram, no Vertex/Bedrock calls.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mendacity.mission import (
    MissionResult,
    MissionSpec,
    MissionValidationError,
    StageRecord,
    _grade_provenance,
    _schema_check,
    validate_spec,
)


# ---------------------------------------------------------------------------
# Schema validator
# ---------------------------------------------------------------------------


def _good_spec_dict() -> dict:
    return {
        "mission_id": "TEST-001",
        "operator": "J2-INSCOM-Demo",
        "authorization": {
            "authority": "title-10",
            "target_class": "foreign",
            "approval_chain": ["J2"],
        },
        "target": {
            "platform": "telegram",
            "channel": "@mendacity_sandbox_demo",
            "audience_profile": "test",
        },
        "persona": {
            "archetype": "test-archetype",
            "name_seed": "Vlad K.",
            "generate_avatar": False,
        },
        "artifact": {
            "type": "image",
            "prompt": "test prompt",
            "source": "generate",
            "must_pass": ["c2pa", "titan", "synthid"],
            "strip_watermarks": True,
        },
        "delivery": {"dry_run": True, "caption": ""},
    }


def test_schema_check_happy_path_no_issues():
    spec = MissionSpec.from_dict(_good_spec_dict())
    assert _schema_check(spec) == []


def test_schema_check_catches_bad_authority():
    d = _good_spec_dict()
    d["authorization"]["authority"] = "title-50"
    spec = MissionSpec.from_dict(d)
    issues = _schema_check(spec)
    assert any("authority" in i and "title-10" in i for i in issues)


def test_schema_check_catches_bad_target_class():
    d = _good_spec_dict()
    d["authorization"]["target_class"] = "domestic"
    spec = MissionSpec.from_dict(d)
    assert any("target_class" in i for i in _schema_check(spec))


def test_schema_check_catches_bad_platform():
    d = _good_spec_dict()
    d["target"]["platform"] = "discord"
    spec = MissionSpec.from_dict(d)
    assert any("platform" in i for i in _schema_check(spec))


def test_schema_check_catches_missing_must_pass():
    d = _good_spec_dict()
    d["artifact"]["must_pass"] = ["c2pa"]   # missing titan + synthid
    spec = MissionSpec.from_dict(d)
    issues = _schema_check(spec)
    msg = " ".join(issues)
    assert "must_pass" in msg and "titan" in msg and "synthid" in msg


def test_schema_check_catches_bad_source():
    d = _good_spec_dict()
    d["artifact"]["source"] = "https://evil.example.com"
    spec = MissionSpec.from_dict(d)
    assert any("artifact.source" in i for i in _schema_check(spec))


def test_schema_check_requires_prompt_when_generate():
    d = _good_spec_dict()
    d["artifact"]["source"] = "generate"
    d["artifact"]["prompt"] = ""
    spec = MissionSpec.from_dict(d)
    assert any("prompt" in i for i in _schema_check(spec))


def test_schema_check_requires_persona_id_or_archetype_when_live():
    """When dry_run=false the spec must supply EITHER an explicit persona_id
    OR a persona.archetype the engine can resolve via the matcher."""
    d = _good_spec_dict()
    d["delivery"]["dry_run"] = False
    d["delivery"]["persona_id"] = ""
    d["persona"]["archetype"] = ""
    spec = MissionSpec.from_dict(d)
    issues = _schema_check(spec)
    assert any("persona_id" in i or "archetype" in i for i in issues)


def test_schema_check_archetype_alone_is_ok_when_live():
    """Archetype set + persona_id empty + dry_run=false should pass schema —
    preflight will resolve persona_id from archetype via the matcher."""
    d = _good_spec_dict()
    d["delivery"]["dry_run"] = False
    d["delivery"]["persona_id"] = ""
    d["persona"]["archetype"] = "frustrated-quartermaster"
    spec = MissionSpec.from_dict(d)
    issues = _schema_check(spec)
    assert not any("persona_id" in i for i in issues)


def test_schema_check_persona_id_alone_is_ok_when_live():
    """persona_id set + archetype empty should pass schema."""
    d = _good_spec_dict()
    d["delivery"]["dry_run"] = False
    d["delivery"]["persona_id"] = "anton_kh"
    d["persona"]["archetype"] = ""
    spec = MissionSpec.from_dict(d)
    issues = _schema_check(spec)
    assert not any("persona_id" in i for i in issues)


def test_schema_check_collects_multiple_issues():
    d = _good_spec_dict()
    d["authorization"]["authority"] = "title-50"
    d["target"]["platform"] = "discord"
    d["artifact"]["type"] = "video"
    spec = MissionSpec.from_dict(d)
    issues = _schema_check(spec)
    assert len(issues) >= 3   # all reported, not first-failure


def test_schema_check_bad_mission_id():
    d = _good_spec_dict()
    d["mission_id"] = "1 invalid id with spaces"
    spec = MissionSpec.from_dict(d)
    assert any("mission_id" in i for i in _schema_check(spec))


# ---------------------------------------------------------------------------
# validate_spec end-to-end (raises with code)
# ---------------------------------------------------------------------------


def test_validate_spec_happy_path_does_not_raise(tmp_path, monkeypatch):
    spec = MissionSpec.from_dict(_good_spec_dict())
    # validate_spec needs the real allowlist; use the actual file.
    validate_spec(spec)   # should not raise


def test_validate_spec_raises_on_bad_authority():
    d = _good_spec_dict()
    d["authorization"]["authority"] = "title-50"
    spec = MissionSpec.from_dict(d)
    with pytest.raises(MissionValidationError) as exc:
        validate_spec(spec)
    assert exc.value.code == "validation_failed"


def test_validate_spec_raises_on_unauthorized_channel():
    d = _good_spec_dict()
    d["target"]["channel"] = "@some_random_unsanctioned_channel"
    spec = MissionSpec.from_dict(d)
    with pytest.raises(MissionValidationError) as exc:
        validate_spec(spec)
    assert exc.value.code == "channel_not_authorized"


def test_validate_spec_aggregates_schema_issues_in_message():
    d = _good_spec_dict()
    d["authorization"]["authority"] = "title-50"
    d["artifact"]["type"] = "video"
    spec = MissionSpec.from_dict(d)
    with pytest.raises(MissionValidationError) as exc:
        validate_spec(spec)
    msg = str(exc.value)
    assert "title-10" in msg and "image" in msg


# ---------------------------------------------------------------------------
# Provenance grader
# ---------------------------------------------------------------------------


def _make_report(c2pa: str, titan: str, synthid: str) -> dict:
    """Build a minimal provenance report for grading tests."""
    return {
        "c2pa": {"status": c2pa},
        "titan_watermark": {"status": titan, "detectionResult": "MACHINE_GENERATED_NOT_DETECTED"} if titan == "ok" else {"status": titan},
        "google_synthid": {"status": synthid, "watermark_verification_result": "NOT_WATERMARKED"} if synthid == "ok" else {"status": synthid},
    }


def test_grade_all_pass_when_no_manifests_and_skipped_clouds():
    rep = _make_report(c2pa="manifest_not_found", titan="skipped", synthid="skipped")
    g = _grade_provenance(
        rep, {"c2pa", "titan", "synthid"}, ran_titan=False, ran_google=False
    )
    assert g["per_detector"]["c2pa"] is True
    assert g["per_detector"]["titan"] is True
    assert g["per_detector"]["synthid"] is True
    assert g["all_passed"] is True


def test_grade_fail_when_c2pa_manifest_present():
    rep = _make_report(c2pa="ok", titan="skipped", synthid="skipped")
    g = _grade_provenance(
        rep, {"c2pa", "titan", "synthid"}, ran_titan=False, ran_google=False
    )
    assert g["per_detector"]["c2pa"] is False
    assert g["all_passed"] is False


def test_grade_skipped_cloud_treated_as_pass_inconclusive():
    rep = _make_report(c2pa="manifest_not_found", titan="skipped", synthid="skipped")
    g = _grade_provenance(
        rep, {"c2pa", "titan", "synthid"}, ran_titan=False, ran_google=False
    )
    # Skipped detectors flagged via ran_titan/ran_google; per-detector still True
    assert g["ran_titan"] is False
    assert g["ran_google"] is False


def test_grade_titan_real_run_pass():
    rep = _make_report(c2pa="manifest_not_found", titan="ok", synthid="skipped")
    g = _grade_provenance(
        rep, {"c2pa", "titan", "synthid"}, ran_titan=True, ran_google=False
    )
    assert g["per_detector"]["titan"] is True
    assert g["ran_titan"] is True


def test_grade_titan_real_run_fail():
    rep = {
        "c2pa": {"status": "manifest_not_found"},
        "titan_watermark": {"status": "ok", "detectionResult": "MACHINE_GENERATED_DETECTED"},
        "google_synthid": {"status": "skipped"},
    }
    g = _grade_provenance(
        rep, {"c2pa", "titan", "synthid"}, ran_titan=True, ran_google=False
    )
    assert g["per_detector"]["titan"] is False
    assert g["all_passed"] is False


# ---------------------------------------------------------------------------
# Result serialization
# ---------------------------------------------------------------------------


def test_mission_result_serializes_to_dict():
    r = MissionResult(
        mission_id="TEST-002",
        operator="op",
        status="completed",
        started_at="2026-05-03T00:00:00+00:00",
        finished_at="2026-05-03T00:00:01+00:00",
        stages=[StageRecord(stage="validated", status="ok", ts="t", detail={"x": 1})],
        final_artifact_path="/tmp/x.jpg",
        final_provenance_report={"c2pa": {"status": "manifest_not_found"}},
        error=None,
        spec={"mission_id": "TEST-002"},
    )
    d = r.to_dict()
    s = json.dumps(d)   # round-trip safety
    parsed = json.loads(s)
    assert parsed["mission_id"] == "TEST-002"
    assert parsed["status"] == "completed"
    assert parsed["error"] is None
    assert len(parsed["stages"]) == 1


def test_mission_result_failure_has_structured_error():
    r = MissionResult(
        mission_id="TEST-003",
        operator="op",
        status="failed",
        started_at="t1",
        finished_at="t2",
        error={"stage": "validated", "code": "validation_failed", "message": "oops"},
    )
    d = r.to_dict()
    assert d["error"]["code"] == "validation_failed"
    assert d["error"]["stage"] == "validated"


# ---------------------------------------------------------------------------
# Result-emit contract validator
# ---------------------------------------------------------------------------


def test_validate_result_dict_happy_path():
    from mendacity.mission import _validate_result_dict
    r = MissionResult(
        mission_id="TEST-OK",
        operator="op",
        status="completed",
        started_at="2026-05-03T00:00:00+00:00",
        finished_at="2026-05-03T00:00:01+00:00",
        stages=[StageRecord(stage="validated", status="ok", ts="t")],
    )
    assert _validate_result_dict(r.to_dict()) == []


def test_validate_result_dict_catches_bad_status():
    from mendacity.mission import _validate_result_dict
    d = {
        "mission_id": "X",
        "operator": "op",
        "status": "weird",
        "started_at": "t",
        "stages": [],
    }
    issues = _validate_result_dict(d)
    assert any("status" in i for i in issues)


def test_validate_result_dict_catches_bad_stage_shape():
    from mendacity.mission import _validate_result_dict
    d = {
        "mission_id": "X",
        "operator": "op",
        "status": "completed",
        "started_at": "t",
        "stages": [{"name": "missing-stage-key"}],
    }
    issues = _validate_result_dict(d)
    assert any("stage" in i for i in issues)


def test_validate_result_dict_catches_missing_error_fields():
    from mendacity.mission import _validate_result_dict
    d = {
        "mission_id": "X",
        "operator": "op",
        "status": "failed",
        "started_at": "t",
        "stages": [],
        "error": {"stage": "validated"},   # missing code + message
    }
    issues = _validate_result_dict(d)
    assert any("error.code" in i for i in issues)
    assert any("error.message" in i for i in issues)


def test_validate_result_dict_null_error_is_ok():
    from mendacity.mission import _validate_result_dict
    d = {
        "mission_id": "X",
        "operator": "op",
        "status": "completed",
        "started_at": "t",
        "stages": [],
        "error": None,
    }
    issues = _validate_result_dict(d)
    # error=None is the success-shape; no issues from that.
    assert not any("error" in i for i in issues)
