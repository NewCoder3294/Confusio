"""Amazon Bedrock: Titan Image Generator invisible watermark detection."""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest


def _sigv4_json_post(url: str, body: bytes, region: str) -> dict[str, Any]:
    session = boto3.Session()
    creds = session.get_credentials()
    if creds is None:
        raise RuntimeError(
            "No AWS credentials found (configure env, ~/.aws/credentials, or IAM role)."
        )

    parsed = urllib.parse.urlparse(url)
    request = AWSRequest(
        method="POST",
        url=url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Host": parsed.netloc,
        },
    )
    SigV4Auth(creds, "bedrock-runtime", region).add_auth(request)

    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers=dict(request.headers),
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = resp.read()
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} from Bedrock: {err_body}") from e

    return json.loads(payload.decode("utf-8"))


def _rest_detect_generated_content(
    *,
    region: str,
    foundation_model_id: str,
    image_bytes: bytes,
) -> dict[str, Any]:
    """Call DetectGeneratedContent when boto3 does not yet expose the operation."""
    body_obj = {
        "foundationModelId": foundation_model_id,
        "content": {
            "imageContent": {"bytes": base64.b64encode(image_bytes).decode("ascii")}
        },
    }
    body = json.dumps(body_obj).encode("utf-8")
    host = f"bedrock-runtime.{region}.amazonaws.com"
    url = f"https://{host}/detectGeneratedContent"
    return _sigv4_json_post(url, body, region)


def detect_titan_watermark(
    image_bytes: bytes,
    *,
    region: str | None = None,
    foundation_model_id: str | None = None,
) -> dict[str, Any]:
    """
    Ask Bedrock whether a Titan Image Generator G1 watermark is present.

    Requires IAM permission ``bedrock:DetectGeneratedContent`` and credentials.
    Supported regions per AWS docs historically include ``us-east-1`` and ``us-west-2``.
    """
    region = region or os.environ.get("AWS_REGION") or os.environ.get(
        "AWS_DEFAULT_REGION", "us-east-1"
    )
    foundation_model_id = foundation_model_id or os.environ.get(
        "TITAN_WATERMARK_FOUNDATION_MODEL_ID", "amazon.titan-image-generator-v1"
    )

    client = boto3.client("bedrock-runtime", region_name=region)
    fn = getattr(client, "detect_generated_content", None)
    if callable(fn):
        try:
            resp = fn(
                foundationModelId=foundation_model_id,
                content={"imageContent": {"bytes": image_bytes}},
            )
            return {"status": "ok", "source": "boto3.detect_generated_content", **resp}
        except Exception as e:
            return {
                "status": "error",
                "detail": str(e),
                "hint": "Ensure IAM allows bedrock:DetectGeneratedContent in this region.",
            }

    try:
        resp = _rest_detect_generated_content(
            region=region,
            foundation_model_id=foundation_model_id,
            image_bytes=image_bytes,
        )
        return {"status": "ok", "source": "rest.detectGeneratedContent", **resp}
    except Exception as e:
        return {
            "status": "error",
            "detail": str(e),
            "hint": "Verify region support, IAM policy, and endpoint /detectGeneratedContent.",
        }
