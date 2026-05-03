#!/usr/bin/env python3
"""
Embed Apple-style *titles* the way macOS / Photos commonly exposes them:

**JPEG**
  - TIFF **DocumentName** (tag 269): stem like ``IMG_5842`` (matches Camera-roll-style names).
  - TIFF **ImageDescription** (270): human-readable caption / title (often shown in Get Info).
  - Optional **XPTitle** (40091): legacy Windows XP Unicode title field; some tools round-trip it.
  - By default, also writes Apple-ish **Software** / **HostComputer** (IFD0), optional **Artist** /
    **Copyright**, and Exif **UserComment** (Unicode); disable with ``--no-apple-device-strings``.
  - Optional ``--user-comment`` sets Exif **UserComment** explicitly (overrides the
    default title-based UserComment).

**PNG**
  - Standard PNG ``Title`` text chunk (what Finder shows as “Title” for PNG when present).

Use after ``apply_jpeg_exif.py`` if you inject EXIF first, or run this alone on a bare JPEG/PNG.

Examples::

  python scripts/apple_style_titles.py jpeg \\
    --image photo.jpg --output titled.jpg \\
    --stem IMG_5842 --title \"Weekend hike\"

  # DCIM-style disk name IMG_<n>.JPG inside folder ``exports/``
  python scripts/apple_style_titles.py jpeg \\
    --image photo.jpg --output exports/ --apple-roll-filename --stem 5842

  python scripts/apple_style_titles.py png \\
    --image art.png --output art_titled.png \\
    --stem IMG_5842 --title \"Weekend hike\"

  # Guess IMG_XXXX from DateTimeOriginal (JPEG EXIF), fallback random IMG_1xxx–IMG_9xxx
  python scripts/apple_style_titles.py jpeg --image photo.jpg --output out.jpg --infer-stem --title \"Lake\"
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent


def _load_apple_roll_paths():
    spec = importlib.util.spec_from_file_location(
        "apple_roll_paths", _SCRIPTS / "apple_roll_paths.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("apple_roll_paths missing")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_ar = _load_apple_roll_paths()
normalize_img_stem = _ar.normalize_img_stem
infer_stem_from_exif_jpeg = _ar.infer_stem_from_exif_jpeg
infer_stem_random = _ar.infer_stem_random
infer_stem_png_bytes = _ar.infer_stem_png_bytes
resolve_apple_roll_path = _ar.resolve_apple_roll_path


def _require_piexif():
    try:
        import piexif  # noqa: F401
    except ImportError as e:
        print(
            "Missing piexif: `pip install piexif` or `pip install -e '.[dev]'`.",
            file=sys.stderr,
        )
        raise SystemExit(1) from e
    return __import__("piexif")


def _require_pil():
    try:
        from PIL import Image
        from PIL import PngImagePlugin
    except ImportError as e:
        print("Missing Pillow: `pip install Pillow`.", file=sys.stderr)
        raise SystemExit(1) from e
    return Image, PngImagePlugin


def _xp_title_unicode(title: str) -> bytes:
    """UTF-16 BE NUL-terminated payload typical for XPTitle."""
    encoded = title.encode("utf-16-be") + b"\x00\x00"
    return encoded


def _exif_user_comment_unicode(text: str) -> bytes:
    """EXIF UserComment: 8-byte ``Unicode\\0`` charset header + UTF-16 LE body."""
    return b"Unicode\x00" + text.encode("utf-16-le")


def cmd_jpeg(args: argparse.Namespace) -> int:
    piexif = _require_piexif()
    Image, _ = _require_pil()
    src = Path(args.image)
    raw = src.read_bytes()

    if raw[:3] != b"\xff\xd8\xff":
        im = Image.open(io.BytesIO(raw))
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=95, optimize=True)
        raw = buf.getvalue()
        print("Re-encoded input as JPEG before embedding titles.", file=sys.stderr)

    if args.infer_stem:
        stem = infer_stem_from_exif_jpeg(piexif, raw)
    elif args.random_stem:
        stem = infer_stem_random()
    else:
        stem = normalize_img_stem(args.stem)

    title_text = args.title if args.title is not None else stem

    try:
        exif_dict = piexif.load(raw)
    except Exception:
        exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}

    zeroth = exif_dict.setdefault("0th", {})
    zeroth[piexif.ImageIFD.DocumentName] = stem.encode("ascii", errors="replace")
    zeroth[piexif.ImageIFD.ImageDescription] = title_text.encode("utf-8")
    if args.xp_title:
        zeroth[piexif.ImageIFD.XPTitle] = _xp_title_unicode(title_text)

    if getattr(args, "apple_make", None) is not None:
        zeroth[piexif.ImageIFD.Make] = args.apple_make.encode("utf-8")
    if getattr(args, "apple_model", None) is not None:
        zeroth[piexif.ImageIFD.Model] = args.apple_model.encode("utf-8")

    exif_ifd = exif_dict.setdefault("Exif", {})
    if getattr(args, "apple_device_strings", True):
        zeroth[piexif.ImageIFD.Software] = args.apple_software.encode("utf-8")
        zeroth[piexif.ImageIFD.HostComputer] = args.apple_host.encode("utf-8")
        # Finder / Photos sometimes surface these alongside titles.
        zeroth[piexif.ImageIFD.Artist] = args.apple_artist.encode("utf-8")
        zeroth[piexif.ImageIFD.Copyright] = args.apple_copyright.encode("utf-8")

    if getattr(args, "user_comment", None) is not None:
        exif_ifd[piexif.ExifIFD.UserComment] = _exif_user_comment_unicode(
            args.user_comment
        )
    elif getattr(args, "apple_device_strings", True):
        exif_ifd[piexif.ExifIFD.UserComment] = _exif_user_comment_unicode(title_text)

    try:
        exif_bytes = piexif.dump(exif_dict)
    except Exception as e:
        print(f"piexif.dump failed: {e}", file=sys.stderr)
        return 1

    out_buf = io.BytesIO()
    try:
        piexif.insert(exif_bytes, raw, out_buf)
    except Exception as e:
        print(f"piexif.insert failed: {e}", file=sys.stderr)
        return 1

    final_bytes = out_buf.getvalue()
    if getattr(args, "apple_roll_filename", False):
        out_dir = Path(args.output)
        if out_dir.exists() and out_dir.is_file():
            print(
                "With --apple-roll-filename, --output must be a directory.",
                file=sys.stderr,
            )
            return 1
        out_path = resolve_apple_roll_path(
            out_dir, stem, extension=getattr(args, "apple_extension", "JPG")
        )
    else:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(final_bytes)
    print(f"Wrote {out_path} (DocumentName={stem}, ImageDescription set)")
    return 0


def cmd_png(args: argparse.Namespace) -> int:
    Image, PngImagePlugin = _require_pil()
    src = Path(args.image)
    raw_bytes = src.read_bytes()
    im = Image.open(io.BytesIO(raw_bytes))
    if args.random_stem:
        stem = infer_stem_random()
    elif args.infer_stem:
        stem = infer_stem_png_bytes(raw_bytes)
    else:
        stem = normalize_img_stem(args.stem)

    title_text = args.title if args.title is not None else stem

    meta = PngImagePlugin.PngInfo()
    meta.add_text("Title", title_text)
    # Description often mirrors ImageDescription on Apple exports
    meta.add_text("Description", title_text)

    if getattr(args, "apple_roll_filename", False):
        out_dir = Path(args.output)
        if out_dir.exists() and out_dir.is_file():
            print(
                "With --apple-roll-filename, --output must be a directory.",
                file=sys.stderr,
            )
            return 1
        out_path = resolve_apple_roll_path(
            out_dir, stem, extension=getattr(args, "apple_extension", "PNG")
        )
    else:
        out_path = Path(args.output)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    im.save(out_path, pnginfo=meta)
    print(f"Wrote {out_path} (PNG Title + Description tEXt = {title_text!r})")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="Embed Apple-style document/title metadata (JPEG TIFF tags + PNG Title chunk)."
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_stem_group(sp: argparse.ArgumentParser) -> None:
        g = sp.add_mutually_exclusive_group(required=True)
        g.add_argument(
            "--stem",
            help="Filename-style stem, e.g. 5842 or IMG_5842",
        )
        g.add_argument(
            "--infer-stem",
            action="store_true",
            help="JPEG: derive IMG_XXXX from EXIF date hash; PNG: hash of file bytes",
        )
        g.add_argument(
            "--random-stem",
            action="store_true",
            help="Pick a random IMG_1xxx–IMG_9xxx stem",
        )

    j = sub.add_parser("jpeg", help="Set TIFF DocumentName / ImageDescription (+ optional XPTitle)")
    j.add_argument("--image", required=True)
    j.add_argument("--output", required=True)
    add_stem_group(j)
    j.add_argument(
        "--title",
        default=None,
        help="ImageDescription / display title (default: same as stem)",
    )
    j.add_argument(
        "--xp-title",
        action="store_true",
        help="Also set legacy XPTitle (UTF-16 BE)",
    )
    j.add_argument(
        "--no-apple-device-strings",
        action="store_false",
        dest="apple_device_strings",
        help=(
            "Skip IFD0 Software / HostComputer / Artist / Copyright and Exif UserComment "
            "(these are written by default with Apple-ish values)."
        ),
    )
    j.add_argument(
        "--apple-software",
        default="18.2.1",
        metavar="STR",
        help='IFD0 Software when --apple-device-strings (default: "%(default)s").',
    )
    j.add_argument(
        "--apple-host",
        default="iPhone",
        metavar="STR",
        help='IFD0 HostComputer when --apple-device-strings (default: "%(default)s").',
    )
    j.add_argument(
        "--apple-artist",
        default="",
        metavar="STR",
        help="IFD0 Artist (default: empty; many phone JPEGs omit this).",
    )
    j.add_argument(
        "--apple-copyright",
        default="",
        metavar="STR",
        help="IFD0 Copyright (default: empty).",
    )
    j.add_argument(
        "--user-comment",
        default=None,
        metavar="TEXT",
        help="Exif UserComment (Unicode); overrides default title-based UserComment.",
    )
    j.add_argument(
        "--apple-make",
        default=None,
        metavar="STR",
        help="IFD0 Make (tag 271); overrides EXIF from earlier pipeline steps.",
    )
    j.add_argument(
        "--apple-model",
        default=None,
        metavar="STR",
        help=(
            "IFD0 Model (tag 272); overrides e.g. fixture “iPhone X”. "
            "Prefer --user-comment for long text (Model is often truncated)."
        ),
    )
    j.add_argument(
        "--apple-roll-filename",
        action="store_true",
        help=(
            "Save as DCIM-style IMG_<digits>.JPG inside directory --output "
            "(default extension JPG; see --apple-extension)."
        ),
    )
    j.add_argument(
        "--apple-extension",
        default="JPG",
        metavar="EXT",
        help="File extension when using --apple-roll-filename (default JPG).",
    )
    j.set_defaults(func=cmd_jpeg, apple_device_strings=True)

    n = sub.add_parser("png", help="Set PNG Title (and Description) text chunks")
    n.add_argument("--image", required=True)
    n.add_argument("--output", required=True)
    add_stem_group(n)
    n.add_argument(
        "--title",
        default=None,
        help="PNG Title text (default: same as normalized stem)",
    )
    n.add_argument(
        "--apple-roll-filename",
        action="store_true",
        help=(
            "Save as IMG_<digits>.PNG inside directory --output "
            "(Camera-roll-style basename for PNG exports)."
        ),
    )
    n.add_argument(
        "--apple-extension",
        default="PNG",
        metavar="EXT",
        help="File extension when using --apple-roll-filename (default PNG).",
    )
    n.set_defaults(func=cmd_png)

    args = p.parse_args()
    if getattr(args, "stem", None) is not None and args.stem:
        try:
            normalize_img_stem(args.stem)
        except ValueError as e:
            print(f"Invalid --stem: {e}", file=sys.stderr)
            return 1
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
