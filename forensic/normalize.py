"""Idempotent JPEG/PNG orientation normalizer.

Bakes EXIF Orientation into pixels and strips the tag, so any downstream
viewer (browser, OS preview, downstream tooling) renders the image upright
without depending on `image-orientation: from-image`.

Idempotent: writes a sibling `<file>.normalized` marker; subsequent runs
short-circuit on the marker. Operators can also force a manual additional
rotation via `--rotate <90|180|270>` which physically rotates and
re-marks.

Usage:
  python -m forensic.normalize <path>
  python -m forensic.normalize <path> --rotate 90
  python -m forensic.normalize <path> --force
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

# EXIF Orientation tag → CCW degrees needed via PIL.rotate to display upright.
# (PIL.rotate is counter-clockwise. EXIF 6 means "rotate 90 CW for display"
# which equals 270 CCW.)
_EXIF_ROTATE_CCW = {3: 180, 6: 270, 8: 90}


def _marker(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".normalized")


def normalize(path: Path, *, force: bool = False, extra_rotate_cw: int = 0) -> str:
    """Normalize one image. Returns one of: skipped, normalized, rotated, no_change.

    - If marker exists and not force/extra: skip.
    - If EXIF Orientation in {3,6,8}: rotate accordingly, strip tag, mark.
    - If extra_rotate_cw given: apply that on top, mark.
    - Otherwise: just mark (no-op pixels).
    """
    if not path.exists():
        return "missing"
    marker = _marker(path)

    if marker.exists() and not force and extra_rotate_cw == 0:
        return "skipped"

    im = Image.open(path)
    original_size = im.size
    ex = im.getexif()
    ori = ex.get(274)
    rotate_ccw = 0
    if ori in _EXIF_ROTATE_CCW:
        rotate_ccw = _EXIF_ROTATE_CCW[ori]
    if extra_rotate_cw:
        # Convert CW to CCW for PIL.
        rotate_ccw = (rotate_ccw + (360 - extra_rotate_cw)) % 360

    changed = False
    if rotate_ccw != 0:
        im = im.rotate(rotate_ccw, expand=True)
        changed = True

    # Strip orientation tag regardless — we've baked rotation into pixels.
    if 274 in ex:
        ex[274] = 1
        changed = True

    fmt = (im.format or "JPEG").upper()
    save_kwargs: dict = {"quality": 92} if fmt == "JPEG" else {}
    if 274 in ex and fmt == "JPEG":
        save_kwargs["exif"] = ex.tobytes()
    if changed or extra_rotate_cw or not marker.exists():
        im.save(path, **save_kwargs)

    marker.touch()
    if extra_rotate_cw:
        return f"rotated:{extra_rotate_cw}cw size {original_size}->{im.size}"
    if rotate_ccw:
        return f"normalized size {original_size}->{im.size}"
    return "no_change"


def _cli(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Normalize image orientation in place.")
    p.add_argument("path", type=Path)
    p.add_argument("--rotate", type=int, default=0, choices=[0, 90, 180, 270],
                   help="Apply additional rotation (degrees CW) on top of EXIF normalization.")
    p.add_argument("--force", action="store_true",
                   help="Re-run normalization even if marker exists.")
    args = p.parse_args(argv)
    try:
        result = normalize(args.path, force=args.force, extra_rotate_cw=args.rotate)
    except Exception as exc:
        print(f"normalize: {exc}", file=sys.stderr)
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
