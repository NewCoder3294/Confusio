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
"""
from __future__ import annotations

import argparse
import io
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image

log = logging.getLogger(__name__)

GEMINI_IMAGE_MODEL = "gemini-2.5-flash-image"


# ---------------------------------------------------------------------------
# Per-persona perspective
# ---------------------------------------------------------------------------

# Derive a vantage-point hint from a persona profile. Keep this purely
# rule-based — no extra LLM call — so the cascade stays fast and cheap.
def _perspective_for(persona_id: str) -> str:
    pid = persona_id.lower()
    if "olga" in pid:
        return (
            "from a second-floor apartment window looking down through curtains, "
            "slightly obstructed view, indoor reflection visible at the edge"
        )
    if "anton" in pid:
        return (
            "from the driver's seat of a parked beat-up sedan at the side of the "
            "road, dashboard visible at the bottom edge, side-mirror in frame"
        )
    if "dmitry" in pid:
        return (
            "from across the street near a small auto shop entrance, slight "
            "telephoto framing, wires/poles in the upper foreground"
        )
    if "news" in pid or "aggregator" in pid:
        return (
            "telephoto crop of a forwarded social-media post — visible chat-app "
            "letterbox bars, slight JPEG re-compression artifacts"
        )
    return (
        "from a different angle than the source frame — handheld phone, casual, "
        "slight motion blur"
    )


def _prompt_for(seed_prompt: str, persona_id: str) -> str:
    perspective = _perspective_for(persona_id)
    return (
        f"The same scene as: {seed_prompt}. "
        f"But shot {perspective}. "
        f"Same time of day, same subject, plausibly the same incident captured "
        f"by a different bystander. Photorealistic phone capture, "
        f"low-fidelity, no text overlay, no graphics, no logos, documentary."
    )


# ---------------------------------------------------------------------------
# Gemini call
# ---------------------------------------------------------------------------

def _generate_one(mission_id: str, persona_id: str, seed_prompt: str, out_dir: Path) -> Path:
    from google import genai  # lazy

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    client = genai.Client(api_key=api_key)
    prompt = _prompt_for(seed_prompt, persona_id)
    log.info("cascade-image: %s persona=%s", mission_id, persona_id)
    resp = client.models.generate_content(
        model=GEMINI_IMAGE_MODEL,
        contents=[prompt],
    )
    for cand in resp.candidates:
        for part in cand.content.parts:
            inline = getattr(part, "inline_data", None)
            if inline and inline.data:
                png_path = out_dir / f"{mission_id}-{persona_id}.png"
                png_path.write_bytes(inline.data)
                # JPEG mirror: orchestrator prefers .jpg first.
                jpg_path = out_dir / f"{mission_id}-{persona_id}.jpg"
                try:
                    img = Image.open(io.BytesIO(inline.data)).convert("RGB")
                    img.save(jpg_path, format="JPEG", quality=85)
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

    # Run in parallel — Gemini image gen tolerates concurrent requests on a
    # single key and the demo wins seconds from the parallelism.
    with ThreadPoolExecutor(max_workers=min(4, len(persona_ids))) as pool:
        futures = {
            pool.submit(_generate_one, args.mission_id, pid, args.seed_prompt, out_dir): pid
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
