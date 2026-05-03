"""Client-side hydration of an engine MissionResult into the Foundry Ontology.

The bridge calls `hydrate(result_dict, client, ontology_rid)` after reading a
`<mission_id>.json` from `missions/results/`. This module does the actual
parsing-and-row-writing.

Why client-side and not a Foundry-side action?
--------------------------------------------
For the hackathon, we picked the path that requires zero Foundry-side Python
deployment. A Foundry-side `ingestMissionResult` action — written as a
Functions-on-Objects in a Code Repository — would be the v2 home for this
logic; it would give us atomic transactional writes and put the hydration in
Foundry's audit trail. v1 trades that for "no Code Repository to set up the
night before the demo." The structure here mirrors what a Foundry-side
function would do, so the lift later is mechanical.

Architecture:

    parse_result(result_dict) → HydrationPlan          (pure, testable)
    apply_plan(plan, client, ontology_rid)             (the SDK calls)
    hydrate(result_dict, client, ontology_rid)         (the public entry)

`parse_result` has zero SDK imports. Everything in this file is unit-testable
without a Foundry tenant.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Iterable

LOG = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Plan types — what we'll write to the Ontology
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class MissionUpdate:
    mission_id: str
    fields: dict[str, Any]   # status, started_at, finished_at, failure_*, provenance_pass_rate, etc.


@dataclass
class PersonaUpsert:
    persona_id: str
    archetype: str
    display_name: str
    avatar_path: str | None
    created_for_mission: str
    created_at: str


@dataclass
class ArtifactUpsert:
    artifact_id: str
    mission_id: str
    type: str
    prompt: str
    source_path: str | None
    final_path: str
    source_sha256: str | None
    stripped_sha256: str | None
    final_sha256: str
    passed_c2pa: bool
    passed_titan: bool
    passed_synthid: bool
    passed_all: bool
    watermark_stripped: bool
    exif_transplanted: bool
    final_provenance_json: str
    created_at: str


@dataclass
class DetectionResultUpsert:
    result_id: str
    artifact_id: str
    detector: str          # c2pa | titan | synthid
    passed: bool
    run_status: str        # ok | skipped | error
    raw_response: str      # inline JSON
    checked_at: str


@dataclass
class MissionStageUpsert:
    stage_id: str
    mission_id: str
    seq: int
    name: str
    status: str
    ts: str
    detail_json: str
    summary: str | None


@dataclass
class HydrationPlan:
    mission_update: MissionUpdate
    personas: list[PersonaUpsert] = field(default_factory=list)
    artifacts: list[ArtifactUpsert] = field(default_factory=list)
    detection_results: list[DetectionResultUpsert] = field(default_factory=list)
    stages: list[MissionStageUpsert] = field(default_factory=list)

    def __str__(self) -> str:
        return (
            f"HydrationPlan(mission={self.mission_update.mission_id}, "
            f"personas={len(self.personas)}, artifacts={len(self.artifacts)}, "
            f"detection_results={len(self.detection_results)}, stages={len(self.stages)})"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Parsing — pure
# ──────────────────────────────────────────────────────────────────────────────


# Canonical engine stage → Foundry-side detector key. Engine uses long names in
# the provenance report; the Ontology uses short names for compactness in
# Workshop pills.
_DETECTOR_KEY_MAP = {
    "c2pa": "c2pa",
    "titan_watermark": "titan",
    "google_synthid": "synthid",
}


def _stage_by_name(stages: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    """Return the *last* stage with the given name (so retries override earlier attempts)."""
    matches = [s for s in stages if s.get("stage") == name]
    return matches[-1] if matches else None


def _passed_map(provenance_check_stage: dict[str, Any] | None) -> dict[str, Any]:
    """Extract the per-detector pass map from the provenance_check stage."""
    if not provenance_check_stage:
        return {"per_detector": {}, "all_passed": False, "ran_titan": False, "ran_google": False}
    return provenance_check_stage.get("detail", {}).get("passed", {})


def _detector_run_status(report: dict[str, Any], engine_key: str) -> str:
    """Reads `final_provenance_report.<engine_key>.status` → ok|skipped|error."""
    section = (report or {}).get(engine_key) or {}
    status = section.get("status")
    if status in ("ok", "skipped", "error"):
        return status
    return "error"


def _summarize_stage(stage: dict[str, Any]) -> str | None:
    """Heuristic one-line operator-readable summary for a stage row."""
    name = stage.get("stage")
    status = stage.get("status")
    detail = stage.get("detail") or {}

    if name == "validated" and status == "ok":
        return f"Authority validated: {detail.get('authority')} / {detail.get('target_class')} → {detail.get('channel')}"
    if name == "persona_generated" and status == "ok":
        return f"Persona forged: {detail.get('archetype')} ({detail.get('name_seed')})"
    if name == "artifact_selected" and status == "ok":
        return f"Source artifact selected (sha256:{(detail.get('sha256') or '')[:8]})"
    if name == "watermark_strip":
        if status == "ok":
            after = (detail.get("after_sha") or "")[:8]
            return f"SynthID watermark stripped via {detail.get('tool', 'synthidbye')} → sha256:{after}"
        if status == "error":
            return "Watermark strip failed"
    if name == "exif_transplant" and status == "ok":
        after = (detail.get("after_sha") or "")[:8]
        return f"EXIF camera profile transplanted → sha256:{after}"
    if name == "provenance_check":
        # Defer to ProvenanceGrader for the rich version; this is the brief form.
        passed = detail.get("passed") or {}
        per = passed.get("per_detector") or {}
        bits = [f"{k}={'PASS' if v else 'FAIL'}" for k, v in per.items()]
        return "Provenance: " + ", ".join(bits)
    if name == "delivered":
        if status == "skipped":
            return f"Dry-run — would post to {detail.get('would_post_to', '?')}"
        if status == "ok":
            return f"Delivered to {detail.get('channel', '?')} (msg {detail.get('telegram_message_id')})"
        if status == "error":
            return "Delivery failed"
    return None


def parse_result(result: dict[str, Any]) -> HydrationPlan:
    """Convert an engine result dict into a HydrationPlan. Pure function."""
    mission_id = result["mission_id"]
    status = result.get("status", "completed")
    stages_raw = result.get("stages") or []
    spec = result.get("spec") or {}
    final_report = result.get("final_provenance_report") or {}
    error = result.get("error")

    started_at = result.get("started_at")
    finished_at = result.get("finished_at")

    # ── Mission update ──
    mission_fields: dict[str, Any] = {
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
    }
    if error:
        mission_fields["failure_stage"] = error.get("stage")
        mission_fields["failure_code"] = error.get("code")
        mission_fields["failure_message"] = error.get("message")
    else:
        mission_fields["failure_stage"] = None
        mission_fields["failure_code"] = None
        mission_fields["failure_message"] = None

    plan = HydrationPlan(mission_update=MissionUpdate(mission_id=mission_id, fields=mission_fields))

    # ── Persona ──
    persona_stage = _stage_by_name(stages_raw, "persona_generated")
    if persona_stage and persona_stage.get("status") == "ok":
        d = persona_stage.get("detail") or {}
        plan.personas.append(PersonaUpsert(
            persona_id=d.get("persona_id") or f"{mission_id}-persona",
            archetype=d.get("archetype") or spec.get("persona", {}).get("archetype", "unspecified"),
            display_name=d.get("name_seed") or spec.get("persona", {}).get("name_seed", ""),
            avatar_path=d.get("avatar_path"),
            created_for_mission=mission_id,
            created_at=persona_stage.get("ts") or started_at or _now_iso(),
        ))

    # ── Artifact ──
    selected = _stage_by_name(stages_raw, "artifact_selected")
    strip_stage = _stage_by_name(stages_raw, "watermark_strip")
    exif_stage = _stage_by_name(stages_raw, "exif_transplant")
    prov_stage = _stage_by_name(stages_raw, "provenance_check")
    final_path = result.get("final_artifact_path")
    final_sha = (final_report.get("meta") or {}).get("sha256")

    if final_path and final_sha:
        passed = _passed_map(prov_stage)
        per = passed.get("per_detector", {})
        artifact_id = f"{mission_id}-clean"   # see ontology.md §1.4 — switch when engine emits a real ID

        plan.artifacts.append(ArtifactUpsert(
            artifact_id=artifact_id,
            mission_id=mission_id,
            type="image",
            prompt=spec.get("artifact", {}).get("prompt", ""),
            source_path=(selected.get("detail") or {}).get("work_path") if selected else None,
            final_path=final_path,
            source_sha256=(selected.get("detail") or {}).get("sha256") if selected else None,
            stripped_sha256=(strip_stage.get("detail") or {}).get("after_sha") if strip_stage and strip_stage.get("status") == "ok" else None,
            final_sha256=final_sha,
            passed_c2pa=bool(per.get("c2pa", False)),
            passed_titan=bool(per.get("titan", False)),
            passed_synthid=bool(per.get("synthid", False)),
            passed_all=bool(passed.get("all_passed", False)),
            watermark_stripped=bool(strip_stage and strip_stage.get("status") == "ok"),
            exif_transplanted=bool(exif_stage and exif_stage.get("status") == "ok"),
            final_provenance_json=json.dumps(final_report, ensure_ascii=False),
            created_at=(prov_stage.get("ts") if prov_stage else None) or finished_at or _now_iso(),
        ))

        # ── Detection results — one row per detector ──
        for engine_key, short_name in _DETECTOR_KEY_MAP.items():
            section = (final_report.get(engine_key) or {})
            plan.detection_results.append(DetectionResultUpsert(
                result_id=f"{artifact_id}:{short_name}",
                artifact_id=artifact_id,
                detector=short_name,
                passed=bool(per.get(short_name, False)),
                run_status=_detector_run_status(final_report, engine_key),
                raw_response=json.dumps(section, ensure_ascii=False),
                checked_at=(prov_stage.get("ts") if prov_stage else None) or _now_iso(),
            ))

        # provenance_pass_rate for the mission — denormalized
        mission_fields["provenance_pass_rate"] = 1.0 if passed.get("all_passed") else 0.0

    # ── Stages — one row per emitted stage, in order ──
    for seq, st in enumerate(stages_raw):
        plan.stages.append(MissionStageUpsert(
            stage_id=f"{mission_id}:{seq}",
            mission_id=mission_id,
            seq=seq,
            name=st.get("stage", "unknown"),
            status=st.get("status", "ok"),
            ts=st.get("ts") or _now_iso(),
            detail_json=json.dumps(st.get("detail") or {}, ensure_ascii=False),
            summary=_summarize_stage(st),
        ))

    return plan


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ──────────────────────────────────────────────────────────────────────────────
# Apply — the SDK side
# ──────────────────────────────────────────────────────────────────────────────


def apply_plan(plan: HydrationPlan, client: Any, ontology_rid: str) -> None:
    """Push the plan into Foundry. Order matters — parents before children.

    Errors on individual rows are logged but don't raise; the bridge prefers
    partial hydration over no hydration during a live demo.
    """
    # 1. Mission update first — Persona / Artifact / Stage rows reference mission_id.
    _apply_one(client, ontology_rid, "Mission", plan.mission_update.mission_id, plan.mission_update.fields)

    # 2. Persona.
    for p in plan.personas:
        _apply_one(client, ontology_rid, "Persona", p.persona_id, _without_pk(asdict(p), "persona_id"))

    # 3. Artifact (Mission must already exist).
    for a in plan.artifacts:
        _apply_one(client, ontology_rid, "Artifact", a.artifact_id, _without_pk(asdict(a), "artifact_id"))

    # 4. DetectionResult (Artifact must already exist).
    for dr in plan.detection_results:
        _apply_one(client, ontology_rid, "DetectionResult", dr.result_id, _without_pk(asdict(dr), "result_id"))

    # 5. MissionStage.
    for st in plan.stages:
        _apply_one(client, ontology_rid, "MissionStage", st.stage_id, _without_pk(asdict(st), "stage_id"))


def _without_pk(d: dict[str, Any], pk: str) -> dict[str, Any]:
    return {k: v for k, v in d.items() if k != pk}


def _apply_one(client: Any, ontology_rid: str, type_name: str, pk_value: str, fields: dict[str, Any]) -> None:
    """Upsert a single row.

    The exact SDK call differs per `foundry-platform-sdk` version. The shape
    below assumes object-edit actions are auto-generated per type. If your
    tenant doesn't auto-generate edit actions, the alternative is the
    `objects.create` / `objects.modify` REST endpoint — adapt here once.
    """
    try:
        # Convention: Foundry auto-generates `create<TypeName>` and `edit<TypeName>` actions
        # when you mark a type "Editable" in Ontology Manager. Try edit first, fall back to create.
        client.ontologies.Ontology.Action.apply(
            ontology=ontology_rid,
            action=f"edit-{_kebab(type_name)}",
            parameters={**fields, _pk_field_for(type_name): pk_value},
        )
    except Exception as e_edit:
        try:
            client.ontologies.Ontology.Action.apply(
                ontology=ontology_rid,
                action=f"create-{_kebab(type_name)}",
                parameters={**fields, _pk_field_for(type_name): pk_value},
            )
        except Exception as e_create:
            LOG.error(
                "failed to upsert %s pk=%s: edit_err=%s create_err=%s",
                type_name, pk_value, e_edit, e_create,
            )


def _kebab(s: str) -> str:
    out: list[str] = []
    for i, ch in enumerate(s):
        if ch.isupper() and i > 0:
            out.append("-")
        out.append(ch.lower())
    return "".join(out)


def _pk_field_for(type_name: str) -> str:
    return {
        "Mission": "mission_id",
        "Persona": "persona_id",
        "Artifact": "artifact_id",
        "DetectionResult": "result_id",
        "MissionStage": "stage_id",
        "Channel": "channel_id",
    }[type_name]


# ──────────────────────────────────────────────────────────────────────────────
# Public entry
# ──────────────────────────────────────────────────────────────────────────────


def hydrate(result_dict: dict[str, Any], client: Any, ontology_rid: str) -> HydrationPlan:
    """Parse + apply. Returns the plan for logging / inspection."""
    plan = parse_result(result_dict)
    LOG.info("hydrating: %s", plan)
    apply_plan(plan, client, ontology_rid)
    return plan


# ──────────────────────────────────────────────────────────────────────────────
# Smoke test — run with: python -m palantir.aip.result_ingester missions/results/SHADOW-FOX-001.json
# ──────────────────────────────────────────────────────────────────────────────


if __name__ == "__main__":  # pragma: no cover
    import sys
    if len(sys.argv) != 2:
        sys.exit("usage: result_ingester.py <result.json>")
    with open(sys.argv[1]) as f:
        result = json.load(f)
    plan = parse_result(result)
    print(plan)
    print("Mission update:", plan.mission_update)
    print(f"Personas: {len(plan.personas)}; Artifacts: {len(plan.artifacts)}; "
          f"DetectionResults: {len(plan.detection_results)}; Stages: {len(plan.stages)}")
    if plan.stages:
        print("\nStage timeline (parsed):")
        for s in plan.stages:
            mark = {"ok": "✓", "error": "✗", "skipped": "·"}.get(s.status, "?")
            print(f"  [{mark}] {s.seq:>2}. {s.name:<20} — {s.summary or s.status}")
