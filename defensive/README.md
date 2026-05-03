# defensive/

Defensive arm of Mendacity — image validation against the same detector
stack used offensively. Mirrors the layout of `forensic/`.

## Install

```bash
cd defensive
pip install -r requirements.txt
```

## Run the API

```bash
uvicorn defensive.api.server:app --host 127.0.0.1 --port 8788
```

Override port via `DEFENSIVE_API_PORT` (consumed by API, bot, and Next.js
proxy so all three agree without configuration drift).

## Run the tests

```bash
pytest defensive/tests -v
```

## Lane discipline

Never edits `src/mendacity/`, `social/`, `forensic/`, `palantir/`, or
`frontend/`. Imports read-only from `src/mendacity/{c2pa_report,titan,
google_wm,audit}.py`.

## Status

- Engine: 7 detectors (c2pa, synthid, titan, ai_classifier, exif, ela, phash)
  with composite verdict and weighted-evidence confidence.
- API: `POST /v1/verify`, `GET /v1/verify/{id}`. Bound to `127.0.0.1:8788`,
  override via `DEFENSIVE_API_PORT`.
- Persistence: append-only JSONL at `defensive/audit.jsonl`
  (override via `DEFENSIVE_AUDIT_PATH`). Foundry persistence ships in Plan D.

## Next plans

- **Plan B** — Frontend Verify tab + Next.js proxy route.
- **Plan C** — Telegram bot.
- **Plan D** — Foundry ontology (`InboundArtifact`, `InboundDetection`),
  Workshop module, `palantir/defensive/` ontology spec, `foundry_writer`.
