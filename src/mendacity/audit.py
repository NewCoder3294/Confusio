"""Before/after audit — runs an image through the Mendacity transformation
pipeline and emits a comparison report (input state vs output state).

This is the technical money shot for the demo: take a Gemini-generated
PNG with embedded SynthID watermark and no EXIF, run it through our
pipeline, and emit a structured report showing:

- BEFORE: SHA, MIME, dimensions, EXIF (none), C2PA (none), provenance state
- AFTER:  SHA, MIME, dimensions, EXIF (iPhone), C2PA (none), provenance state
- TRANSFORM: pixels modified, SynthIDBye seed, EXIF template applied
- COMPARISON IMAGE: side-by-side PNG for slide use

Without cloud creds the report shows the structural transformation
(EXIF transplant + SynthIDBye pixel perturbation). With ``--titan``/
``--google`` it adds verified detector flips.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mendacity.mime import guess_image_mime
from mendacity.pipeline import AnalyzeOptions, analyze_image

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
AUDITS_DIR = REPO_ROOT / "missions" / "audits"
DEFAULT_EXIF_TEMPLATE = REPO_ROOT / "fixtures" / "koze_iphonex_gist.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _exif_summary(path: Path) -> dict[str, Any]:
    """Lightweight EXIF/header summary suitable for slide rendering."""
    try:
        from PIL import Image

        import piexif
    except ImportError:
        return {"error": "PIL/piexif not available"}

    out: dict[str, Any] = {"present": False}
    try:
        img = Image.open(path)
        out["dimensions"] = list(img.size)
        out["format"] = img.format
        exif_bytes = img.info.get("exif")
        if exif_bytes:
            d = piexif.load(exif_bytes)
            ifd0 = d.get("0th", {})

            def _decode(tag: int) -> str | None:
                v = ifd0.get(tag)
                if v is None:
                    return None
                if isinstance(v, bytes):
                    try:
                        return v.decode("utf-8", "ignore").strip("\x00 ")
                    except Exception:
                        return repr(v)
                return str(v)

            out["present"] = True
            out["make"] = _decode(piexif.ImageIFD.Make)
            out["model"] = _decode(piexif.ImageIFD.Model)
            out["software"] = _decode(piexif.ImageIFD.Software)
            out["datetime"] = _decode(piexif.ImageIFD.DateTime)
            out["gps_present"] = bool(d.get("GPS"))
        return out
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def _pixel_diff(before: Path, after: Path) -> dict[str, Any]:
    """Compute fraction of pixels modified and mean per-pixel intensity delta.
    Returns dict with ``pct_modified``, ``mean_delta``, ``method``.
    """
    try:
        from PIL import Image
    except ImportError:
        return {"error": "PIL not available"}

    a = Image.open(before).convert("RGB")
    b = Image.open(after).convert("RGB")
    if a.size != b.size:
        b = b.resize(a.size)

    a_data = list(a.getdata())
    b_data = list(b.getdata())
    n = len(a_data)
    modified = 0
    delta_sum = 0
    for (r1, g1, b1), (r2, g2, b2) in zip(a_data, b_data):
        d = abs(r1 - r2) + abs(g1 - g2) + abs(b1 - b2)
        if d > 0:
            modified += 1
        delta_sum += d
    return {
        "pct_modified": round(100 * modified / n, 2),
        "mean_delta": round(delta_sum / n, 3),
        "method": "PIL RGB sum-abs-delta",
        "pixels_total": n,
    }


def _side_by_side(before: Path, after: Path, out_path: Path, *, label_top: str = "BEFORE — adversary view", label_bot: str = "AFTER — Mendacity-transformed") -> Path:
    """Compose a labeled side-by-side PNG for slide rendering."""
    from PIL import Image, ImageDraw, ImageFont

    a = Image.open(before).convert("RGB")
    b = Image.open(after).convert("RGB")

    # Normalize heights for clean side-by-side
    target_h = min(a.height, b.height, 600)
    a_w = int(a.width * (target_h / a.height))
    b_w = int(b.width * (target_h / b.height))
    a = a.resize((a_w, target_h))
    b = b.resize((b_w, target_h))

    pad = 40
    label_h = 60
    canvas_w = a_w + b_w + 3 * pad
    canvas_h = target_h + label_h + 2 * pad

    canvas = Image.new("RGB", (canvas_w, canvas_h), (16, 16, 18))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 22)
        font_small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
    except Exception:
        font = ImageFont.load_default()
        font_small = font

    canvas.paste(a, (pad, pad))
    canvas.paste(b, (pad * 2 + a_w, pad))
    draw.text((pad, pad + target_h + 16), label_top, fill=(220, 60, 60), font=font)
    draw.text(
        (pad * 2 + a_w, pad + target_h + 16), label_bot, fill=(80, 200, 120), font=font
    )
    draw.text(
        (pad, pad + target_h + 40), "Gemini-generated • SynthID embedded • no EXIF", fill=(180, 180, 180), font=font_small
    )
    draw.text(
        (pad * 2 + a_w, pad + target_h + 40), "iPhone X EXIF transplanted • SynthID stripped • re-encoded", fill=(180, 180, 180), font=font_small
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, format="PNG")
    return out_path


@dataclass
class AuditResult:
    audit_id: str
    started_at: str
    input: dict[str, Any]
    output: dict[str, Any]
    transform: dict[str, Any]
    provenance_before: dict[str, Any]
    provenance_after: dict[str, Any]
    comparison_image_path: str | None
    verdict: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "audit_id": self.audit_id,
            "started_at": self.started_at,
            "input": self.input,
            "output": self.output,
            "transform": self.transform,
            "provenance_before": self.provenance_before,
            "provenance_after": self.provenance_after,
            "comparison_image_path": self.comparison_image_path,
            "verdict": self.verdict,
        }


def run_audit(
    input_path: Path,
    *,
    exif_template: Path | None = None,
    audits_dir: Path | None = None,
    run_titan: bool = False,
    run_google: bool = False,
) -> AuditResult:
    """Transform ``input_path`` through the Mendacity pipeline and emit a
    structured before/after report.
    """
    input_path = Path(input_path).resolve()
    if not input_path.exists():
        raise FileNotFoundError(input_path)

    audits_dir = audits_dir or AUDITS_DIR
    audit_id = (
        f"AUDIT-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-"
        f"{_sha256(input_path)[:8]}"
    )
    work_dir = audits_dir / audit_id
    work_dir.mkdir(parents=True, exist_ok=True)

    exif_template = exif_template or DEFAULT_EXIF_TEMPLATE
    if not exif_template.exists():
        raise FileNotFoundError(f"EXIF template missing: {exif_template}")

    # Stage 0: capture BEFORE state
    before_jpeg = work_dir / "before.jpg"
    # Re-encode to JPEG so PIL EXIF readers behave consistently when the
    # input is a PNG. This does not alter the comparison: the BEFORE image
    # we display is the original; only metadata extraction uses this copy.
    if input_path.suffix.lower() == ".png":
        from PIL import Image
        Image.open(input_path).convert("RGB").save(before_jpeg, "JPEG", quality=95)
    else:
        shutil.copyfile(input_path, before_jpeg)

    before_meta = {
        "path": str(input_path),
        "mime": guess_image_mime(input_path.read_bytes()),
        "sha256": _sha256(input_path),
        "size_bytes": input_path.stat().st_size,
        "exif": _exif_summary(input_path),
    }
    prov_before = analyze_image(
        path=before_jpeg,
        options=AnalyzeOptions(run_titan=run_titan, run_google=run_google),
    )

    # Stage 1: SynthIDBye watermark strip
    stripped = work_dir / "stripped.jpg"
    cmd = ["npx", "tsx", "scripts/synthidbye_run.ts", str(before_jpeg), str(stripped)]
    proc = subprocess.run(
        cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=180
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"SynthIDBye failed (rc={proc.returncode}): {proc.stderr.strip()[:500]}"
        )
    # Capture seed from stderr for reproducibility.
    seed_line = next(
        (l for l in proc.stderr.splitlines() if "seed" in l.lower()), ""
    )

    # Stage 2: EXIF transplant — produces the "after" image.
    after_jpeg = work_dir / "after.jpg"
    cmd2 = [
        sys.executable,
        "scripts/apply_jpeg_exif.py",
        "from-json",
        "--json", str(exif_template),
        "--image", str(stripped),
        "--output", str(after_jpeg),
        "--reencode-jpeg",
    ]
    proc2 = subprocess.run(
        cmd2, cwd=REPO_ROOT, capture_output=True, text=True, timeout=60
    )
    if proc2.returncode != 0:
        raise RuntimeError(
            f"EXIF transplant failed (rc={proc2.returncode}): "
            f"{proc2.stderr.strip()[:500]}"
        )

    # Stage 3: capture AFTER state
    after_meta = {
        "path": str(after_jpeg),
        "mime": guess_image_mime(after_jpeg.read_bytes()),
        "sha256": _sha256(after_jpeg),
        "size_bytes": after_jpeg.stat().st_size,
        "exif": _exif_summary(after_jpeg),
    }
    prov_after = analyze_image(
        path=after_jpeg,
        options=AnalyzeOptions(run_titan=run_titan, run_google=run_google),
    )

    # Stage 4: pixel diff
    pixel = _pixel_diff(before_jpeg, after_jpeg)

    # Stage 5: composed comparison PNG
    comparison_path = work_dir / "comparison.png"
    try:
        _side_by_side(input_path, after_jpeg, comparison_path)
        comparison_str: str | None = str(comparison_path)
    except Exception as exc:  # pragma: no cover - PIL/font issues
        log.warning("comparison render failed: %s", exc)
        comparison_str = None

    # Verdict
    verdict_lines = []
    e_before = before_meta["exif"]
    e_after = after_meta["exif"]
    verdict_lines.append(
        f"EXIF: {e_before.get('make') or '<none>'}/{e_before.get('software') or '<none>'} "
        f"-> {e_after.get('make') or '<none>'}/{e_after.get('software') or '<none>'}"
    )
    verdict_lines.append(
        f"C2PA: {prov_before.get('c2pa', {}).get('status')} -> "
        f"{prov_after.get('c2pa', {}).get('status')}"
    )
    if run_google:
        verdict_lines.append(
            f"SynthID: {prov_before.get('google_synthid', {}).get('watermark_verification_result', '<n/a>')} -> "
            f"{prov_after.get('google_synthid', {}).get('watermark_verification_result', '<n/a>')}"
        )
    if run_titan:
        verdict_lines.append(
            f"Titan: {prov_before.get('titan_watermark', {}).get('detectionResult', '<n/a>')} -> "
            f"{prov_after.get('titan_watermark', {}).get('detectionResult', '<n/a>')}"
        )
    verdict_lines.append(
        f"Pixels modified: {pixel.get('pct_modified')}% "
        f"(mean RGB delta: {pixel.get('mean_delta')})"
    )
    verdict = " | ".join(verdict_lines)

    result = AuditResult(
        audit_id=audit_id,
        started_at=_now_iso(),
        input=before_meta,
        output=after_meta,
        transform={
            "synthidbye_seed_log": seed_line.strip(),
            "exif_template": str(exif_template),
            "pixel_diff": pixel,
        },
        provenance_before=prov_before,
        provenance_after=prov_after,
        comparison_image_path=comparison_str,
        verdict=verdict,
    )

    # Write atomic JSON
    out_json = work_dir / "audit.json"
    tmp = out_json.with_suffix(out_json.suffix + ".tmp")
    tmp.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    tmp.replace(out_json)
    return result
