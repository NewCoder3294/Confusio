"""ProvenanceGrader — turns a structured provenance report into operator prose.

Called from the Workshop "Mission Detail" view to render a one-paragraph
natural-language summary of whether the artifact would survive an adversary's
detection stack. Cited in the demo segment when the operator points at a
completed mission.

This is a deterministic templating function, not an LLM call. Reasons:

  1. We need stable output during the live demo — no completion drift.
  2. The audit story benefits from a function whose output is reproducible
     given the same input. "Why did this say PASS?" must be answerable
     from the input alone.
  3. It's faster — Workshop renders the summary inline.

If a future version wants LLM-authored copy, swap `summarize_artifact()` for
an AIP Logic call that takes the same input and returns a string.

Reads from the engine's existing `final_provenance_report` shape — no schema
changes required on the engine side. See `PALANTIR_REQUESTS.md §3` for the
shape this expects.

Usage from a Foundry Function:

    from provenance_grader import summarize_artifact, summarize_mission_status_line

    summary = summarize_artifact(artifact_obj)   # full paragraph
    pill    = summarize_mission_status_line(...) # 1-line tile copy

Both are pure; both are unit-testable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class ArtifactInput:
    """Shape the grader actually consumes — independent of how Foundry hands
    it over.

    `final_provenance_report` is the inline JSON the engine emits. This dataclass
    accepts it as either a dict (already parsed) or a JSON string.
    """
    artifact_id: str
    prompt: str
    final_path: str
    watermark_stripped: bool
    exif_transplanted: bool
    passed_c2pa: bool
    passed_titan: bool
    passed_synthid: bool
    passed_all: bool
    final_provenance_report: dict[str, Any]

    @classmethod
    def from_ontology_object(cls, obj: dict[str, Any]) -> "ArtifactInput":
        report = obj.get("final_provenance_json") or obj.get("final_provenance_report") or {}
        if isinstance(report, str):
            try:
                report = json.loads(report)
            except json.JSONDecodeError:
                report = {}
        return cls(
            artifact_id=obj["artifact_id"],
            prompt=obj.get("prompt", ""),
            final_path=obj.get("final_path", ""),
            watermark_stripped=bool(obj.get("watermark_stripped", False)),
            exif_transplanted=bool(obj.get("exif_transplanted", False)),
            passed_c2pa=bool(obj.get("passed_c2pa", False)),
            passed_titan=bool(obj.get("passed_titan", False)),
            passed_synthid=bool(obj.get("passed_synthid", False)),
            passed_all=bool(obj.get("passed_all", False)),
            final_provenance_report=report,
        )


def summarize_artifact(artifact: ArtifactInput) -> str:
    """Return a one-paragraph operator-readable summary, 60–120 words.

    Voice: sober, procedural, doctrine-aligned. No marketing copy. Do not
    say "successfully" — the artifact either survived or it didn't, and the
    operator does not need to be congratulated.
    """
    detector_lines = [
        _format_detector_line(
            "Content Credentials (C2PA)",
            artifact.passed_c2pa,
            artifact.final_provenance_report.get("c2pa") or {},
        ),
        _format_detector_line(
            "Amazon Titan watermark",
            artifact.passed_titan,
            artifact.final_provenance_report.get("titan_watermark") or {},
        ),
        _format_detector_line(
            "Google SynthID",
            artifact.passed_synthid,
            artifact.final_provenance_report.get("google_synthid") or {},
        ),
    ]

    treatment_phrase = _treatment_phrase(artifact.watermark_stripped, artifact.exif_transplanted)

    if artifact.passed_all:
        verdict_phrase = (
            "would not be flagged by any of the three provenance layers an adversary "
            "is likely to deploy"
        )
        outlook_phrase = (
            "Suitable for delivery on the targeted channel. Operator should still "
            "verify that the caption and posting cadence match the persona's prior "
            "behavior; provenance pass is necessary, not sufficient."
        )
    elif _none_passed(artifact):
        verdict_phrase = (
            "would be flagged by every provenance layer the adversary's vetting pipeline "
            "is expected to run"
        )
        outlook_phrase = (
            "Do not deliver. Regenerate the artifact, re-strip, and re-grade before "
            "considering this mission ready."
        )
    else:
        failed = [d for d, ok in [
            ("C2PA", artifact.passed_c2pa),
            ("Titan", artifact.passed_titan),
            ("SynthID", artifact.passed_synthid),
        ] if not ok]
        verdict_phrase = (
            f"would survive most provenance checks but is flagged by "
            f"{_human_join(failed)}"
        )
        outlook_phrase = (
            "Holding for operator review. The flagged layer is a credible failure mode "
            "if the adversary's pipeline includes it; consider re-running the strip stage "
            "or selecting a different source artifact."
        )

    paragraph = (
        f"Artifact {artifact.artifact_id} {treatment_phrase} {verdict_phrase}. "
        + " ".join(detector_lines).strip()
        + " "
        + outlook_phrase
    )
    # Collapse any double spaces from optional blocks.
    return " ".join(paragraph.split())


def summarize_mission_status_line(
    status: str,
    provenance_pass_rate: float | None,
    failure_code: str | None = None,
) -> str:
    """One-line copy for the Mission Board status pill / row caption."""
    if status == "completed":
        if provenance_pass_rate is None:
            return "Completed (no artifacts graded)"
        if provenance_pass_rate >= 0.999:
            return "Completed — all artifacts cleared adversary detection"
        if provenance_pass_rate <= 0.001:
            return "Completed — but every artifact was flagged. Review before further runs."
        return f"Completed — {provenance_pass_rate*100:.0f}% of artifacts cleared adversary detection"
    if status == "failed":
        if failure_code:
            return f"Failed: {_humanize_failure_code(failure_code)}"
        return "Failed (cause unspecified)"
    if status == "aborted":
        return "Aborted by operator"
    if status == "executing":
        return "Executing — engine is working the artifact"
    if status == "pending_approval":
        return "Pending operator approval"
    if status == "draft":
        return "Draft — not yet approved"
    return status.capitalize()


# ──────────────────────────────────────────────────────────────────────────────
# Internals
# ──────────────────────────────────────────────────────────────────────────────


def _format_detector_line(
    name: str,
    passed: bool,
    section: dict[str, Any],
) -> str:
    """Render one sentence per detector, citing what the detector actually said."""
    status = (section or {}).get("status")
    if passed and status == "skipped":
        # Important: a 'skipped' run with passed=true is "we didn't actually
        # check, so we're assuming clean." Flag this in the prose.
        return f"{name}: not run during this grade — assumed clean."
    if passed and status == "ok":
        # Cite the cleanest piece of evidence.
        if section.get("watermark_verification_result"):
            return f"{name}: {section['watermark_verification_result']}."
        if section.get("detectionResult"):
            return f"{name}: {section['detectionResult']}."
        if (section.get("status") == "manifest_not_found"):
            return f"{name}: no manifest detected (consistent with a non-watermarked image)."
        return f"{name}: clean."
    if passed and status == "manifest_not_found":
        return f"{name}: no manifest detected (consistent with a non-watermarked image)."
    if not passed and status == "ok":
        if section.get("watermark_verification_result"):
            return f"{name}: FLAGGED — verifier returned {section['watermark_verification_result']}."
        if section.get("detectionResult"):
            return f"{name}: FLAGGED — detector returned {section['detectionResult']}."
        return f"{name}: flagged by the detector."
    if not passed and status == "error":
        return f"{name}: detector errored — treat as inconclusive."
    return f"{name}: {'passed' if passed else 'flagged'} ({status or 'unknown'})."


def _treatment_phrase(watermark_stripped: bool, exif_transplanted: bool) -> str:
    if watermark_stripped and exif_transplanted:
        return "(watermark-stripped and EXIF-transplanted)"
    if watermark_stripped:
        return "(watermark-stripped, no EXIF transplant)"
    if exif_transplanted:
        return "(EXIF-transplanted, no watermark strip)"
    return "(unmodified)"


def _none_passed(a: ArtifactInput) -> bool:
    return not (a.passed_c2pa or a.passed_titan or a.passed_synthid)


def _human_join(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


_FAILURE_LEXICON = {
    "validation_failed": "spec failed validation",
    "channel_not_authorized": "target channel not on the sandbox allowlist",
    "artifact_source_missing": "source fixture not found",
    "generation_failed": "image generation crashed",
    "provenance_check_error": "provenance check raised",
    "regen_budget_exhausted": "regeneration budget exhausted",
    "watermark_strip_failed": "watermark strip exited non-zero",
    "delivery_failed": "Telegram delivery failed",
    "engine_timeout": "engine produced no result before the timeout",
    "internal_error": "internal engine error",
}


def _humanize_failure_code(code: str) -> str:
    return _FAILURE_LEXICON.get(code, code.replace("_", " "))


# ──────────────────────────────────────────────────────────────────────────────
# Smoke test
# ──────────────────────────────────────────────────────────────────────────────


if __name__ == "__main__":  # pragma: no cover
    import sys
    if len(sys.argv) != 2:
        sys.exit("usage: provenance_grader.py <result.json>")
    with open(sys.argv[1]) as f:
        result = json.load(f)

    # Reconstruct an ArtifactInput from a result file directly.
    final_report = result["final_provenance_report"] or {}
    pchk = next(
        (s for s in (result.get("stages") or []) if s.get("stage") == "provenance_check"),
        {},
    )
    passed = (pchk.get("detail") or {}).get("passed") or {}
    per = passed.get("per_detector") or {}

    artifact = ArtifactInput(
        artifact_id=f"{result['mission_id']}-clean",
        prompt=(result.get("spec") or {}).get("artifact", {}).get("prompt", ""),
        final_path=result.get("final_artifact_path", ""),
        watermark_stripped=any(
            s.get("stage") == "watermark_strip" and s.get("status") == "ok"
            for s in (result.get("stages") or [])
        ),
        exif_transplanted=any(
            s.get("stage") == "exif_transplant" and s.get("status") == "ok"
            for s in (result.get("stages") or [])
        ),
        passed_c2pa=bool(per.get("c2pa", False)),
        passed_titan=bool(per.get("titan", False)),
        passed_synthid=bool(per.get("synthid", False)),
        passed_all=bool(passed.get("all_passed", False)),
        final_provenance_report=final_report,
    )

    print("─── Artifact summary ───")
    print(summarize_artifact(artifact))
    print()
    print("─── Mission status line ───")
    print(summarize_mission_status_line(
        result.get("status", "completed"),
        1.0 if passed.get("all_passed") else 0.0,
        (result.get("error") or {}).get("code"),
    ))
