"""Forensic CLI: signature-match, prnu-extract / prnu-inject, steg-{embed,extract,analyze}, full-stack.

Run from repo root:

    python -m forensic.cli signature-match --donor ref.jpg --target ai.jpg --output out.jpg
    python -m forensic.cli prnu-extract  --corpus dir/ --output prnu.npy
    python -m forensic.cli prnu-inject   --target ai.jpg --prnu prnu.npy --output out.jpg
    python -m forensic.cli steg-embed    --image cover.png --payload-text 'msg' --key SECRET --output stego.png
    python -m forensic.cli steg-extract  --image stego.png --key SECRET
    python -m forensic.cli steg-analyze  --image stego.png [--cover cover.png]
    python -m forensic.cli full-stack    --target ai.jpg --donor ref.jpg --prnu prnu.npy \\
                                         --payload-text 'next contact: ...' --key SECRET --output final.png
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _add_signature_match(sub):
    p = sub.add_parser("signature-match", help="Run all 4 Tier-1 signature-match steps")
    p.add_argument("--donor", required=True, type=Path, help="donor JPEG (real iPhone capture)")
    p.add_argument("--target", required=True, type=Path, help="synthetic image to match to donor")
    p.add_argument("--output", required=True, type=Path)
    return p


def _add_prnu_extract(sub):
    p = sub.add_parser("prnu-extract", help="Estimate PRNU from a corpus")
    p.add_argument("--corpus", required=True, type=Path, help="directory of reference images")
    p.add_argument("--output", required=True, type=Path, help="output .npy path")
    p.add_argument("--max-images", type=int, default=50)
    p.add_argument("--height", type=int, default=None, help="resize all corpus images to this H")
    p.add_argument("--width", type=int, default=None, help="resize all corpus images to this W")
    return p


def _add_prnu_inject(sub):
    p = sub.add_parser("prnu-inject", help="Inject a PRNU pattern into a synthetic image")
    p.add_argument("--target", required=True, type=Path)
    p.add_argument("--prnu", required=True, type=Path, help="path to .npy from prnu-extract")
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--alpha", type=float, default=0.025)
    return p


def _add_steg_embed(sub):
    p = sub.add_parser("steg-embed", help="LSB-embed a payload into an image (PNG output)")
    p.add_argument("--image", required=True, type=Path, help="cover image")
    p.add_argument("--key", required=True, type=str)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--payload-text", type=str, help="text payload")
    src.add_argument("--payload-file", type=Path, help="read payload from file")
    p.add_argument("--output", required=True, type=Path)
    return p


def _add_steg_extract(sub):
    p = sub.add_parser("steg-extract", help="Recover a payload from a stego image")
    p.add_argument("--image", required=True, type=Path)
    p.add_argument("--key", required=True, type=str)
    p.add_argument("--output", type=Path, help="write payload bytes here; if omitted prints to stdout")
    return p


def _add_steg_analyze(sub):
    p = sub.add_parser("steg-analyze", help="Run chi-squared + RS analysis self-check")
    p.add_argument("--image", required=True, type=Path)
    p.add_argument("--cover", type=Path, help="optional reference cover for delta comparison")
    return p


def _add_full_stack(sub):
    p = sub.add_parser("full-stack", help="Run signature-match + prnu-inject + steg-embed end-to-end")
    p.add_argument("--target", required=True, type=Path)
    p.add_argument("--donor", required=True, type=Path)
    p.add_argument("--prnu", type=Path, help="optional PRNU .npy; if omitted, PRNU step is skipped")
    p.add_argument("--alpha", type=float, default=0.025)
    p.add_argument("--key", type=str, help="optional steg key; if omitted, steg step is skipped")
    src = p.add_mutually_exclusive_group()
    src.add_argument("--payload-text", type=str)
    src.add_argument("--payload-file", type=Path)
    p.add_argument("--output", required=True, type=Path)
    return p


def _add_launder(sub):
    p = sub.add_parser("launder", help="Re-photograph + spectrum laundering (defeats CNN classifiers)")
    p.add_argument("--target", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--reference", type=Path, help="optional natural-photo reference for spectrum target")
    p.add_argument("--psf-sigma", type=float, default=0.7)
    p.add_argument("--chroma", type=float, default=1.2)
    p.add_argument("--noise", type=float, default=1.8)
    p.add_argument("--sharpen", type=float, default=0.6)
    p.add_argument("--jpeg-q1", type=int, default=88)
    p.add_argument("--jpeg-q2", type=int, default=92)
    p.add_argument("--blend", type=float, default=0.5, help="spectrum correction blend (0..1)")
    p.add_argument("--no-score", action="store_true", help="skip surrogate detector before/after")
    p.add_argument("--force-heuristic", action="store_true", help="skip torch surrogate, use spectral heuristic")
    p.add_argument("--seed", type=int, default=0)
    return p


def _add_launder_score(sub):
    p = sub.add_parser("launder-score", help="Run surrogate AI-detector on one image")
    p.add_argument("--image", required=True, type=Path)
    p.add_argument("--force-heuristic", action="store_true")
    return p


def _add_launder_compare(sub):
    p = sub.add_parser("launder-compare", help="Side-by-side before/after PNG with detector scores")
    p.add_argument("--before", required=True, type=Path)
    p.add_argument("--after", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--force-heuristic", action="store_true")
    return p


def _add_launder_sweep(sub):
    p = sub.add_parser("launder-sweep", help="Try multiple param sets, find best p_ai drop")
    p.add_argument("--target", required=True, type=Path)
    p.add_argument("--output-dir", required=True, type=Path)
    p.add_argument("--multi", action="store_true", help="score against every surrogate; pick minimax (worst-detector) winner")
    return p


def _add_launder_cascade(sub):
    p = sub.add_parser("launder-cascade", help="Two-pass laundering + color jitter (best evasion)")
    p.add_argument("--target", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    return p


def _add_anti_detect(sub):
    p = sub.add_parser(
        "anti-detect",
        help="Full chain: cascade laundering → optional PRNU inject → optional signature match → multi-detector self-check",
    )
    p.add_argument("--target", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--donor", type=Path, help="real-camera JPEG for signature transplant")
    p.add_argument("--prnu", type=Path, help=".npy PRNU pattern from prnu-extract")
    p.add_argument("--prnu-alpha", type=float, default=0.025)
    p.add_argument("--no-cascade", action="store_true", help="skip laundering cascade")
    p.add_argument("--no-self-check", action="store_true", help="skip surrogate scoring")
    p.add_argument("--max-p-ai", type=float, default=0.40,
                   help="abort if worst-detector p_ai exceeds this (default 0.40)")
    p.add_argument("--no-strict", action="store_true",
                   help="don't abort on threshold; just warn")
    return p


def cmd_signature_match(args):
    from forensic.signature import full_signature_match
    status = full_signature_match(args.target, args.donor, args.output)
    print(json.dumps(status, indent=2))
    return 0


def cmd_prnu_extract(args):
    from forensic.prnu import extract as prnu_extract

    paths = sorted(p for p in args.corpus.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    if not paths:
        print(f"no images found in {args.corpus}", file=sys.stderr)
        return 1
    target_shape = (args.height, args.width) if args.height and args.width else None
    prnu = prnu_extract.extract_prnu(paths, target_shape=target_shape, max_images=args.max_images)
    prnu_extract.save_prnu(prnu, args.output)
    print(json.dumps({
        "corpus_size": len(paths),
        "used": min(len(paths), args.max_images),
        "shape": list(prnu.shape),
        "saved": str(args.output),
    }, indent=2))
    return 0


def cmd_prnu_inject(args):
    from forensic.prnu import extract as prnu_extract
    from forensic.prnu import inject as prnu_inject

    prnu = prnu_extract.load_prnu(args.prnu)
    out = prnu_inject.inject_prnu(args.target, prnu, args.output, alpha=args.alpha)
    rho = prnu_inject.correlate(out, prnu)
    print(json.dumps({"output": str(out), "correlation": rho, "alpha": args.alpha}, indent=2))
    return 0


def _read_payload(args) -> bytes:
    if getattr(args, "payload_text", None):
        return args.payload_text.encode("utf-8")
    if getattr(args, "payload_file", None):
        return args.payload_file.read_bytes()
    return b""


def cmd_steg_embed(args):
    from forensic.steg import embed as steg_embed

    payload = _read_payload(args)
    out, meta = steg_embed.embed(args.image, payload, args.key.encode("utf-8"), args.output)
    print(json.dumps({"output": str(out), **meta}, indent=2))
    return 0


def cmd_steg_extract(args):
    from forensic.steg import extract as steg_extract

    payload = steg_extract.extract(args.image, args.key.encode("utf-8"))
    if args.output:
        args.output.write_bytes(payload)
        print(json.dumps({"output": str(args.output), "bytes": len(payload)}, indent=2))
    else:
        try:
            sys.stdout.write(payload.decode("utf-8"))
        except UnicodeDecodeError:
            sys.stdout.buffer.write(payload)
    return 0


def cmd_steg_analyze(args):
    from forensic.steg import analyze as steg_analyze

    if args.cover:
        report = steg_analyze.compare(args.cover, args.image)
    else:
        r = steg_analyze.analyze(args.image)
        report = {
            "chi_squared_p": r.chi_squared_p,
            "rs_estimated_rate": r.rs_estimated_rate,
            "flagged": r.flagged,
            "note": r.note,
        }
    print(json.dumps(report, indent=2))
    return 0


def cmd_full_stack(args):
    from forensic.signature import full_signature_match

    work = args.output.with_suffix(".sigmatch.jpg")
    status = full_signature_match(args.target, args.donor, work)
    print(json.dumps({"signature_match": status}, indent=2))

    current = work
    prnu_corr = None
    if args.prnu:
        from forensic.prnu import extract as prnu_extract
        from forensic.prnu import inject as prnu_inject

        prnu = prnu_extract.load_prnu(args.prnu)
        prnu_out = args.output.with_suffix(".prnu.jpg")
        prnu_inject.inject_prnu(current, prnu, prnu_out, alpha=args.alpha)
        prnu_corr = prnu_inject.correlate(prnu_out, prnu)
        print(json.dumps({"prnu_inject": {"output": str(prnu_out), "correlation": prnu_corr}}, indent=2))
        current = prnu_out

    if args.key:
        from forensic.steg import embed as steg_embed
        from forensic.steg import analyze as steg_analyze

        payload = _read_payload(args)
        if not payload:
            print("--key given but no --payload-text or --payload-file", file=sys.stderr)
            return 2
        stego_out, meta = steg_embed.embed(current, payload, args.key.encode("utf-8"), args.output)
        cmp = steg_analyze.compare(current, stego_out)
        print(json.dumps({"steg_embed": meta, "steg_analyze": cmp}, indent=2))
        current = stego_out

    if current != args.output:
        import shutil
        shutil.copy2(current, args.output)
    print(json.dumps({"final": str(args.output)}, indent=2))
    return 0


def cmd_launder(args):
    from forensic.laundering import full_launder, rephoto, spectrum

    rp = rephoto.RephotoParams(
        psf_sigma=args.psf_sigma,
        chroma_strength=args.chroma,
        sensor_noise=args.noise,
        sharpen_amount=args.sharpen,
        jpeg_q1=args.jpeg_q1,
        jpeg_q2=args.jpeg_q2,
        seed=args.seed,
    )
    sp = spectrum.SpectrumParams(blend=args.blend)
    result = full_launder(
        target=args.target,
        output=args.output,
        rephoto_params=rp,
        spectrum_params=sp,
        spectrum_reference=args.reference,
        score_before_after=not args.no_score,
        force_heuristic_score=args.force_heuristic,
    )
    print(json.dumps(result, indent=2))
    return 0


def cmd_launder_score(args):
    from forensic.laundering import selfcheck

    r = selfcheck.detect(args.image, force_heuristic=args.force_heuristic)
    print(json.dumps({
        "model": r.model,
        "backend": r.backend,
        "p_ai": r.p_ai,
        "p_real": r.p_real,
        "raw_label": r.raw_label,
        "note": r.note,
    }, indent=2))
    return 0


def cmd_launder_compare(args):
    from forensic.laundering import demo, selfcheck

    sb = selfcheck.detect(args.before, force_heuristic=args.force_heuristic)
    sa = selfcheck.detect(args.after, force_heuristic=args.force_heuristic)
    out = demo.side_by_side(args.before, args.after, args.output, score_before=sb, score_after=sa)
    print(json.dumps({
        "output": str(out),
        "before": {"model": sb.model, "p_ai": sb.p_ai, "raw_label": sb.raw_label},
        "after": {"model": sa.model, "p_ai": sa.p_ai, "raw_label": sa.raw_label},
        "delta_p_ai": sa.p_ai - sb.p_ai,
    }, indent=2))
    return 0


def cmd_launder_sweep(args):
    from forensic.laundering import demo

    if args.multi:
        results = demo.multi_sweep(args.target, args.output_dir)
    else:
        results = demo.sweep(args.target, args.output_dir)
    print(json.dumps({"results": results, "best": results[0] if results else None}, indent=2))
    return 0


def cmd_launder_cascade(args):
    from forensic.laundering import cascade as cascade_mod

    result = cascade_mod.cascade(args.target, args.output)
    print(json.dumps(result, indent=2))
    return 0


def cmd_anti_detect(args):
    from forensic.integration import (
        AntiDetectionAbort,
        AntiDetectionOptions,
        apply_anti_detection_chain,
    )

    opts = AntiDetectionOptions(
        cascade=not args.no_cascade,
        prnu_pattern=args.prnu,
        prnu_alpha=args.prnu_alpha,
        donor_jpeg=args.donor,
        self_check=not args.no_self_check,
        max_p_ai=args.max_p_ai,
        strict=not args.no_strict,
    )
    try:
        report = apply_anti_detection_chain(args.target, args.output, options=opts)
    except AntiDetectionAbort as exc:
        print(json.dumps({
            "ok": False,
            "aborted": True,
            "message": str(exc),
            "report": exc.report,
        }, indent=2))
        return 2
    print(json.dumps({"ok": True, "report": report}, indent=2))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="mendacity-forensic", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    _add_signature_match(sub)
    _add_prnu_extract(sub)
    _add_prnu_inject(sub)
    _add_steg_embed(sub)
    _add_steg_extract(sub)
    _add_steg_analyze(sub)
    _add_full_stack(sub)
    _add_launder(sub)
    _add_launder_score(sub)
    _add_launder_compare(sub)
    _add_launder_sweep(sub)
    _add_launder_cascade(sub)
    _add_anti_detect(sub)

    args = parser.parse_args(argv)
    handlers = {
        "signature-match": cmd_signature_match,
        "prnu-extract": cmd_prnu_extract,
        "prnu-inject": cmd_prnu_inject,
        "steg-embed": cmd_steg_embed,
        "steg-extract": cmd_steg_extract,
        "steg-analyze": cmd_steg_analyze,
        "full-stack": cmd_full_stack,
        "launder": cmd_launder,
        "launder-cascade": cmd_launder_cascade,
        "launder-score": cmd_launder_score,
        "launder-compare": cmd_launder_compare,
        "launder-sweep": cmd_launder_sweep,
        "anti-detect": cmd_anti_detect,
    }
    return handlers[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
