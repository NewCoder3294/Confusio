"""
Defensive triage CLI for the Intel Inbox.

Inverts the same instruments the offensive arm uses to grade itself, and
points them at a *suspect inbound* image instead. Returns one JSON document
combining provenance detectors (C2PA / Titan / SynthID), the spectral-surrogate
AI classifier (forensic.laundering.selfcheck), EXIF anomaly summary, and a
composite verdict.

Usage:
    python -m forensic.triage --image /path/to/suspect.jpg

Output (stdout, JSON):
    {
        "meta": {...},
        "provenance": {...},          # analyze_image() output
        "ai_surrogate": {...},        # spectral / sdxl-detector verdict
        "exif_anomalies": [...],
        "verdict": {
            "label": "SUSPECTED_SYNTHETIC" | "INCONCLUSIVE" | "SUSPECTED_AUTHENTIC",
            "confidence": "high" | "medium" | "low",
            "drivers": [...]          # short strings explaining the call
        }
    }
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Make src/mendacity importable when run from repo root via -m
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


_AI_GENERATOR_KEYWORDS = (
    "dall-e", "dalle", "openai",
    "midjourney",
    "stable diffusion", "stability", "sdxl",
    "gemini", "imagen",
    "firefly",
    "ideogram",
    "leonardo",
    "runway",
)

_SQUARE_AI_SIZES = {(1024, 1024), (512, 512), (768, 768), (2048, 2048), (1024, 1792), (1792, 1024)}


def _exif_summary(image_path: Path) -> dict[str, Any]:
    """Pull EXIF + flag synthetic-image fingerprints."""
    try:
        from PIL import Image, ExifTags
    except ImportError:
        return {"error": "Pillow not installed", "anomalies": [], "fields": {}}

    anomalies: list[str] = []
    fields: dict[str, Any] = {}

    try:
        with Image.open(image_path) as img:
            size = (img.width, img.height)
            fields["dimensions"] = f"{size[0]}x{size[1]}"
            if size in _SQUARE_AI_SIZES:
                anomalies.append(f"Dimensions {size[0]}x{size[1]} match a common AI generator output size.")

            raw_exif = img.getexif() or {}
            tag_lookup = {v: k for k, v in ExifTags.TAGS.items()}

            def get(name: str):
                tag = tag_lookup.get(name)
                return raw_exif.get(tag) if tag is not None else None

            software = get("Software")
            make = get("Make")
            model = get("Model")
            datetime_field = get("DateTime")

            if software:
                fields["software"] = str(software)
                low = str(software).lower()
                if any(k in low for k in _AI_GENERATOR_KEYWORDS):
                    anomalies.append(f"Software field declares an AI generator: {software!r}.")
            if make:
                fields["camera_make"] = str(make)
            if model:
                fields["camera_model"] = str(model)
            if datetime_field:
                fields["datetime"] = str(datetime_field)

            if not make and not model and not software:
                anomalies.append("EXIF has no Make, Model, or Software fields — unusual for any photo claiming a device origin.")

            # MakerNote presence (tag 37500)
            has_makernote = 37500 in raw_exif
            fields["has_makernote"] = has_makernote
            if (make or model) and not has_makernote:
                anomalies.append(f"EXIF claims {make or model!r} but contains no MakerNote — real device captures almost always include one.")
    except Exception as e:
        return {"error": f"EXIF read failed: {type(e).__name__}: {e}", "anomalies": [], "fields": {}}

    return {"fields": fields, "anomalies": anomalies}


def _composite_verdict(provenance: dict, surrogate: dict, anomalies: list[str]) -> dict[str, Any]:
    drivers: list[str] = []
    score = 0  # > 0 leans synthetic; < 0 leans authentic

    # C2PA manifest naming the generator is the strongest single signal.
    c2pa = provenance.get("c2pa") or {}
    if c2pa.get("status") == "ok":
        actions = ((c2pa.get("summary") or {}).get("claim_generator_info") or [])
        if actions:
            drivers.append(f"C2PA manifest present, claims generator: {actions}")
            score += 3
        else:
            drivers.append("C2PA manifest present (generator unspecified).")
            score += 1
    elif c2pa.get("status") == "manifest_not_found":
        drivers.append("No C2PA manifest (most images don't carry one — neutral signal).")

    # Spectral / sdxl surrogate.
    p_ai = surrogate.get("p_ai")
    if isinstance(p_ai, (int, float)):
        if p_ai >= 0.7:
            drivers.append(f"AI surrogate p(synthetic)={p_ai:.2f} (strong).")
            score += 3
        elif p_ai >= 0.5:
            drivers.append(f"AI surrogate p(synthetic)={p_ai:.2f} (moderate).")
            score += 1
        elif p_ai <= 0.2:
            drivers.append(f"AI surrogate p(synthetic)={p_ai:.2f} (low — leans authentic).")
            score -= 2
        else:
            drivers.append(f"AI surrogate p(synthetic)={p_ai:.2f} (inconclusive band).")

    # EXIF anomalies.
    if anomalies:
        for a in anomalies:
            drivers.append(a)
        # Each anomaly nudges the score; explicit AI-generator declaration is the heaviest.
        score += sum(3 if "AI generator" in a else 1 for a in anomalies)

    if score >= 4:
        label, confidence = "SUSPECTED_SYNTHETIC", "high"
    elif score >= 2:
        label, confidence = "SUSPECTED_SYNTHETIC", "medium"
    elif score <= -2:
        label, confidence = "SUSPECTED_AUTHENTIC", "medium"
    else:
        label, confidence = "INCONCLUSIVE", "low"

    return {"label": label, "confidence": confidence, "score": score, "drivers": drivers}


def triage(image_path: Path) -> dict[str, Any]:
    from mendacity.pipeline import analyze_image
    from forensic.laundering import selfcheck

    provenance = analyze_image(path=image_path)

    sur = selfcheck.detect(image_path, force_heuristic=True)
    surrogate = {
        "model": sur.model,
        "backend": sur.backend,
        "p_ai": sur.p_ai,
        "p_real": sur.p_real,
        "raw_label": sur.raw_label,
        "note": sur.note,
    }

    exif = _exif_summary(image_path)
    verdict = _composite_verdict(provenance, surrogate, exif.get("anomalies") or [])

    return {
        "meta": provenance.get("meta", {}),
        "provenance": provenance,
        "ai_surrogate": surrogate,
        "exif": exif,
        "verdict": verdict,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="forensic.triage")
    parser.add_argument("--image", required=True, type=Path)
    args = parser.parse_args(argv)

    if not args.image.is_file():
        json.dump({"error": f"file not found: {args.image}"}, sys.stdout)
        return 1

    result = triage(args.image)
    json.dump(result, sys.stdout, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
