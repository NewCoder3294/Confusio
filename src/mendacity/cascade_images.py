"""Per-corroborator artifact images.

For each non-seed cast member, generate a Gemini image of the SAME scene as
the seed but from that persona's vantage point — making the multi-witness
cascade visually plausible. Outputs land at::

  missions/generated/{mission_id}-{persona_id}.png
  missions/generated/{mission_id}-{persona_id}.jpg   (alias for orchestrator)

The orchestrator picks them up automatically when posting that
corroborator's reply.

Why Gemini and not gpt-image-1: cost (free tier today) and latency (~3-5s
vs 12-18s) — the cascade has to feel snappy in a live demo.

Quality matching: we pass the seed image to Gemini as visual reference so
the corroborator perspectives inherit the seed's aesthetic (low-fidelity,
amateur phone capture, similar lighting, similar compression). Without that
reference, Gemini renders cinematic golden-hour images that betray the
"random bystander" framing.
"""
from __future__ import annotations

import argparse
import io
import logging
import mimetypes
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image
from dotenv import load_dotenv

log = logging.getLogger(__name__)

# Load credentials from the social config the same way image_gen.py does so
# this module works whether spawned from Next.js (no env), the orchestrator,
# or invoked directly from a shell.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_PATH = _REPO_ROOT / "social" / "config" / "api_credentials.env"
load_dotenv(_ENV_PATH)

GEMINI_IMAGE_MODEL = "gemini-2.5-flash-image"


# ---------------------------------------------------------------------------
# Per-persona perspective
# ---------------------------------------------------------------------------

# Vantage-point hint per persona profile. Kept short so the camera-quality
# directives in the prompt template aren't crowded out.
def _perspective_for(persona_id: str) -> str:
    pid = persona_id.lower()
    if "olga" in pid:
        return "from the opposite side of the street at sidewalk level, a parked car partly visible in the foreground"
    if "anton" in pid:
        return "from the driver's seat of a parked old sedan, dashboard visible at the bottom"
    if "dmitry" in pid:
        return "from across the street near a small auto shop, wires and a power pole in the upper foreground"
    if "news" in pid or "aggregator" in pid:
        return "as a re-shared screenshot of a chat-app message — letterbox bars, extra JPEG compression"
    if "mariya" in pid:
        return "from across a small park looking past a low fence, slight foreground blur from chain-link"
    if "pavel" in pid:
        return "from a slightly elevated vantage point further down the street, telephoto compression"
    return "from a different bystander angle on the same scene, handheld phone, slight motion blur, no window or curtain framing"


def _prompt_for(seed_prompt: str, persona_id: str, has_reference: bool) -> str:
    perspective = _perspective_for(persona_id)
    quality = (
        "Match the camera quality, lighting, time of day, weather, and overall "
        "aesthetic of the reference image exactly. The reference is a low-quality "
        "amateur phone snap — slightly blurry, slight motion blur, mediocre dynamic "
        "range, JPEG compression artifacts, no cinematic styling. Reproduce that "
        "look. Do not improve the lighting. Do not make it look professional."
        if has_reference
        else "Low-fidelity amateur phone snap. Slightly blurry. Slight motion blur. "
        "JPEG compression. Mediocre dynamic range. No cinematic styling. No bokeh. "
        "No golden-hour drama. Documentary, ugly, accidental."
    )
    return (
        f"Render the SAME real-world scene as the reference (if shown): {seed_prompt}. "
        f"Shot {perspective}. "
        f"{quality} "
        f"Same time of day, same subject, same weather and lighting as the reference. "
        f"This is the same incident captured by a different bystander on the same kind of phone. "
        f"No text overlay, no logos, no graphics, no UI elements."
    )


# ---------------------------------------------------------------------------
# Gemini call
# ---------------------------------------------------------------------------

def _resolve_seed_image(out_dir: Path, mission_id: str) -> Path | None:
    """Find the seed artifact image in out_dir. Prefer the EXIF-transplanted
    JPEG (closest to what the channel sees), fall back to the raw PNG."""
    for ext in ("jpg", "png"):
        p = out_dir / f"{mission_id}.{ext}"
        if p.exists() and p.stat().st_size > 0:
            return p
    return None


def _generate_one(
    mission_id: str,
    persona_id: str,
    seed_prompt: str,
    out_dir: Path,
    seed_image_path: Path | None,
) -> Path:
    from google import genai  # lazy
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    client = genai.Client(api_key=api_key)

    has_ref = seed_image_path is not None
    prompt = _prompt_for(seed_prompt, persona_id, has_reference=has_ref)
    contents: list = [prompt]
    if has_ref:
        mime, _ = mimetypes.guess_type(str(seed_image_path))
        if not mime:
            mime = "image/jpeg" if seed_image_path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
        contents.append(
            types.Part.from_bytes(
                data=seed_image_path.read_bytes(), mime_type=mime
            )
        )
    log.info(
        "cascade-image: %s persona=%s ref=%s",
        mission_id, persona_id, seed_image_path.name if has_ref else "none",
    )
    resp = client.models.generate_content(
        model=GEMINI_IMAGE_MODEL,
        contents=contents,
    )
    for cand in resp.candidates:
        for part in cand.content.parts:
            inline = getattr(part, "inline_data", None)
            if inline and inline.data:
                png_path = out_dir / f"{mission_id}-{persona_id}.png"
                png_path.write_bytes(inline.data)
                # JPEG mirror at moderate quality so it actually shows the
                # compression artifacts the prompt asked for.
                jpg_path = out_dir / f"{mission_id}-{persona_id}.jpg"
                try:
                    img = Image.open(io.BytesIO(inline.data)).convert("RGB")
                    img.save(jpg_path, format="JPEG", quality=78)
                except Exception:
                    log.exception("jpeg mirror failed for %s", png_path)
                return png_path
    raise RuntimeError(f"no image returned by Gemini for {mission_id}-{persona_id}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mission-id", required=True)
    parser.add_argument("--seed-prompt", required=True)
    parser.add_argument(
        "--personas",
        required=True,
        help="Comma-separated persona ids (corroborators only, no seed).",
    )
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=os.getenv("MENDACITY_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    persona_ids = [p.strip() for p in args.personas.split(",") if p.strip()]
    if not persona_ids:
        log.warning("no persona ids supplied; nothing to do")
        return 0

    seed_image_path = _resolve_seed_image(out_dir, args.mission_id)
    if seed_image_path is None:
        log.warning(
            "seed image not found in %s for %s — proceeding text-only "
            "(quality match will be weaker)",
            out_dir, args.mission_id,
        )

    # Run in parallel — Gemini image gen tolerates concurrent requests on a
    # single key and the demo wins seconds from the parallelism.
    with ThreadPoolExecutor(max_workers=min(4, len(persona_ids))) as pool:
        futures = {
            pool.submit(
                _generate_one,
                args.mission_id,
                pid,
                args.seed_prompt,
                out_dir,
                seed_image_path,
            ): pid
            for pid in persona_ids
        }
        any_failed = False
        for fut in as_completed(futures):
            pid = futures[fut]
            try:
                path = fut.result()
                log.info("cascade-image done: %s", path)
            except Exception as exc:
                log.exception("cascade-image failed for persona %s: %s", pid, exc)
                any_failed = True
    return 0 if not any_failed else 2


if __name__ == "__main__":
    sys.exit(main())
