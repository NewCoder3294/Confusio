"""Artifact prompt seeder.

Wraps a user's subject description with a hardcoded plausibility scaffold
before it reaches DALL-E. The user says WHAT to photograph; we control HOW
that thing should appear so the output looks captured rather than rendered.

Why this matters for anti-detection:

  * AI image detectors key on "studio render" tells: even lighting, sharp
    focus everywhere, perfect skin/material, suspicious symmetry, hand
    artifacts, melted hardware, glowing edges.
  * Forensic analysts cross-check pixel content against the EXIF claim. If
    the EXIF says iPhone at 1/30s ISO 1600 in low light but the pixels show
    a noiseless studio render, the artifact is internally inconsistent and
    fails on the first cross-reference.
  * The cheapest way to defeat both is at generation time, before the
    pixel-level laundering chain runs. Less work for the laundering chain
    means smaller PSNR cost and a higher-fidelity final artifact.

This module is pure. No IO. Tested by inspection.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional


# ─────────────────────────────────────────────────────────────────────────
# The scaffold. Every artifact prompt goes through this.
# ─────────────────────────────────────────────────────────────────────────

ARTIFACT_SYSTEM_PROMPT = """\
You are producing a single still image that must look like a candid photograph
captured on a consumer device in plausible field conditions. The viewer will
believe a real person took this photo with a real camera. Apply every
constraint below to the output:

CAPTURE PLAUSIBILITY (non-negotiable)
- Handheld phone-camera framing: imperfect, slightly tilted, off-center.
- Available-light look: ambient lighting only, no studio rim or key lights.
- Mild lens-level imperfections: very slight motion blur on moving elements,
  modest sensor noise in shadow regions, soft micro-contrast.
- Natural color cast tied to the implied environment (cool fluorescent
  indoors, warm sodium street light at night, overcast diffusion outdoors).
- Imperfect composition: a finger-edge in the frame, partial occlusion,
  reflection off a surface, or a casual crop is appropriate when relevant.

ANTI-AI-TELL CONSTRAINTS (non-negotiable)
- No watermarks, signatures, copyright marks, or platform overlays.
- No glowing effects, no aura, no extreme bokeh, no halo around subjects.
- Hands, eyes, fingernails, ears, teeth, hardware lines, and text edges must
  be photographically plausible (count fingers, keep symmetry believable,
  no melted screens or warped fastener heads).
- No artificially perfect surfaces: real skin has pores and asymmetry, real
  metal has scratches and oxidation, real fabric has lint and creases.
- No high-saturation digital-only colors. Stay within the gamut a phone
  sensor can actually capture.

OUTPUT FRAME
- Single image, no collage, no diptych, no caption, no border, no UI chrome.
- 1024×1024 unless the caller specifies otherwise.

THE OPERATOR HAS DESCRIBED WHAT TO PHOTOGRAPH BELOW. You decide HOW the
candid phone-camera capture of that thing would actually look in real life.

OPERATOR REQUEST:
{user_prompt}\
"""


# ─────────────────────────────────────────────────────────────────────────
# Optional camera-aware addendum derived from the EXIF template.
# ─────────────────────────────────────────────────────────────────────────


@dataclass
class CameraHint:
    make: Optional[str] = None
    model: Optional[str] = None
    iso: Optional[int] = None
    exposure: Optional[str] = None  # human-readable, e.g. "1/30 s"
    focal_length_mm: Optional[float] = None
    f_number: Optional[float] = None
    hour_local: Optional[int] = None  # 0..23, for time-of-day cues

    def lighting_cue(self) -> Optional[str]:
        """Translate ISO + exposure into a plain-English lighting cue."""
        if self.iso is None:
            return None
        if self.iso >= 1600:
            return "low-light handheld"
        if self.iso >= 800:
            return "dim indoor or dusk"
        if self.iso >= 200:
            return "shaded outdoor or overcast"
        return "bright daylight"

    def time_cue(self) -> Optional[str]:
        if self.hour_local is None:
            return None
        h = self.hour_local
        if 5 <= h < 8:
            return "early morning"
        if 8 <= h < 11:
            return "mid morning"
        if 11 <= h < 14:
            return "midday"
        if 14 <= h < 17:
            return "afternoon"
        if 17 <= h < 20:
            return "late afternoon / golden hour"
        if 20 <= h < 23:
            return "evening / dusk"
        return "night"

    def device_cue(self) -> Optional[str]:
        if not (self.make or self.model):
            return None
        parts = [p for p in (self.make, self.model) if p]
        return " ".join(parts)


def parse_camera_hint(exif_template: Mapping[str, Any]) -> CameraHint:
    """Extract a CameraHint from one of our EXIF JSON templates.

    Templates live in ``fixtures/*.json``. Different templates use different
    key shapes; we look up several common spellings and silently skip
    missing fields.
    """
    g = exif_template
    # ExifTool-style flat dict OR nested IFD0/ExifIFD shapes.
    def get(*keys: str) -> Any:
        for k in keys:
            if k in g and g[k] not in (None, "", 0):
                return g[k]
        # Look one level deep for nested structures.
        for v in g.values():
            if isinstance(v, Mapping):
                for k in keys:
                    if k in v and v[k] not in (None, "", 0):
                        return v[k]
        return None

    make = get("Make", "EXIF:Make", "make")
    model = get("Model", "EXIF:Model", "model")

    iso_raw = get("ISO", "ISOSpeedRatings", "PhotographicSensitivity", "iso")
    try:
        iso = int(iso_raw) if iso_raw is not None else None
    except (TypeError, ValueError):
        iso = None

    exposure = get("ExposureTime", "ShutterSpeedValue", "exposure")
    if isinstance(exposure, (int, float)):
        if exposure < 1:
            denom = round(1 / exposure) if exposure > 0 else 0
            exposure = f"1/{denom} s" if denom else None
        else:
            exposure = f"{exposure:g} s"
    elif exposure is not None:
        exposure = str(exposure)

    fl_raw = get("FocalLength", "focal_length")
    try:
        fl = float(str(fl_raw).split()[0]) if fl_raw is not None else None
    except (TypeError, ValueError):
        fl = None

    fn_raw = get("FNumber", "ApertureValue", "f_number")
    try:
        fn = float(fn_raw) if fn_raw is not None else None
    except (TypeError, ValueError):
        fn = None

    # DateTimeOriginal "YYYY:MM:DD HH:MM:SS"
    dt = get("DateTimeOriginal", "DateTime", "CreateDate", "datetime_original")
    hour: Optional[int] = None
    if isinstance(dt, str):
        try:
            time_part = dt.split(" ")[1]
            hour = int(time_part.split(":")[0])
        except (IndexError, ValueError):
            hour = None

    return CameraHint(
        make=str(make) if make else None,
        model=str(model) if model else None,
        iso=iso,
        exposure=exposure,
        focal_length_mm=fl,
        f_number=fn,
        hour_local=hour,
    )


def parse_camera_hint_from_path(path: Path) -> CameraHint:
    """Convenience: read JSON and parse."""
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return CameraHint()
    if not isinstance(data, Mapping):
        return CameraHint()
    return parse_camera_hint(data)


def _build_camera_addendum(hint: CameraHint) -> Optional[str]:
    """Render the camera hint into a few extra lines for the prompt."""
    bits: list[str] = []
    device = hint.device_cue()
    if device:
        bits.append(f"Device claim (must be visually consistent): {device}")
    light = hint.lighting_cue()
    if light:
        bits.append(f"Implied lighting: {light}")
    if hint.iso:
        bits.append(f"ISO ~{hint.iso} (shadow noise should be visible)")
    if hint.exposure:
        bits.append(f"Shutter ~{hint.exposure} (motion implications)")
    if hint.focal_length_mm:
        bits.append(f"Focal length ~{hint.focal_length_mm:g}mm equivalent")
    time = hint.time_cue()
    if time:
        bits.append(f"Time of day: {time}")
    if not bits:
        return None
    body = "\n".join(f"- {b}" for b in bits)
    return f"\nCAMERA / SCENE CONTINUITY (match the EXIF claim)\n{body}"


# ─────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────


def wrap_artifact_prompt(
    user_prompt: str,
    *,
    camera_hint: Optional[CameraHint] = None,
    persona_archetype: Optional[str] = None,
) -> str:
    """Wrap a raw user prompt with the seeded scaffold.

    Parameters
    ----------
    user_prompt:
        What the operator typed (e.g. "leaked regiment movement order").
    camera_hint:
        Optional EXIF-derived hints for visual continuity. If provided, an
        extra block is appended that pins lighting/time/device.
    persona_archetype:
        Optional. If provided, included as low-priority context — the post
        author's archetype (e.g. "delivery driver"), since their phone-photo
        habits constrain plausibility (e.g. dashcam-style framing).
    """
    if not isinstance(user_prompt, str) or not user_prompt.strip():
        raise ValueError("wrap_artifact_prompt: user_prompt must be non-empty.")

    cleaned = user_prompt.strip()

    suffix_blocks: list[str] = []
    if camera_hint is not None:
        addendum = _build_camera_addendum(camera_hint)
        if addendum:
            suffix_blocks.append(addendum)
    if persona_archetype:
        suffix_blocks.append(
            f"\nAUTHOR CONTEXT (low priority)\n"
            f"- The post author is a {persona_archetype}. Their typical "
            "photo habits should constrain framing where reasonable."
        )

    seeded = ARTIFACT_SYSTEM_PROMPT.format(user_prompt=cleaned)
    if suffix_blocks:
        seeded += "\n" + "".join(suffix_blocks)
    return seeded


__all__ = [
    "ARTIFACT_SYSTEM_PROMPT",
    "CameraHint",
    "parse_camera_hint",
    "parse_camera_hint_from_path",
    "wrap_artifact_prompt",
]
