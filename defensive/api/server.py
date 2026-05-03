"""FastAPI service for the defensive verify pipeline."""
from __future__ import annotations

import hashlib
import io
import uuid
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from defensive.engine.composite import run as composite_run
from defensive.engine.verdict import Verdict
from defensive.persistence.audit import append as audit_append

app = FastAPI(title="Mendacity Verify", version="1.0")

ALLOWED_MIMES = {"image/jpeg", "image/png", "image/webp"}
MAX_BYTES = 10 * 1024 * 1024  # 10 MB

# Replace with Foundry persistence in Plan D. For v1, in-memory dict so
# GET /v1/verify/{id} can round-trip within a process lifetime.
_artifact_cache: dict[str, dict] = {}


@app.post("/v1/verify")
async def verify(
    image: Annotated[UploadFile, File()],
    operator: Annotated[str, Form()],
    source: Annotated[
        Literal["verify_tab", "telegram_bot", "api_direct"], Form()
    ],
) -> dict:
    if image.content_type not in ALLOWED_MIMES:
        raise HTTPException(
            status_code=400,
            detail={"code": "unsupported_mime", "got": image.content_type},
        )

    image_bytes = await image.read()
    if len(image_bytes) > MAX_BYTES:
        raise HTTPException(
            status_code=400,
            detail={"code": "image_too_large", "max_bytes": MAX_BYTES},
        )

    try:
        from PIL import Image as _PIL_Image, UnidentifiedImageError
        with _PIL_Image.open(io.BytesIO(image_bytes)) as _probe:
            _probe.verify()
    except (UnidentifiedImageError, OSError) as e:
        raise HTTPException(
            status_code=400,
            detail={"code": "image_invalid", "error": type(e).__name__},
        ) from e

    try:
        verdict: Verdict = composite_run(image_bytes, mime_type=image.content_type)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"code": "engine_failed", "error": type(e).__name__},
        ) from e

    artifact_id = str(uuid.uuid4())
    sha = hashlib.sha256(image_bytes).hexdigest()
    submitted_at = datetime.now(timezone.utc).isoformat()

    audit_append(
        artifact_id=artifact_id, sha256=sha,
        operator=operator, source=source, verdict=verdict,
    )

    body = {
        "artifact_id": artifact_id,
        "sha256": sha,
        "verdict": {
            "level": verdict.level.value,
            "confidence": verdict.confidence,
            "summary": verdict.summary,
        },
        "signals": [s.to_dict() for s in verdict.signals],
        "submitted_at": submitted_at,
        "submitted_via": source,
        "operator": operator,
        "thumbnail_uri": None,  # Populated in Plan D (Foundry media-set push).
    }
    _artifact_cache[artifact_id] = body
    return body


@app.get("/v1/verify/{artifact_id}")
async def get_verify(artifact_id: str) -> dict:
    body = _artifact_cache.get(artifact_id)
    if body is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "artifact_not_found", "artifact_id": artifact_id},
        )
    return body
