# Mendacity

Information-layer module of the Mendacity deception platform — an offensive synthetic-deception toolchain built for U.S. Army intelligence (Title 10, foreign actors only) for the 3rd Annual NATSEC Hackathon at Cerebral Valley.

## Components

- [`src/mendacity/mission*`](./src/mendacity) — **mission orchestrator** (`mendacity-mission`): plan → generate → strip → EXIF-transplant → provenance-grade → deliver.
- [`src/mendacity/audit.py`](./src/mendacity/audit.py) — before/after audit report generator (`mendacity-mission audit`).
- [`src/mendacity/pipeline.py`](./src/mendacity/pipeline.py) — provenance check engine: C2PA + Titan + SynthID.
- [`social/`](./social/README.md) — multi-persona Telegram delivery layer (Telethon, dossier-grade Streamlit operator console).
- [`scripts/synthidbye_run.ts`](./scripts/synthidbye_run.ts) + [`vendor/SynthIDBye/`](./vendor/SynthIDBye) — watermark stripping for adversary-evasion.

---

## Mission CLI

End-to-end mission orchestration. A single command takes a free-text operator intent or a structured YAML spec and produces a sandbox-delivered, provenance-graded artifact.

### Subcommands

| Command | Purpose |
|---|---|
| `mendacity-mission run <spec.yaml>` | Execute one mission, write result to `missions/results/`. |
| `mendacity-mission watch [--workers N]` | Daemon: poll `missions/inbox/`, process new specs (parallel optional). |
| `mendacity-mission plan "<intent>"` | LLM-convert operator intent into a strict MissionSpec YAML. |
| `mendacity-mission status <id>` | One-line status of a completed mission. |
| `mendacity-mission grade <result.json>` | Re-print pass/fail summary. |
| `mendacity-mission audit <image>` | Before/after transform report on any image. |
| `mendacity-mission audit-mission <id>` | Re-audit a completed mission's source artifact. |
| `mendacity-mission match-persona "<archetype>"` | Resolve archetype to best-matching persona via LLM. |
| `mendacity-mission personas` | List available personas with live Telegram session status. |
| `mendacity-mission login <id>` | Re-authenticate an expired Telethon persona session (interactive — needs SMS code). |

### Mission flow (the engine)

Each mission progresses through these stages:

1. `validated` — schema check + Title 10 + foreign target_class + sandbox allowlist
2. `preflight` — persona session liveness check (live deliveries only)
3. `persona_generated` — fabricates persona + (optional) DALL-E avatar
4. `artifact_selected` — generates image via DALL-E 3 OR copies a fixture
5. `watermark_strip` — runs SynthIDBye to defeat AI-watermark detection
6. `exif_transplant` — applies a real-camera EXIF profile (e.g., iPhone X)
7. `provenance_check` — runs C2PA + (optional) Titan + (optional) SynthID
8. `regen_attempt` (if needed) — re-runs strip + EXIF + check up to N times on grading failure
9. `delivered` — Telegram post with image attached (or `dry_run` skip)

### Mission spec example

See [`missions/example.yaml`](./missions/example.yaml). All hard constraints (`title-10`, `foreign`, `must_pass: [c2pa, titan, synthid]`) are enforced at validation; specs that violate them are aborted before any work runs.

### Sandbox allowlist

Engine refuses any mission whose `target.channel` is not in [`missions/sandbox_channels.json`](./missions/sandbox_channels.json). This is the Title-10 sandbox boundary.

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
