"""CLI entrypoint for ``mendacity-mission``.

Subcommands:
- ``run <spec.yaml>``  — execute one mission, write result to missions/results/
- ``watch``            — daemon: poll missions/inbox/, process new specs
- ``grade <result.json>`` — re-print pass/fail summary for a completed run
- ``audit <image>``    — before/after transform report for slide rendering
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from mendacity.audit import run_audit
from mendacity.mission import (
    MISSIONS_DIR,
    MissionSpec,
    execute_mission,
    watch_inbox,
    write_result,
)


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="[%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _print_summary(result_dict: dict) -> None:
    print(f"Mission:   {result_dict['mission_id']}")
    print(f"Operator:  {result_dict['operator']}")
    print(f"Status:    {result_dict['status'].upper()}")
    print(f"Started:   {result_dict['started_at']}")
    print(f"Finished:  {result_dict.get('finished_at')}")
    print()
    print("Stages:")
    for s in result_dict["stages"]:
        marker = {"ok": "[OK]", "skipped": "[--]", "error": "[!!]"}.get(
            s["status"], "[??]"
        )
        print(f"  {marker} {s['stage']:<22} {s['ts']}")

    print()
    prov_stage = next(
        (s for s in result_dict["stages"] if s["stage"] == "provenance_check"),
        None,
    )
    if prov_stage:
        passed = prov_stage["detail"].get("passed", {})
        per = passed.get("per_detector", {})
        report = prov_stage["detail"].get("report", {})
        all_passed = passed.get("all_passed")

        def _label(name: str, key_in_report: str) -> str:
            status = report.get(key_in_report, {}).get("status")
            # C2PA: 'manifest_not_found' IS the win condition (no embedded creds).
            if name == "c2pa":
                if status == "manifest_not_found":
                    return "PASS (no Content Credentials embedded)"
                if status == "ok":
                    return "FAIL (manifest present — would expose AI provenance)"
                return f"ERROR ({status})"
            # Cloud detectors: ok = ran, skipped = no creds (inconclusive).
            if status == "ok":
                return "PASS (verified)" if per.get(name) else "FAIL (verified)"
            if status == "skipped":
                return "PASS (skipped — no creds; inconclusive)" if per.get(name) else "FAIL"
            return f"ERROR ({status})"

        print("Provenance grading:")
        print(f"  C2PA     : {_label('c2pa',    'c2pa')}")
        print(f"  Titan    : {_label('titan',   'titan_watermark')}")
        print(f"  SynthID  : {_label('synthid', 'google_synthid')}")
        print(f"  --> {'ALL PASS — artifact ships' if all_passed else 'BLOCKED'}")
    err = result_dict.get("error")
    if err:
        print()
        if isinstance(err, dict):
            print(f"Error  [{err.get('code')}] at stage '{err.get('stage')}':")
            print(f"  {err.get('message')}")
        else:
            print(f"Error: {err}")


def _cmd_run(args: argparse.Namespace) -> int:
    spec_path = Path(args.spec)
    if not spec_path.exists():
        print(f"spec not found: {spec_path}", file=sys.stderr)
        return 2
    spec = MissionSpec.from_yaml_path(spec_path)
    result = execute_mission(
        spec, run_titan=args.titan, run_google=args.google
    )
    out = write_result(result)
    print(f"[mendacity-mission] result -> {out}", file=sys.stderr)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        _print_summary(result.to_dict())
    return 0 if result.status == "completed" else 1


def _cmd_watch(args: argparse.Namespace) -> int:
    watch_inbox(
        inbox=Path(args.inbox) if args.inbox else None,
        results_dir=Path(args.results) if args.results else None,
        poll_seconds=args.poll,
        run_titan=args.titan,
        run_google=args.google,
        once=args.once,
    )
    return 0


def _cmd_grade(args: argparse.Namespace) -> int:
    p = Path(args.result)
    if not p.exists():
        print(f"result not found: {p}", file=sys.stderr)
        return 2
    data = json.loads(p.read_text(encoding="utf-8"))
    _print_summary(data)
    return 0


def _cmd_audit(args: argparse.Namespace) -> int:
    img = Path(args.image)
    if not img.exists():
        print(f"image not found: {img}", file=sys.stderr)
        return 2
    template = Path(args.exif_template) if args.exif_template else None
    result = run_audit(
        img,
        exif_template=template,
        run_titan=args.titan,
        run_google=args.google,
    )
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
        return 0

    d = result.to_dict()
    print(f"Audit:    {d['audit_id']}")
    print(f"Started:  {d['started_at']}")
    print()
    inp, out = d["input"], d["output"]
    print(f"BEFORE  {inp['path']}")
    print(f"  sha256:  {inp['sha256']}")
    print(f"  mime:    {inp['mime']}")
    print(f"  size:    {inp['size_bytes']:>10} bytes")
    print(
        f"  exif:    make={inp['exif'].get('make')!r:<10} "
        f"model={inp['exif'].get('model')!r:<14} "
        f"software={inp['exif'].get('software')!r}"
    )
    print(f"  C2PA:    {d['provenance_before'].get('c2pa', {}).get('status')}")
    print()
    print(f"AFTER   {out['path']}")
    print(f"  sha256:  {out['sha256']}")
    print(f"  mime:    {out['mime']}")
    print(f"  size:    {out['size_bytes']:>10} bytes")
    print(
        f"  exif:    make={out['exif'].get('make')!r:<10} "
        f"model={out['exif'].get('model')!r:<14} "
        f"software={out['exif'].get('software')!r}"
    )
    print(f"  C2PA:    {d['provenance_after'].get('c2pa', {}).get('status')}")
    print()
    pix = d["transform"].get("pixel_diff", {})
    print(f"TRANSFORM")
    print(f"  pixels modified : {pix.get('pct_modified')}%")
    print(f"  mean RGB delta  : {pix.get('mean_delta')}")
    print(f"  EXIF template   : {d['transform'].get('exif_template')}")
    print(f"  SynthIDBye log  : {d['transform'].get('synthidbye_seed_log')[:120]}")
    print()
    print(f"COMPARISON IMAGE: {d.get('comparison_image_path')}")
    print()
    print(f"VERDICT: {d['verdict']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mendacity-mission",
        description="Run, watch, and grade Mendacity deception missions.",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="execute one MissionSpec YAML")
    p_run.add_argument("spec", help="path to mission YAML")
    p_run.add_argument("--titan", action="store_true", help="run Bedrock Titan check")
    p_run.add_argument("--google", action="store_true", help="run Vertex SynthID check")
    p_run.add_argument("--json", action="store_true", help="emit full result JSON")
    p_run.set_defaults(func=_cmd_run)

    p_watch = sub.add_parser("watch", help="poll inbox, execute new specs")
    p_watch.add_argument("--inbox", help=f"inbox dir (default: {MISSIONS_DIR / 'inbox'})")
    p_watch.add_argument("--results", help=f"results dir (default: {MISSIONS_DIR / 'results'})")
    p_watch.add_argument("--poll", type=float, default=1.0)
    p_watch.add_argument("--titan", action="store_true")
    p_watch.add_argument("--google", action="store_true")
    p_watch.add_argument("--once", action="store_true", help="single sweep, then exit")
    p_watch.set_defaults(func=_cmd_watch)

    p_grade = sub.add_parser("grade", help="print summary of a completed result JSON")
    p_grade.add_argument("result", help="path to result JSON")
    p_grade.set_defaults(func=_cmd_grade)

    p_audit = sub.add_parser(
        "audit", help="before/after transform report on a single image"
    )
    p_audit.add_argument("image", help="path to input image (PNG or JPEG)")
    p_audit.add_argument(
        "--exif-template",
        help="path to EXIF JSON template (default: fixtures/koze_iphonex_gist.json)",
    )
    p_audit.add_argument("--titan", action="store_true")
    p_audit.add_argument("--google", action="store_true")
    p_audit.add_argument("--json", action="store_true", help="emit full audit JSON")
    p_audit.set_defaults(func=_cmd_audit)

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
