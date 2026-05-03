"""Read and summarize C2PA / Content Credentials from image bytes."""

from __future__ import annotations

import io
import json
from typing import Any

import c2pa


def _summarize_manifest_store(store: dict[str, Any]) -> dict[str, Any]:
    """Pick user-facing fields from Reader.json() output."""
    active = store.get("active_manifest")
    manifests = store.get("manifests") or {}
    active_manifest = manifests.get(active) if active else None

    claim_generators: list[dict[str, Any]] = []
    actions_summary: list[dict[str, Any]] = []

    if isinstance(active_manifest, dict):
        claim_gen = active_manifest.get("claim_generator_info")
        if isinstance(claim_gen, list):
            for cg in claim_gen:
                if isinstance(cg, dict):
                    claim_generators.append(
                        {
                            "name": cg.get("name"),
                            "version": cg.get("version"),
                        }
                    )

        for assertion in active_manifest.get("assertions") or []:
            if not isinstance(assertion, dict):
                continue
            label = assertion.get("label")
            if label == "c2pa.actions":
                data = assertion.get("data") or {}
                actions = data.get("actions") if isinstance(data, dict) else None
                if isinstance(actions, list):
                    for act in actions:
                        if not isinstance(act, dict):
                            continue
                        actions_summary.append(
                            {
                                "action": act.get("action"),
                                "digitalSourceType": act.get("digitalSourceType"),
                                "softwareAgent": act.get("softwareAgent"),
                            }
                        )

    return {
        "active_manifest_label": active,
        "claim_generator_info": claim_generators,
        "actions": actions_summary,
    }


def read_c2pa(mime_type: str, image_bytes: bytes) -> dict[str, Any]:
    """
    Return a structured report for C2PA in this asset.

    On success, includes raw manifest store JSON and a short summary.
    When no manifest is embedded, returns status manifest_not_found.
    """
    stream = io.BytesIO(image_bytes)
    try:
        with c2pa.Reader(mime_type, stream) as reader:
            raw = json.loads(reader.json())
    except c2pa.C2paError.ManifestNotFound:
        return {
            "status": "manifest_not_found",
            "detail": "No C2PA JUMBF data in this file (missing does not prove camera/original).",
        }
    except c2pa.C2paError as e:
        return {
            "status": "error",
            "error_type": type(e).__name__,
            "detail": str(e),
        }

    validation_state = None
    if isinstance(raw, dict):
        validation_state = raw.get("validation_state") or raw.get("validationState")

    summary = {}
    if isinstance(raw, dict):
        summary = _summarize_manifest_store(raw)

    return {
        "status": "ok",
        "validation_state": validation_state,
        "summary": summary,
        "manifest_store": raw,
    }
