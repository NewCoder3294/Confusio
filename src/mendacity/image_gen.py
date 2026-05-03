"""Image generation — calls a frontier text-to-image model and writes the
result to disk. v2 uses OpenAI gpt-image-1 (was DALL-E 3).

Why gpt-image-1: DALL-E 3 silently auto-revises prompts toward editorial
polish and ignores "amateur" / "low quality" directives, which destroys our
"random local with a 2015 phone" aesthetic. gpt-image-1 follows prompts
literally, supports a `moderation: "low"` mode for our research scope, and
respects vernacular cues. Cost (medium quality, 1024×1024): ~$0.042 per
image — same order as DALL-E 3 standard.

Provenance note: gpt-image-1 outputs do not carry C2PA Content Credentials
by default, but the downstream pipeline (re-encode + EXIF transplant +
SynthIDBye) still strips any embedded provenance defensively.
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


# Anti-cinematic envelope. gpt-image-1 follows prompts literally so we don't
# need the DALL-E 3 auto-revise bypass; just clean positive descriptors of
# the OUTPUT image (vernacular phone snapshot) without any device/people
# words that could activate phone-in-frame or photographer-in-frame
# imagery. The downstream degrade pass in process_artifact handles
# resolution / noise / tilt deterministically.
_AMATEUR_WRAP = (
    "Eye-level ground-perspective candid still of {subject}. "
    "Shot from a normal standing height looking straight ahead. "
    "Soft focus, slight motion blur, flat dull colors with no color grading "
    "or filter, blown-out overcast daylight with crushed shadows. "
    "Casual off-center framing with the horizon slightly tilted. "
    "Looks like an unedited low-quality casual photo someone uploaded to a "
    "regional news Telegram channel — mundane, raw, ordinary, not "
    "cinematic, not editorial, not staged."
)


def wrap_amateur_prompt(subject: str) -> str:
    """Envelope the operator's subject prompt with vernacular-phone cues."""
    return _AMATEUR_WRAP.format(subject=subject.strip())


def generate_image(
    prompt: str,
    *,
    output_path: Path,
    size: str = "1024x1024",
    quality: str = "medium",
    model: str = "gpt-image-1",
    api_key: str | None = None,
    raw_prompt: bool = False,
) -> GenerationResult:
    """Generate one image and save it to ``output_path`` (PNG).

    Defaults: gpt-image-1, medium quality, 1024×1024. The downstream
    process_artifact pass degrades to 720px and adds noise/blur/tilt to
    finish the phone-quality look.
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

    # gpt-image-1 and dall-e-3 have different parameter shapes. gpt-image-1
    # does not accept response_format (always returns b64_json) and adds
    # moderation/output_format. We branch so the same module supports both
    # for forensic comparison if needed.
    try:
        if model == "gpt-image-1":
            resp = client.images.generate(
                model=model,
                prompt=effective_prompt,
                size=size,
                quality=quality,
                n=1,
                moderation="low",
            )
        else:
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

    p = argparse.ArgumentParser(description="Generate one image via gpt-image-1.")
    p.add_argument("--prompt", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--size", default="1024x1024")
    p.add_argument("--quality", default="medium")
    p.add_argument("--model", default="gpt-image-1")
    p.add_argument(
        "--raw-prompt",
        action="store_true",
        help="Send the operator's prompt verbatim. Default wraps it in an "
        "anti-cinematic amateur-phone envelope.",
    )
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        result = generate_image(
            args.prompt,
            output_path=Path(args.output),
            size=args.size,
            quality=args.quality,
            model=args.model,
            raw_prompt=args.raw_prompt,
        )
    except ImageGenError as exc:
        print(f"image_gen: {exc}", file=sys.stderr)
        return 1
    print(str(result.output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
