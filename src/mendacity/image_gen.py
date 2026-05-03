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


def generate_image(
    prompt: str,
    *,
    output_path: Path,
    size: str = "1024x1024",
    quality: str = "standard",
    model: str = "dall-e-3",
    api_key: str | None = None,
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

    client = OpenAI(api_key=key)
    log.info("generating image: model=%s size=%s quality=%s", model, size, quality)

    try:
        resp = client.images.generate(
            model=model,
            prompt=prompt,
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
