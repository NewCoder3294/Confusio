"""CLI entrypoint for ``mendacity-mission``.

Subcommands:
- ``run <spec.yaml>``  — execute one mission, write result to missions/results/
- ``watch``            — daemon: poll missions/inbox/, process new specs
- ``grade <result.json>`` — re-print pass/fail summary for a completed run
- ``audit <image>``    — before/after transform report for slide rendering
- ``plan "<intent>"``  — operator intent → MissionSpec YAML (LLM planner)
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
from mendacity.mission_planner import (
    PlannerError,
    match_archetype_to_persona,
    plan_mission_yaml,
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
        workers=args.workers,
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
    print("TRANSFORM")
    print(f"  pixels modified : {pix.get('pct_modified')}%")
    print(f"  mean RGB delta  : {pix.get('mean_delta')}")
    print(f"  EXIF template   : {d['transform'].get('exif_template')}")
    print(f"  SynthIDBye log  : {d['transform'].get('synthidbye_seed_log')[:120]}")
    print()
    print(f"COMPARISON IMAGE: {d.get('comparison_image_path')}")
    print()
    print(f"VERDICT: {d['verdict']}")
    return 0


def _cmd_personas(args: argparse.Namespace) -> int:
    """Show all personas with their session auth status."""
    if str(MISSIONS_DIR.parent) not in sys.path:
        sys.path.insert(0, str(MISSIONS_DIR.parent))
    try:
        from social.personas import load_personas
        from social.telegram_client import (
            PersonaTelegramClient,
            SessionExpiredError,
            TelegramError,
        )
    except Exception as exc:
        print(f"social/ stack not importable: {exc}", file=sys.stderr)
        return 2

    personas_dir = MISSIONS_DIR.parent / "social" / "personas"
    try:
        personas = load_personas(personas_dir=personas_dir, require_sessions=False)
    except Exception as exc:
        print(f"persona load failed: {exc}", file=sys.stderr)
        return 2

    if not personas:
        print("(no personas found)")
        return 0

    import asyncio

    async def _probe_one(p) -> str:
        sp = p.resolved_session_path()
        if not sp.exists():
            return "no-session-file"
        client = PersonaTelegramClient(sp)
        try:
            await client.start()
            return "AUTHORIZED"
        except SessionExpiredError:
            return "EXPIRED"
        except TelegramError as exc:
            return f"ERROR ({exc})"
        except Exception as exc:
            return f"ERROR ({type(exc).__name__})"
        finally:
            try:
                await client.stop()
            except Exception:
                pass

    async def _probe_all() -> dict[str, str]:
        out = {}
        for pid, p in personas.items():
            out[pid] = await _probe_one(p)
        return out

    statuses = asyncio.run(_probe_all())

    print(f"{'persona_id':<22} {'language':<10} {'session status'}")
    print("-" * 60)
    for pid, p in personas.items():
        marker = {
            "AUTHORIZED": "[OK]",
            "EXPIRED": "[!!]",
            "no-session-file": "[--]",
        }.get(statuses[pid], "[??]")
        print(f"{marker} {pid:<18} {p.language:<10} {statuses[pid]}")
    print()
    expired = [pid for pid, s in statuses.items() if s != "AUTHORIZED"]
    if expired:
        print("To re-login expired personas, run interactively:")
        for pid in expired:
            print(f"  python -m social.scripts.login_persona {pid}")
    return 0


def _cmd_login(args: argparse.Namespace) -> int:
    """Run interactive Telethon login for a persona.

    Wraps the existing social.scripts.login_persona script for discoverability
    inside the unified CLI. The login itself is interactive — operator must
    enter the SMS verification code Telegram sends to the persona's phone.
    Cannot be automated.
    """
    if str(MISSIONS_DIR.parent) not in sys.path:
        sys.path.insert(0, str(MISSIONS_DIR.parent))
    try:
        from social.scripts.login_persona import main as login_main
    except Exception as exc:
        print(f"login wrapper failed to import: {exc}", file=sys.stderr)
        return 2
    # The script's main() takes argv[0] = script-name, argv[1] = persona_id.
    return login_main(["login_persona", args.persona_id])


def _cmd_status(args: argparse.Namespace) -> int:
    """Compact one-line status for a mission_id."""
    p = MISSIONS_DIR / "results" / f"{args.mission_id}.json"
    if not p.exists():
        print(f"no result for mission_id {args.mission_id!r} at {p}", file=sys.stderr)
        return 2
    d = json.loads(p.read_text(encoding="utf-8"))
    status = d.get("status", "unknown")
    err = d.get("error") or {}
    err_str = ""
    if err:
        err_str = f"  [{err.get('code')}@{err.get('stage')}: {err.get('message','')[:80]}]"
    prov_stage = next(
        (s for s in d.get("stages", []) if s.get("stage") == "provenance_check"),
        None,
    )
    grade = ""
    if prov_stage:
        passed = prov_stage.get("detail", {}).get("passed", {})
        if passed.get("all_passed"):
            grade = " | provenance: ALL PASS"
        else:
            grade = " | provenance: BLOCKED"
    deliv = next(
        (s for s in d.get("stages", []) if s.get("stage") == "delivered"),
        None,
    )
    deliv_str = ""
    if deliv:
        if deliv.get("status") == "ok":
            tmid = deliv.get("detail", {}).get("telegram_message_id")
            deliv_str = f" | delivered: msg_id={tmid}"
        elif deliv.get("status") == "skipped":
            deliv_str = " | delivery: dry_run"
    print(
        f"{args.mission_id}: {status.upper()}{grade}{deliv_str}{err_str}"
    )
    return 0


def _cmd_audit_mission(args: argparse.Namespace) -> int:
    """Re-audit a completed mission's source artifact (before/after report)."""
    p = MISSIONS_DIR / "results" / f"{args.mission_id}.json"
    if not p.exists():
        print(f"no result for mission_id {args.mission_id!r}", file=sys.stderr)
        return 2
    d = json.loads(p.read_text(encoding="utf-8"))
    selected = next(
        (s for s in d.get("stages", []) if s.get("stage") == "artifact_selected"),
        None,
    )
    if not selected:
        print(f"no artifact_selected stage in {p}", file=sys.stderr)
        return 2
    src = selected.get("detail", {}).get("source_fixture") or selected.get(
        "detail", {}
    ).get("work_path")
    if not src:
        print("no source path in artifact_selected stage", file=sys.stderr)
        return 2
    src_p = Path(src)
    if not src_p.exists():
        print(f"source artifact missing on disk: {src_p}", file=sys.stderr)
        return 2

    print(f"[audit-mission] re-auditing {args.mission_id} from {src_p}", file=sys.stderr)
    args.image = str(src_p)
    args.exif_template = None
    return _cmd_audit(args)


def _cmd_match_persona(args: argparse.Namespace) -> int:
    """Score archetype against available personas, print best match."""
    try:
        pid, meta = match_archetype_to_persona(
            args.archetype,
            audience_profile=args.audience or "",
            language_hint=args.language or "",
        )
    except PlannerError as exc:
        print(f"[matcher] {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"persona_id": pid, "meta": meta}, indent=2))
    else:
        print(f"persona_id: {pid}")
        print(f"  source:   {meta.get('source')}")
        if meta.get("model"):
            print(f"  model:    {meta.get('model')}")
    return 0


def _cmd_plan(args: argparse.Namespace) -> int:
    try:
        text = plan_mission_yaml(
            args.intent,
            operator=args.operator,
            require_live_persona=args.live,
        )
    except PlannerError as exc:
        print(f"[planner] {exc}", file=sys.stderr)
        return 2

    if args.out:
        out = Path(args.out)
        if out.is_dir():
            # Extract mission_id from the YAML to name the file
            import yaml as _yaml
            spec = _yaml.safe_load(text)
            mid = spec.get("mission_id", "GENERATED-MISSION")
            out = out / f"{mid}.yaml"
        # Atomic write
        tmp = out.with_suffix(out.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(out)
        print(f"[planner] wrote {out}", file=sys.stderr)
    print(text)
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
    p_watch.add_argument(
        "--workers", type=int, default=1,
        help="parallel mission workers (default 1, serial). 4-8 recommended for batched submissions.",
    )
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

    p_plan = sub.add_parser(
        "plan", help="convert operator-intent text into a MissionSpec YAML"
    )
    p_plan.add_argument(
        "intent",
        help="natural-language description of the mission "
             "(e.g., 'plant a leaked-orders post in the pro-regime channel "
             "from a frustrated quartermaster persona')",
    )
    p_plan.add_argument(
        "--operator", default="J2-INSCOM-Demo",
        help="operator identity stamped on the mission (default: J2-INSCOM-Demo)",
    )
    p_plan.add_argument(
        "--out", help="write YAML to file or directory (mission_id is appended if dir)",
    )
    p_plan.add_argument(
        "--live", action="store_true",
        help="require delivery.persona_id to come from social/personas/",
    )
    p_plan.set_defaults(func=_cmd_plan)

    p_personas = sub.add_parser(
        "personas",
        help="list available personas and their Telegram session auth status",
    )
    p_personas.set_defaults(func=_cmd_personas)

    p_login = sub.add_parser(
        "login",
        help="interactively re-login an expired persona (requires SMS code)",
    )
    p_login.add_argument(
        "persona_id",
        help="persona to re-authenticate (must exist under social/personas/)",
    )
    p_login.set_defaults(func=_cmd_login)

    p_status = sub.add_parser(
        "status", help="compact one-line status for a completed mission",
    )
    p_status.add_argument("mission_id", help="mission_id to look up under missions/results/")
    p_status.set_defaults(func=_cmd_status)

    p_audit_mission = sub.add_parser(
        "audit-mission",
        help="re-audit a completed mission's source artifact (before/after report)",
    )
    p_audit_mission.add_argument(
        "mission_id", help="mission_id whose source artifact to re-audit"
    )
    p_audit_mission.add_argument("--titan", action="store_true")
    p_audit_mission.add_argument("--google", action="store_true")
    p_audit_mission.add_argument("--json", action="store_true")
    p_audit_mission.set_defaults(func=_cmd_audit_mission)

    p_match = sub.add_parser(
        "match-persona",
        help="resolve an archetype to the best-matching available persona_id",
    )
    p_match.add_argument(
        "archetype",
        help="archetype description (e.g., 'frustrated battalion quartermaster')",
    )
    p_match.add_argument("--audience", help="audience profile hint")
    p_match.add_argument(
        "--language", help="2-letter language code hint (ru, uk, fa, etc.)"
    )
    p_match.add_argument("--json", action="store_true")
    p_match.set_defaults(func=_cmd_match_persona)

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
