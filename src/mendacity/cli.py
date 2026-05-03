"""CLI entrypoint."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from mendacity.pipeline import AnalyzeOptions, analyze_image


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Check image provenance: C2PA first; optional Amazon Titan watermark; "
            "optional Google SynthID via Vertex AI."
        )
    )
    parser.add_argument(
        "image",
        type=Path,
        help="Path to an image file (JPEG, PNG, WebP, …)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON report to stdout",
    )
    parser.add_argument(
        "--titan",
        action="store_true",
        help="Call Bedrock DetectGeneratedContent (needs AWS credentials)",
    )
    parser.add_argument(
        "--google",
        action="store_true",
        help="Call Vertex AI watermark verification (needs GCP + mendacity[google])",
    )
    args = parser.parse_args(argv)

    # Progress on stderr so JSON stdout stays machine-readable (avoids "silent" cloud calls).
    if args.titan:
        print("[mendacity] Running Amazon Titan watermark check…", file=sys.stderr, flush=True)
    if args.google:
        print("[mendacity] Running Google Vertex watermark check…", file=sys.stderr, flush=True)

    opts = AnalyzeOptions(run_titan=args.titan, run_google=args.google)
    report = analyze_image(path=args.image, options=opts)

    if args.json:
        print(json.dumps(report, indent=2), flush=True)
        return

    # Short human-readable summary
    print(f"File: {report['meta'].get('path', args.image)}", flush=True)
    print(f"SHA-256: {report['meta']['sha256']}")
    print(f"MIME (inferred): {report['meta']['mime_inferred']}")
    c2pa = report["c2pa"]
    print("\n[C2PA]")
    print(f"  status: {c2pa.get('status')}")
    if c2pa.get("status") == "ok":
        vs = c2pa.get("validation_state")
        if vs is not None:
            print(f"  validation_state: {vs}")
        s = c2pa.get("summary") or {}
        gens = s.get("claim_generator_info") or []
        if gens:
            print(f"  claim_generator_info: {gens}")
        acts = s.get("actions") or []
        if acts:
            print(f"  actions (sample): {acts[:5]}{' …' if len(acts) > 5 else ''}")
    elif c2pa.get("status") == "manifest_not_found":
        print("  (no Content Credentials embedded — this does not prove the image is “real”)")

    tw = report["titan_watermark"]
    print("\n[Titan watermark]")
    print(f"  status: {tw.get('status')}")
    if tw.get("status") == "ok":
        print(f"  detectionResult: {tw.get('detectionResult')}")
        print(f"  confidenceLevel: {tw.get('confidenceLevel')}")
    elif tw.get("status") == "skipped":
        print(f"  {tw.get('reason')}")

    gs = report["google_synthid"]
    print("\n[Google SynthID / Vertex watermark model]")
    print(f"  status: {gs.get('status')}")
    if gs.get("status") == "ok":
        print(f"  watermark_verification_result: {gs.get('watermark_verification_result')}")
    elif gs.get("status") == "skipped":
        print(f"  {gs.get('reason')}")
        gh = gs.get("gemini_upload_hint")
        if gh:
            print(f"  Try: {gh}")
    elif gs.get("status") == "error":
        print(f"  detail: {gs.get('detail')}")

    # Non-zero exit if any enabled check errored (optional)
    if tw.get("status") == "error" or gs.get("status") == "error":
        sys.exit(2)


if __name__ == "__main__":
    main()
