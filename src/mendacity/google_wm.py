"""Google Vertex AI: Imagen / SynthID watermark verification (optional)."""

from __future__ import annotations

import os
from typing import Any

# Official sample index (Python):
# https://cloud.google.com/vertex-ai/generative-ai/docs/samples/generativeaionvertexai-imagen-verify-image-watermark
# Model ID from googleapis/python-aiplatform tests: publishers/google/models/imageverification@001

_GEMINI_UPLOAD_HINT = (
    "Without Vertex: open the Gemini app (gemini.google.com), upload this image, and ask "
    "whether it was created or edited with Google AI — that runs Google's SynthID check in-product. "
    "You can try @synthid where supported. "
    "https://support.google.com/gemini/answer/16722517"
)


def verify_google_watermark(image_bytes: bytes) -> dict[str, Any]:
    """
    Run Vertex AI WatermarkVerificationModel (SynthID signal for Google-generated media).

    Requires ``pip install 'mendacity[google]'``, GCP project, ADC or service account,
    and Vertex AI API enabled. Set ``GOOGLE_CLOUD_PROJECT`` and ``GOOGLE_CLOUD_LOCATION``
    (default ``us-central1``).
    """
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        return {
            "status": "skipped",
            "reason": "GOOGLE_CLOUD_PROJECT not set",
            "gemini_upload_hint": _GEMINI_UPLOAD_HINT,
            "docs": "https://cloud.google.com/vertex-ai/generative-ai/docs/image/verify-watermark",
        }

    try:
        import vertexai  # type: ignore
        from vertexai.preview.vision_models import (  # type: ignore
            Image,
            WatermarkVerificationModel,
        )
    except ImportError:
        return {
            "status": "skipped",
            "reason": "google-cloud-aiplatform not installed",
            "hint": "pip install 'mendacity[google]'",
            "gemini_upload_hint": _GEMINI_UPLOAD_HINT,
        }

    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    model_name = os.environ.get("GOOGLE_WATERMARK_MODEL", "imageverification@001")

    try:
        vertexai.init(project=project, location=location)
        model = WatermarkVerificationModel.from_pretrained(model_name)
        img = Image(image_bytes=image_bytes)
        result = model.verify_image(img)
        likelihood = getattr(result, "watermark_verification_result", None)
        raw = getattr(result, "_prediction_response", None)
        predictions = {}
        if raw is not None and hasattr(raw, "predictions"):
            predictions = {"predictions": raw.predictions}
        return {
            "status": "ok",
            "model": model_name,
            "location": location,
            "watermark_verification_result": likelihood,
            "vertex_response_excerpt": predictions,
        }
    except Exception as e:
        return {
            "status": "error",
            "detail": str(e),
            "docs": "https://cloud.google.com/vertex-ai/generative-ai/docs/image/verify-watermark",
        }
