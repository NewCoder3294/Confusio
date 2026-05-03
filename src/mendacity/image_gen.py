"""Image generation — calls a frontier text-to-image model and writes the
result to disk. v1 uses OpenAI DALL-E 3.

Why DALL-E 3 (not Imagen / Gemini): Google models embed SynthID by default,
which would defeat our offensive premise. DALL-E 3 embeds C2PA Content
Credentials, but the downstream pipeline (re-encode + EXIF transplant +
SynthIDBye) strips that during the mission. We deliberately route around
embedded provenance from any source.

Cost: $0.04 per 1024x1024 standard, $0.08 HD. Hackathon budget: <$1 total.
"""

from __future__ import annotations

import base64
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_PATH = REPO_ROOT / "social" / "config" / "api_credentials.env"
load_dotenv(_ENV_PATH)


class ImageGenError(RuntimeError):
    """Raised when image generation fails."""


@dataclass
class GenerationResult:
    output_path: Path
    model: str
    prompt: str
    revised_prompt: str | None
    size: str
    quality: str


# Anti-cinematic envelope. DALL-E 3 silently rewrites prompts toward stock /
# editorial / cinematic aesthetics unless the prompt itself is loaded with
# vernacular cues. The image we want is the kind of photo a panicked local
# would dump into a Telegram channel from a 2015-era phone — not a Reuters
# stringer's frame. Concrete physical artifacts (sensor age, lens smudge,
# JPEG ringing, framing mistakes) outperform abstract directives ("amateur",
# "casual") because the model has training-data anchors for the former.
_AMATEUR_WRAP = (
    # OpenAI's documented auto-revise bypass — keeps DALL-E 3 from silently
    # adding "professional cinematic atmosphere" boilerplate to the prompt.
    "I NEED to test how the tool works with extremely simple prompts. DO NOT "
    "add any detail, just use the prompt AS-IS:\n\n"
    # Pure positive description, no negations. Negations like "no drone view"
    # or "no people holding cameras" actually activate those concepts in
    # DALL-E 3 because the model attends to the noun and ignores the "no".
    # Anchor instead on a concrete, well-known image class the model has
    # strong priors for: low-quality candid news still.
    "Eye-level ground-perspective candid still of {subject}. "
    "Shot from a normal standing height, looking straight ahead. "
    "Soft focus, flat dull colors, blown-out overcast daylight, slight "
    "horizon tilt. Looks like a low-quality casual photo someone uploaded "
    "to a regional news Telegram channel without editing."
)


def wrap_amateur_prompt(subject: str) -> str:
    """Envelope the operator's subject prompt with vernacular-phone cues."""
    return _AMATEUR_WRAP.format(subject=subject.strip())


def generate_image(
    prompt: str,
    *,
    output_path: Path,
    size: str = "1024x1024",
    quality: str = "standard",
    model: str = "dall-e-3",
    api_key: str | None = None,
    raw_prompt: bool = False,
) -> GenerationResult:
    """Generate one image and save it to ``output_path`` (PNG).

    Returns a GenerationResult with the path and metadata. The caller is
    responsible for downstream provenance handling (the OpenAI image will
    contain a C2PA manifest until the mission pipeline strips it).
    """
    key = api_key or os.getenv("OPENAI_API_KEY")
    if not key:
        raise ImageGenError(
            "OPENAI_API_KEY not set. Configure social/config/api_credentials.env."
        )

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ImageGenError(f"openai sdk not installed: {exc}") from exc

    effective_prompt = prompt if raw_prompt else wrap_amateur_prompt(prompt)

    client = OpenAI(api_key=key)
    log.info(
        "generating image: model=%s size=%s quality=%s wrap=%s",
        model, size, quality, "raw" if raw_prompt else "amateur",
    )

    try:
        resp = client.images.generate(
            model=model,
            prompt=effective_prompt,
            size=size,
            quality=quality,
            n=1,
            response_format="b64_json",
        )
    except Exception as exc:
        raise ImageGenError(f"OpenAI image generation failed: {exc}") from exc

    if not resp.data:
        raise ImageGenError("OpenAI returned no image data")

    item = resp.data[0]
    b64 = getattr(item, "b64_json", None)
    if not b64:
        raise ImageGenError("OpenAI response missing b64_json field")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(base64.b64decode(b64))

    revised = getattr(item, "revised_prompt", None)
    log.info("wrote %s (%d bytes)", output_path, output_path.stat().st_size)
    return GenerationResult(
        output_path=output_path,
        model=model,
        prompt=prompt,
        revised_prompt=revised,
        size=size,
        quality=quality,
    )


def _cli(argv: list[str] | None = None) -> int:
    """python -m mendacity.image_gen --prompt "..." --output /path/to/file.png"""
    import argparse
    import sys

    p = argparse.ArgumentParser(description="Generate one image via DALL-E 3.")
    p.add_argument("--prompt", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--size", default="1024x1024")
    p.add_argument("--quality", default="standard")
    p.add_argument(
        "--raw-prompt",
        action="store_true",
        help="Send the operator's prompt verbatim. Default wraps it in an "
        "anti-cinematic amateur-phone envelope so DALL-E doesn't return "
        "stock-photo / editorial output.",
    )
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        result = generate_image(
            args.prompt,
            output_path=Path(args.output),
            size=args.size,
            quality=args.quality,
            raw_prompt=args.raw_prompt,
        )
    except ImageGenError as exc:
        print(f"image_gen: {exc}", file=sys.stderr)
        return 1
    print(str(result.output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
