"""Client-side hydration of an engine MissionResult into the Foundry Ontology.

The bridge calls `hydrate(result_dict, client, ontology_rid)` after reading a
`<mission_id>.json` from `missions/results/`. This module does the parsing
and the SDK action calls.

Schema this module targets (the slim 4-type version actually built in the
Foundry tenant — see `palantir/ontology.md` and the build session
2026-05-03):

    Channel          3 rows seeded for the demo
    Mission          one row per mission (persona + stages denormalized)
    Artifact         one row per finished mission's final artifact
    DetectionResult  three rows per artifact (c2pa, titan, synthid)

Persona fields live on Mission (`personaArchetype`, `personaNameSeed`).
Stage events live on Mission as a single JSON blob (`stagesJson`). This
collapses two object types relative to the original brief in exchange for
~60 minutes of GUI build time.

Parameter naming convention (verified empirically against the live tenant):

  - Foundry auto-camelCases every property when generating the action
    parameters (e.g. `display_name` → `displayName`, `created_at` →
    `createdAt`).
  - The PK is **not** auto-included as a parameter; it must be added by
    hand. We typed PK API names as camelCase for Mission / Artifact /
    DetectionResult (`missionId`, `artifactId`, `resultId`).
  - Channel was built first, before the convention was clear; its PK is
    snake-case `channel_id`. We accept the inconsistency and special-case
    it in `_to_camel_param()` below.

  - All non-PK parameters are camelCase across all 4 types.

Foundry also marks every parameter as required by default. The bridge always
passes empty string / null for "optional" fields rather than omitting them.

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
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

LOG = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Plan types
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class MissionUpsert:
    mission_id: str
    operator: str
    status: str                         # draft | pending_approval | executing | completed | failed | aborted
    target_channel_id: str
    audience_profile: str
    artifact_prompt: str
    dry_run: bool
    dispatched_at: str | None
    created_at: str
    finished_at: str | None
    failure_code: str
    provenance_pass_rate: float
    persona_archetype: str
    persona_name_seed: str
    stages_json: str                    # full stages array as JSON


@dataclass
class ArtifactUpsert:
    artifact_id: str
    mission_id: str
    prompt: str
    final_path: str
    final_sha256: str
    passed_c2pa: bool
    passed_titan: bool
    passed_synthid: bool
    passed_all: bool
    final_provenance_json: str
    created_at: str


@dataclass
class DetectionResultUpsert:
    result_id: str
    artifact_id: str
    detector: str                       # c2pa | titan | synthid
    passed: bool
    run_status: str                     # ok | skipped | error | manifest_not_found
    raw_response: str
    checked_at: str


@dataclass
class HydrationPlan:
    mission: MissionUpsert
    artifact: ArtifactUpsert | None
    detection_results: list[DetectionResultUpsert] = field(default_factory=list)

    def __str__(self) -> str:
        return (
            f"HydrationPlan(mission={self.mission.mission_id} status={self.mission.status}, "
            f"artifact={'yes' if self.artifact else 'no'}, detections={len(self.detection_results)})"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Parsing — pure
# ──────────────────────────────────────────────────────────────────────────────


# Engine's long detector keys → Ontology's short detector enum values.
_DETECTOR_KEY_MAP = {
    "c2pa": "c2pa",
    "titan_watermark": "titan",
    "google_synthid": "synthid",
}


def _stage_by_name(stages: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    matches = [s for s in stages if s.get("stage") == name]
    return matches[-1] if matches else None


def _passed_map(provenance_check_stage: dict[str, Any] | None) -> dict[str, Any]:
    if not provenance_check_stage:
        return {"per_detector": {}, "all_passed": False}
    return provenance_check_stage.get("detail", {}).get("passed", {})


def _detector_run_status(report: dict[str, Any], engine_key: str) -> str:
    section = (report or {}).get(engine_key) or {}
    status = section.get("status")
    if status in ("ok", "skipped", "error", "manifest_not_found"):
        return status
    return "error"


def _summarize_stage(stage: dict[str, Any]) -> str | None:
    """One-line operator-readable summary for a stage row, embedded in stagesJson."""
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_result(result: dict[str, Any]) -> HydrationPlan:
    """Convert an engine result dict into a HydrationPlan. Pure, no SDK calls."""
    mission_id = result["mission_id"]
    status = result.get("status", "completed")
    stages_raw = result.get("stages") or []
    spec = result.get("spec") or {}
    final_report = result.get("final_provenance_report") or {}
    error = result.get("error") or {}

    # Augment each stage with a human summary (so Workshop can render it from
    # stages_json without re-running summarization client-side).
    augmented_stages = []
    for s in stages_raw:
        out = dict(s)
        summ = _summarize_stage(s)
        if summ:
            out["summary"] = summ
        augmented_stages.append(out)

    persona_stage = _stage_by_name(stages_raw, "persona_generated") or {}
    persona_detail = persona_stage.get("detail") or {}
    spec_persona = spec.get("persona") or {}
    spec_target = spec.get("target") or {}
    spec_artifact = spec.get("artifact") or {}
    spec_delivery = spec.get("delivery") or {}

    target_channel_display = spec_target.get("channel", "")
    target_channel_id = target_channel_display.lstrip("@").replace("-", "_")

    prov_stage = _stage_by_name(stages_raw, "provenance_check")
    passed = _passed_map(prov_stage)

    mission = MissionUpsert(
        mission_id=mission_id,
        operator=result.get("operator", spec.get("operator", "")),
        status=status,
        target_channel_id=target_channel_id,
        audience_profile=spec_target.get("audience_profile", ""),
        artifact_prompt=spec_artifact.get("prompt", ""),
        dry_run=bool(spec_delivery.get("dry_run", True)),
        dispatched_at=result.get("started_at"),  # bridge will overwrite with true dispatch ts
        created_at=result.get("started_at") or _now_iso(),
        finished_at=result.get("finished_at"),
        failure_code=error.get("code", "") if status == "failed" else "",
        provenance_pass_rate=1.0 if passed.get("all_passed") else 0.0,
        persona_archetype=persona_detail.get("archetype", spec_persona.get("archetype", "")),
        persona_name_seed=persona_detail.get("name_seed", spec_persona.get("name_seed", "")),
        stages_json=json.dumps(augmented_stages, ensure_ascii=False),
    )

    # ── Artifact (only if a final artifact was produced) ──
    artifact: ArtifactUpsert | None = None
    detections: list[DetectionResultUpsert] = []
    final_path = result.get("final_artifact_path")
    final_sha = (final_report.get("meta") or {}).get("sha256")
    if final_path and final_sha:
        per = passed.get("per_detector", {})
        artifact_id = f"{mission_id}-clean"
        artifact = ArtifactUpsert(
            artifact_id=artifact_id,
            mission_id=mission_id,
            prompt=spec_artifact.get("prompt", ""),
            final_path=final_path,
            final_sha256=final_sha,
            passed_c2pa=bool(per.get("c2pa", False)),
            passed_titan=bool(per.get("titan", False)),
            passed_synthid=bool(per.get("synthid", False)),
            passed_all=bool(passed.get("all_passed", False)),
            final_provenance_json=json.dumps(final_report, ensure_ascii=False),
            created_at=(prov_stage.get("ts") if prov_stage else None) or result.get("finished_at") or _now_iso(),
        )

        for engine_key, short_name in _DETECTOR_KEY_MAP.items():
            section = final_report.get(engine_key) or {}
            detections.append(DetectionResultUpsert(
                result_id=f"{artifact_id}:{short_name}",
                artifact_id=artifact_id,
                detector=short_name,
                passed=bool(per.get(short_name, False)),
                run_status=_detector_run_status(final_report, engine_key),
                raw_response=json.dumps(section, ensure_ascii=False),
                checked_at=(prov_stage.get("ts") if prov_stage else None) or _now_iso(),
            ))

    return HydrationPlan(mission=mission, artifact=artifact, detection_results=detections)


# ──────────────────────────────────────────────────────────────────────────────
# Param naming — snake → camel with the one Channel exception
# ──────────────────────────────────────────────────────────────────────────────


# Properties whose Foundry parameter API name is NOT camelCased — for these we
# pass the literal snake_case key. Every other field gets camelCased.
_SNAKE_PARAM_OVERRIDES = {
    "Channel": {"channel_id"},
}


def _snake_to_camel(s: str) -> str:
    """snake_case → camelCase. Capitalizes only the first letter of each
    segment, leaving the rest unchanged (so `passed_c2pa` → `passedC2pa`,
    not `passedC2Pa` from str.title())."""
    parts = s.split("_")
    return parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:])


def _params_for(type_name: str, snake_dict: dict[str, Any]) -> dict[str, Any]:
    overrides = _SNAKE_PARAM_OVERRIDES.get(type_name, set())
    out: dict[str, Any] = {}
    for k, v in snake_dict.items():
        if k in overrides:
            out[k] = v
        else:
            out[_snake_to_camel(k)] = v
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Apply — the SDK side
# ──────────────────────────────────────────────────────────────────────────────


def _to_dict(d: Any) -> dict[str, Any]:
    """asdict() variant that also coerces None timestamps to empty string for the
    'every parameter required' Foundry default."""
    from dataclasses import asdict
    out = asdict(d)
    return {k: ("" if v is None else v) for k, v in out.items()}


def _apply_one(
    client: Any, ontology_rid: str, type_name: str, action_kebab: str, snake_dict: dict[str, Any],
    sync_retries: int = 8, sync_backoff_s: float = 10.0,
) -> bool:
    """Call create-<type> (or edit-<type>) with retry-on-syncing.

    Returns True on success (validation=VALID and operation_id present).
    """
    params = _params_for(type_name, snake_dict)
    last_err: Exception | None = None
    for attempt in range(sync_retries):
        try:
            result = client.ontologies.Action.apply(
                ontology=ontology_rid, action=action_kebab, parameters=params,
            )
            if result.validation and result.validation.result == "VALID" and result.operation_id:
                LOG.info("applied %s pk=%s", action_kebab, _pk_value(snake_dict))
                return True
            if result.validation and result.validation.result == "INVALID":
                bad = [k for k, v in result.validation.parameters.items() if v.result == "INVALID"]
                LOG.error("validation failed for %s pk=%s: %s", action_kebab, _pk_value(snake_dict), bad)
                return False
        except Exception as e:
            msg = str(e)
            last_err = e
            if "NotSynced" in msg or "Syncing" in msg:
                LOG.debug("ontology still syncing for %s, retrying in %.1fs", action_kebab, sync_backoff_s)
                time.sleep(sync_backoff_s)
                continue
            LOG.error("action %s failed for pk=%s: %s", action_kebab, _pk_value(snake_dict), msg[:200])
            return False
    LOG.error("action %s never succeeded after %d sync retries: %s", action_kebab, sync_retries, last_err)
    return False


def _pk_value(snake_dict: dict[str, Any]) -> str:
    for k in ("mission_id", "artifact_id", "result_id", "channel_id"):
        if k in snake_dict:
            return str(snake_dict[k])
    return "?"


def _upsert(client: Any, ontology_rid: str, type_name: str, snake_dict: dict[str, Any]) -> None:
    """Try create first, fall back to edit on conflict.

    The auto-generated Edit action's parameter list is a *subset* of Create's
    (PK + same body fields), so re-using the same dict works.
    """
    type_kebab = _to_kebab(type_name)
    if _apply_one(client, ontology_rid, type_name, f"create-{type_kebab}", snake_dict):
        return
    # If create failed, try edit (row may already exist).
    if _apply_one(client, ontology_rid, type_name, f"edit-{type_kebab}", snake_dict):
        return
    LOG.error("upsert failed for %s pk=%s — both create and edit declined", type_name, _pk_value(snake_dict))


def _to_kebab(type_name: str) -> str:
    out: list[str] = []
    for i, ch in enumerate(type_name):
        if ch.isupper() and i > 0:
            out.append("-")
        out.append(ch.lower())
    return "".join(out)


def apply_plan(plan: HydrationPlan, client: Any, ontology_rid: str) -> None:
    # Mission first — Artifact and DetectionResult reference it.
    _upsert(client, ontology_rid, "Mission", _to_dict(plan.mission))

    if plan.artifact:
        _upsert(client, ontology_rid, "Artifact", _to_dict(plan.artifact))

    for dr in plan.detection_results:
        _upsert(client, ontology_rid, "DetectionResult", _to_dict(dr))


# ──────────────────────────────────────────────────────────────────────────────
# Public entry
# ──────────────────────────────────────────────────────────────────────────────


def hydrate(result_dict: dict[str, Any], client: Any, ontology_rid: str) -> HydrationPlan:
    plan = parse_result(result_dict)
    LOG.info("hydrating: %s", plan)
    apply_plan(plan, client, ontology_rid)
    return plan


# ──────────────────────────────────────────────────────────────────────────────
# Smoke test (parser only — no SDK calls)
# ──────────────────────────────────────────────────────────────────────────────


if __name__ == "__main__":  # pragma: no cover
    import sys
    if len(sys.argv) != 2:
        sys.exit("usage: result_ingester.py <result.json>")
    with open(sys.argv[1]) as f:
        result = json.load(f)
    plan = parse_result(result)
    print(plan)
    print()
    print("Mission upsert payload (camelCase params):")
    for k, v in _params_for("Mission", _to_dict(plan.mission)).items():
        s = str(v)
        if len(s) > 60:
            s = s[:57] + "..."
        print(f"  {k} = {s}")
    if plan.artifact:
        print()
        print("Artifact upsert (camelCase params):")
        for k, v in _params_for("Artifact", _to_dict(plan.artifact)).items():
            s = str(v)
            if len(s) > 60:
                s = s[:57] + "..."
            print(f"  {k} = {s}")
    print()
    print(f"DetectionResult rows: {len(plan.detection_results)}")
