"""C2PA / Content-Credentials detector. Wraps src/mendacity/c2pa_report.

A "valid" C2PA manifest is not the same as a "human-attested" manifest —
generative AI providers (OpenAI, Google, Adobe Firefly, Stability) sign
their outputs with valid C2PA manifests that *declare* AI generation via
the IPTC ``digitalSourceType`` codes or via the ``softwareAgent`` name on
the ``c2pa.created`` action. We treat those as decisive evidence of
synthesis (severity ``fail``), not as a positive provenance signal.
"""
from __future__ import annotations

import time
from typing import Any

from mendacity.c2pa_report import read_c2pa  # read-only import

from defensive.engine.verdict import DetectorSignal, Severity

NAME = "c2pa"

# IPTC digitalSourceType URIs that indicate an AI generative source.
# https://cv.iptc.org/newscodes/digitalsourcetype/
_AI_DIGITAL_SOURCE_TYPES = {
    "http://cv.iptc.org/newscodes/digitalsourcetype/trainedalgorithmicmedia",
    "http://cv.iptc.org/newscodes/digitalsourcetype/compositewithtrainedalgorithmicmedia",
    "http://cv.iptc.org/newscodes/digitalsourcetype/algorithmicmedia",
    "http://cv.iptc.org/newscodes/digitalsourcetype/digitalcapture",  # not AI but kept commented
}
# digitalcapture is a real-camera signal — not in the AI set. Listed only
# above for clarity; the detector treats anything not in the AI set as
# pass-eligible.
_AI_DIGITAL_SOURCE_TYPES.discard(
    "http://cv.iptc.org/newscodes/digitalsourcetype/digitalcapture"
)

# Substrings (case-insensitive) of claim_generator / softwareAgent names that
# identify known AI image producers. Match is conservative — keep this list
# tight; expanding it widens the false-positive surface on legit creative
# tools that happen to embed these substrings.
_AI_PRODUCER_SUBSTRINGS = (
    "openai",
    "gpt-image",
    "dall-e",
    "dalle",
    "google",
    "gemini",
    "imagen",
    "stability",
    "stable diffusion",
    "midjourney",
    "firefly",  # Adobe Firefly
    "runway",
    "flux",  # Black Forest Labs FLUX
    "ideogram",
    "leonardo",
    "luma",
)


def _ai_evidence(report: dict[str, Any]) -> str | None:
    """Inspect a parsed C2PA report and return an evidence string if it
    declares AI generation, else None."""
    summary = report.get("summary") or {}
    store = report.get("manifest_store") or {}
    active = store.get("active_manifest") or summary.get("active_manifest_label")
    manifests = store.get("manifests") or {}
    manifest = manifests.get(active) or {}

    # 1. claim_generator_info names — top-level summary or in the manifest.
    generators: list[str] = []
    for source in (summary.get("claim_generator_info") or []), (manifest.get("claim_generator_info") or []):
        for entry in source:
            name = (entry or {}).get("name")
            if isinstance(name, str):
                generators.append(name)
    for g in generators:
        gl = g.lower()
        for needle in _AI_PRODUCER_SUBSTRINGS:
            if needle in gl:
                return f"AI producer in C2PA manifest: {g}"

    # 2. assertions — c2pa.actions / c2pa.actions.v2 with digitalSourceType
    #    or softwareAgent matching an AI tool.
    for assertion in manifest.get("assertions") or []:
        label = (assertion.get("label") or "").lower()
        if not label.startswith("c2pa.actions"):
            continue
        actions = (assertion.get("data") or {}).get("actions") or []
        for action in actions:
            dst = (action.get("digitalSourceType") or "").lower()
            if dst in _AI_DIGITAL_SOURCE_TYPES:
                return f"C2PA action declares AI source: {dst.rsplit('/', 1)[-1]}"
            sa = action.get("softwareAgent")
            sa_name = sa.get("name") if isinstance(sa, dict) else sa
            if isinstance(sa_name, str):
                sl = sa_name.lower()
                for needle in _AI_PRODUCER_SUBSTRINGS:
                    if needle in sl:
                        return f"C2PA action softwareAgent is AI producer: {sa_name}"
    return None


def run(image_bytes: bytes, *, mime_type: str = "image/jpeg") -> DetectorSignal:
    """Severity:
      pass — valid manifest from a non-AI producer (legitimate provenance)
      na   — manifest absent (the norm; absence is not evidence)
      fail — manifest validation failed, OR manifest declares AI generation
    """
    started = time.monotonic()
    report = read_c2pa(mime_type, image_bytes)
    elapsed_ms = int((time.monotonic() - started) * 1000)

    status = report.get("status")
    if status == "manifest_not_found":
        return DetectorSignal(
            detector=NAME, severity=Severity.na, score=None,
            evidence="no manifest", latency_ms=elapsed_ms,
        )
    if status == "error":
        return DetectorSignal(
            detector=NAME, severity=Severity.na, score=None,
            evidence=f"reader error: {report.get('error_type', 'unknown')}",
            latency_ms=elapsed_ms,
        )

    validation = (report.get("validation_state") or "").lower()
    if validation and validation != "valid":
        return DetectorSignal(
            detector=NAME, severity=Severity.fail, score=None,
            evidence=f"validation_state={validation}", latency_ms=elapsed_ms,
        )

    ai_evidence = _ai_evidence(report)
    if ai_evidence:
        return DetectorSignal(
            detector=NAME, severity=Severity.fail, score=None,
            evidence=ai_evidence, latency_ms=elapsed_ms,
        )

    return DetectorSignal(
        detector=NAME, severity=Severity.pass_, score=None,
        evidence="manifest valid (non-AI producer)", latency_ms=elapsed_ms,
    )
