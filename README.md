# Mendacity

Information-layer module of the Mendacity deception platform.

## Components

- [`social/`](./social/README.md) — multi-persona AI Telegram agent (issue #3).
- [`src/mendacity/`](./src/mendacity) — image provenance CLI (see below).

---

## Image Provenance CLI

Small CLI and library to run **image provenance checks** in order:

1. **C2PA / Content Credentials** — read embedded manifests (creator, `c2pa.actions`, validation state) via [`c2pa-python`](https://github.com/contentauth/c2pa-python). Missing C2PA does **not** prove an image is “real”.
2. **Amazon Titan** (optional) — Bedrock **DetectGeneratedContent** for the **Titan Image Generator** invisible watermark only (`--titan`).
3. **Google SynthID signal** (optional) — Vertex AI **WatermarkVerificationModel** (`imageverification@001`) (`--google`, requires `pip install 'mendacity[google]'` and GCP setup).

There is **no single boolean “AI or not”**: each layer answers a different question. Combine signals explicitly; treat negatives as inconclusive for “non‑AI”.

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### Optional: Google / Vertex

```bash
pip install -e ".[google]"
export GOOGLE_CLOUD_PROJECT=your-project
export GOOGLE_CLOUD_LOCATION=us-central1   # optional
# Optional override: GOOGLE_WATERMARK_MODEL=imageverification@001
```

Use Application Default Credentials (`gcloud auth application-default login`) or a service account.

**No GCP project?** The CLI still includes a **Gemini upload** tip when the Google check is skipped: use [Gemini](https://gemini.google.com), attach the image, and ask if it was made with Google AI (in-product SynthID verification; see [Google’s help](https://support.google.com/gemini/answer/16722517)).

### Optional: AWS Titan watermark detection

- Regions commonly documented: `us-east-1`, `us-west-2`.
- IAM permission: `bedrock:DetectGeneratedContent`.
- Env: `AWS_REGION` (or `AWS_DEFAULT_REGION`), standard AWS credentials.
- Optional: `TITAN_WATERMARK_FOUNDATION_MODEL_ID` defaults to `amazon.titan-image-generator-v1`.

Many boto3 releases still lack `bedrock-runtime.detect_generated_content`; this tool falls back to a **SigV4-signed POST** to `/detectGeneratedContent` when the client method is missing.

## Usage

```bash
mendacity-check path/to/image.jpg              # human-readable summary
mendacity-check path/to/image.jpg --json       # full JSON report
mendacity-check path/to/image.jpg --titan      # include Titan watermark check
mendacity-check path/to/image.jpg --google     # include Vertex watermark model
```

**Seeing “no output”?** Cloud checks can take time; progress lines go to **stderr** (`Running Titan…`, `Running Google…`). Force unbuffered IO with `export PYTHONUNBUFFERED=1`. Run everything under `assets/`:

```bash
export PYTHONUNBUFFERED=1
./scripts/check_assets.sh   # or: mendacity-check assets/your.png --json --titan --google
```

### Library

```python
from pathlib import Path
from mendacity import analyze_image
from mendacity.pipeline import AnalyzeOptions

report = analyze_image(
    path=Path("photo.jpg"),
    options=AnalyzeOptions(run_titan=False, run_google=False),
)
```

## Tests

```bash
pytest
```

Integration calls to AWS/Google are **not** run in CI; unit tests mock HTTP for Titan REST.

## References

- [C2PA Python examples](https://opensource.contentauthenticity.org/docs/c2pa-python/docs/examples/)
- [Verify an image watermark (Vertex)](https://cloud.google.com/vertex-ai/generative-ai/docs/image/verify-watermark)
- [Amazon Titan watermark detection](https://docs.aws.amazon.com/bedrock/latest/userguide/titan-image-models.html)
