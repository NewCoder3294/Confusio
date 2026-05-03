#!/usr/bin/env python3
"""
Copy or strip JPEG EXIF using piexif (pure Python).

Use this for **local provenance / Mendacity tests only**: e.g. copy metadata from a
**reference JPEG you own** onto another image so pipelines see the same EXIF shape.

``from-json`` / ``transplant`` **harmonize** output by default: **Exif PixelXDimension /
PixelYDimension** match the actual JPEG raster, and **GPS is omitted** (use ``--keep-gps``
to retain GPS from the source / JSON).

This script does **not** download third-party GitHub repos (Swift ImageIO samples are
not used for batch JPEG writing). It does **not** ship vendor-specific defaults meant
to imitate another manufacturer’s camera—supply your own reference file or JSON.

Examples:

  # Copy all EXIF from a reference capture onto another JPEG
  python scripts/apply_jpeg_exif.py transplant \\
    --exif-source ref.jpg --image target.jpg --output out.jpg

  # Same, but re-encode input as JPEG first (e.g. PNG or mislabeled JPEG)
  python scripts/apply_jpeg_exif.py transplant \\
    --exif-source ref.jpg --image assets/foo.png --output out.jpg --reencode-jpeg

  # Remove EXIF from a JPEG
  python scripts/apply_jpeg_exif.py strip --image in.jpg --output stripped.jpg

  # After transplant, tag Software so panels show a synthetic provenance label
  python scripts/apply_jpeg_exif.py transplant ... --annotate-fixture

  # DCIM-style disk name (directory + IMG_<digits>.JPG), stem matches embedded dates when --infer-stem
  python scripts/apply_jpeg_exif.py from-json --json fixtures/foo.json --image in.png \\
    --output assets/ --apple-roll-filename --infer-stem --reencode-jpeg

  # Apple-style DocumentName / PNG Title chunk (run after from-json if desired)
  python scripts/apple_style_titles.py jpeg --image out.jpg --output final.jpg --stem IMG_5842 --title \"Caption\"
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent


def _apple_roll_paths():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "apple_roll_paths", _SCRIPT_DIR / "apple_roll_paths.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load apple_roll_paths")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _resolve_jpeg_output_apple_roll(args, piexif, final_jpeg_bytes: bytes) -> Path | None:
    """If ``--apple-roll-filename``, return ``.../IMG_<n>.JPG`` under ``--output`` dir; else None."""
    if not getattr(args, "apple_roll_filename", False):
        return None

    ar = _apple_roll_paths()
    infer = getattr(args, "infer_stem", False)
    rnd = getattr(args, "random_stem", False)
    stem_arg = getattr(args, "stem", None)

    if infer:
        stem = ar.infer_stem_from_exif_jpeg(piexif, final_jpeg_bytes)
    elif rnd:
        stem = ar.infer_stem_random()
    elif stem_arg:
        stem = ar.normalize_img_stem(stem_arg)
    else:
        print(
            "--apple-roll-filename requires one of --stem, --infer-stem, or --random-stem",
            file=sys.stderr,
        )
        raise SystemExit(1)

    out_dir = Path(args.output)
    if out_dir.exists() and out_dir.is_file():
        print(
            "With --apple-roll-filename, --output must be a directory path, not a file.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    ext = getattr(args, "apple_extension", "JPG")
    return ar.resolve_apple_roll_path(out_dir, stem, extension=ext)


def _require_piexif():
    try:
        import piexif  # noqa: F401
    except ImportError as e:
        print(
            "Missing dependency: install with `pip install piexif` "
            "(included in the project's dev extra: `pip install -e '.[dev]`).",
            file=sys.stderr,
        )
        raise SystemExit(1) from e
    import piexif

    return piexif


def _require_pil():
    try:
        from PIL import Image  # noqa: F401
    except ImportError as e:
        print(
            "Missing dependency: install Pillow (dev extra includes it).",
            file=sys.stderr,
        )
        raise SystemExit(1) from e
    from PIL import Image

    return Image


def _read_image_as_jpeg_bytes(path: Path, reencode: bool) -> tuple[bytes, str]:
    """Return JPEG bytes and a note if re-encoding occurred."""
    raw = path.read_bytes()
    if raw[:3] == b"\xff\xd8\xff" and not reencode:
        return raw, ""
    Image = _require_pil()
    im = Image.open(io.BytesIO(raw))
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=95, optimize=True)
    note = f"re-encoded as JPEG from {path.name} ({getattr(im, 'format', '?')})"
    return buf.getvalue(), note


def _jpeg_pixel_size(jpeg_bytes: bytes) -> tuple[int, int]:
    """Return (width, height) of the raster stored in the JPEG (before EXIF orientation display)."""
    Image = _require_pil()
    im = Image.open(io.BytesIO(jpeg_bytes))
    w, h = im.size
    return int(w), int(h)


def _harmonize_exif_to_output_jpeg(
    piexif,
    exif_dict: dict,
    width: int,
    height: int,
    *,
    omit_gps: bool,
) -> None:
    """Match declared pixel dimensions to actual JPEG; drop GPS unless preserving."""
    exif_ifd = exif_dict.setdefault("Exif", {})
    exif_ifd[piexif.ExifIFD.PixelXDimension] = width
    exif_ifd[piexif.ExifIFD.PixelYDimension] = height
    if omit_gps:
        exif_dict.pop("GPS", None)


def _annotate_fixture(piexif, exif_dict: dict) -> None:
    suffix = b" | mendacity-test-fixture"
    ifd0 = exif_dict.setdefault("0th", {})
    sw = ifd0.get(piexif.ImageIFD.Software, b"")
    if isinstance(sw, bytes):
        ifd0[piexif.ImageIFD.Software] = sw.rstrip() + suffix
    else:
        ifd0[piexif.ImageIFD.Software] = suffix.strip()


def cmd_transplant(args: argparse.Namespace) -> int:
    piexif = _require_piexif()
    exif_src = Path(args.exif_source)
    image_path = Path(args.image)

    try:
        exif_dict = piexif.load(str(exif_src))
    except Exception as e:
        print(f"Failed to read EXIF from {exif_src}: {e}", file=sys.stderr)
        return 1

    if args.annotate_fixture:
        _annotate_fixture(piexif, exif_dict)

    jpeg_bytes, note = _read_image_as_jpeg_bytes(image_path, args.reencode_jpeg)
    if note:
        print(note, file=sys.stderr)

    w, h = _jpeg_pixel_size(jpeg_bytes)
    _harmonize_exif_to_output_jpeg(
        piexif,
        exif_dict,
        w,
        h,
        omit_gps=not getattr(args, "keep_gps", False),
    )

    try:
        exif_bytes = piexif.dump(exif_dict)
    except Exception as e:
        print(f"Failed to serialize EXIF: {e}", file=sys.stderr)
        return 1

    out_buf = io.BytesIO()
    try:
        piexif.insert(exif_bytes, jpeg_bytes, out_buf)
    except Exception as e:
        print(f"Failed to insert EXIF: {e}", file=sys.stderr)
        return 1

    final_bytes = out_buf.getvalue()
    resolved = _resolve_jpeg_output_apple_roll(args, piexif, final_bytes)
    out_path = resolved if resolved is not None else Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(final_bytes)
    print(f"Wrote {out_path}")
    return 0


def cmd_strip(args: argparse.Namespace) -> int:
    piexif = _require_piexif()
    image_path = Path(args.image)
    out_path = Path(args.output)
    jpeg_bytes, note = _read_image_as_jpeg_bytes(image_path, args.reencode_jpeg)
    if note:
        print(note, file=sys.stderr)

    out_buf = io.BytesIO()
    try:
        piexif.remove(jpeg_bytes, out_buf)
    except Exception as e:
        print(f"Failed to strip EXIF: {e}", file=sys.stderr)
        return 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(out_buf.getvalue())
    print(f"Wrote {out_path}")
    return 0


def _coerce_json_exif_value(v: object) -> object:
    """Turn JSON into piexif-friendly Python values (bytes, tuples of rationals, nested tuples)."""
    if isinstance(v, dict) and "__b64__" in v:
        return base64.b64decode(str(v["__b64__"]))
    if isinstance(v, list):
        if not v:
            return tuple()
        if isinstance(v[0], list):
            return tuple(_coerce_json_exif_value(x) for x in v)
        if all(isinstance(x, int) for x in v):
            return tuple(v)
        raise ValueError(f"Unsupported list value in EXIF JSON: {v!r}")
    return v


def _normalize_json_exif(obj: object) -> dict:
    """Load a JSON definition into a piexif-compatible dict (nested ifd name -> tag -> value).

    Top-level keys must be one of: "0th", "Exif", "GPS", "1st" (optional ``_meta`` is ignored).
    Tag keys are integers or hex strings like "0x010f". Values are strings (stored as UTF-8
    bytes), ints, ``{"__b64__": "..."}`` for arbitrary bytes, or lists that become tuples
    (flat rationals, nested lists for GPS / lens specification).
    """
    if not isinstance(obj, dict):
        raise ValueError("root JSON must be an object")

    out: dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}

    for ifd_name in ("0th", "Exif", "GPS", "1st"):
        block = obj.get(ifd_name)
        if block is None:
            continue
        if not isinstance(block, dict):
            raise ValueError(f"{ifd_name} must be an object")
        target = out.setdefault(ifd_name, {})
        for k, v in block.items():
            tag = int(k, 16) if isinstance(k, str) and k.startswith("0x") else int(k)
            if isinstance(v, str):
                target[tag] = v.encode("utf-8")
            else:
                target[tag] = _coerce_json_exif_value(v)

    # thumbnail must be bytes or None for dump
    if "thumbnail" in obj:
        out["thumbnail"] = obj["thumbnail"]

    return out


def cmd_from_json(args: argparse.Namespace) -> int:
    """Apply EXIF from a JSON file (you author it for your own test vectors)."""
    piexif = _require_piexif()
    spec = json.loads(Path(args.json).read_text(encoding="utf-8"))
    exif_dict = _normalize_json_exif(spec)

    image_path = Path(args.image)
    jpeg_bytes, note = _read_image_as_jpeg_bytes(image_path, args.reencode_jpeg)
    if note:
        print(note, file=sys.stderr)

    w, h = _jpeg_pixel_size(jpeg_bytes)
    _harmonize_exif_to_output_jpeg(
        piexif,
        exif_dict,
        w,
        h,
        omit_gps=not getattr(args, "keep_gps", False),
    )

    try:
        exif_bytes = piexif.dump(exif_dict)
    except Exception as e:
        print(f"Invalid EXIF JSON / dump failed: {e}", file=sys.stderr)
        return 1

    out_buf = io.BytesIO()
    try:
        piexif.insert(exif_bytes, jpeg_bytes, out_buf)
    except Exception as e:
        print(f"Failed to insert EXIF: {e}", file=sys.stderr)
        return 1

    final_bytes = out_buf.getvalue()
    resolved = _resolve_jpeg_output_apple_roll(args, piexif, final_bytes)
    out_path = resolved if resolved is not None else Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(final_bytes)
    print(f"Wrote {out_path}")
    return 0


def _register_exif_harmonize_args(sp: argparse.ArgumentParser) -> None:
    sp.add_argument(
        "--keep-gps",
        action="store_true",
        help=(
            "Keep GPS from --exif-source or JSON. Default: omit GPS and set "
            "Exif PixelXDimension/PixelYDimension to match the output JPEG."
        ),
    )


def _register_apple_roll_filename_args(sp: argparse.ArgumentParser) -> None:
    sp.add_argument(
        "--apple-roll-filename",
        action="store_true",
        help=(
            "Write DCIM-style IMG_<digits>.JPG under the directory given by --output "
            "(same pattern as iPhone Camera Roll / DCIM filenames)."
        ),
    )
    sp.add_argument(
        "--apple-extension",
        default="JPG",
        metavar="EXT",
        help="Extension for apple-roll filenames (default JPG).",
    )
    ag = sp.add_mutually_exclusive_group()
    ag.add_argument(
        "--stem",
        default=None,
        metavar="N",
        help="Counter as digits or IMG_NNNN (with --apple-roll-filename)",
    )
    ag.add_argument(
        "--infer-stem",
        action="store_true",
        help="IMG_XXXX from EXIF date/hash after metadata is applied",
    )
    ag.add_argument(
        "--random-stem",
        action="store_true",
        help="Random IMG_1000–IMG_9999",
    )


def main() -> int:
    p = argparse.ArgumentParser(
        description="Copy/strip JPEG EXIF for local provenance testing (see module docstring)."
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("transplant", help="Copy EXIF from --exif-source onto --image")
    t.add_argument("--exif-source", required=True, help="JPEG whose EXIF is copied")
    t.add_argument("--image", required=True, help="Target image (JPEG by default)")
    t.add_argument(
        "--output",
        required=True,
        help="Output JPEG path, or a directory if --apple-roll-filename is set",
    )
    t.add_argument(
        "--reencode-jpeg",
        action="store_true",
        help="Decode with Pillow and re-save as JPEG before inserting EXIF",
    )
    t.add_argument(
        "--annotate-fixture",
        action="store_true",
        help='Append " | mendacity-test-fixture" to TIFF Software if present',
    )
    _register_apple_roll_filename_args(t)
    _register_exif_harmonize_args(t)
    t.set_defaults(func=cmd_transplant)

    s = sub.add_parser("strip", help="Remove EXIF from a JPEG")
    s.add_argument("--image", required=True)
    s.add_argument("--output", required=True)
    s.add_argument(
        "--reencode-jpeg",
        action="store_true",
        help="If input is not raw JPEG, convert to JPEG then strip",
    )
    s.set_defaults(func=cmd_strip)

    j = sub.add_parser(
        "from-json",
        help="Insert EXIF built from a JSON spec (tag ids per piexif IFDs)",
    )
    j.add_argument("--json", required=True, help="Path to JSON EXIF specification")
    j.add_argument("--image", required=True)
    j.add_argument(
        "--output",
        required=True,
        help="Output JPEG path, or a directory if --apple-roll-filename is set",
    )
    j.add_argument("--reencode-jpeg", action="store_true")
    _register_apple_roll_filename_args(j)
    _register_exif_harmonize_args(j)
    j.set_defaults(func=cmd_from_json)

    args = p.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
