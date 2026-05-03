"""Merge C2PA, optional Titan, optional Google checks."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mendacity import c2pa_report
from mendacity.google_wm import verify_google_watermark
from mendacity.mime import guess_image_mime
from mendacity.titan import detect_titan_watermark


@dataclass
class AnalyzeOptions:
    run_titan: bool = False
    run_google: bool = False


def _meta(path: Path | None, data: bytes, mime: str) -> dict[str, Any]:
    h = hashlib.sha256(data).hexdigest()
    out: dict[str, Any] = {
        "sha256": h,
        "mime_inferred": mime,
        "size_bytes": len(data),
    }
    if path is not None:
        out["path"] = str(path.resolve())
    return out


def analyze_image(
    *,
    path: Path | str | None = None,
    data: bytes | None = None,
    options: AnalyzeOptions | None = None,
) -> dict[str, Any]:
    """Run ordered checks: C2PA, then optional Titan, optional Google."""
    opts = options or AnalyzeOptions()

    if path is not None:
        p = Path(path)
        raw = p.read_bytes()
        meta_path = p
    elif data is not None:
        raw = data
        meta_path = None
    else:
        raise ValueError("Provide path or data")

    mime = guess_image_mime(raw)

    report: dict[str, Any] = {
        "meta": _meta(meta_path, raw, mime),
        "c2pa": c2pa_report.read_c2pa(mime, raw),
    }

    if opts.run_titan:
        report["titan_watermark"] = detect_titan_watermark(raw)
    else:
        report["titan_watermark"] = {
            "status": "skipped",
            "reason": "Pass run_titan=True or use CLI --titan",
        }

    if opts.run_google:
        report["google_synthid"] = verify_google_watermark(raw)
    else:
        report["google_synthid"] = {
            "status": "skipped",
            "reason": "Pass run_google=True or use CLI --google",
        }

    return report


def report_to_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2)
