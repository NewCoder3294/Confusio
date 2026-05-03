# Verify — defensive image validation tab + bot

**Status:** Design approved 2026-05-03
**Owner (this session):** Palantir / defensive lane
**Parallel sessions:** Mission, Agents (do not touch their lanes)

## Problem

Mendacity's offensive arm generates synthetic imagery and self-grades it against the same provenance-detection stack an adversary would deploy (C2PA, Amazon Titan watermark, Google SynthID). There is no inverse surface — nowhere for an operator to drop an inbound image and ask "is this real?" with the same evidentiary weight the rest of the toolchain operates with.

Verify is the defensive arm of the same toolchain: a central tab in the operator console plus a callable Telegram bot, both backed by one HTTP API and one detection engine, both producing operator-grade dossier-style verdicts that persist as first-class entities in Foundry.

## Goals

- Operator can drop a single image into a tab and receive a dossier-style verdict in under 3 seconds.
- An external user, restricted to a whitelist, can DM the same image to a Telegram bot and get the same verdict.
- Every verification is recorded as a first-class Foundry object (`InboundArtifact` + N `InboundDetection` rows) and a line in the existing append-only audit log.
- Composite verdict synthesises seven independent detection signals so the operator can see *why* the verdict landed where it landed.
- One detector failure never kills the request — partial verdicts are first-class.

## Non-goals (v1)

- Batch verify (multi-image upload, folder ingest)
- Re-running detectors against an existing artifact
- Cross-mission linking from `InboundArtifact` to `Mission`
- Hosted-API detectors (Hive, Reality Defender, Sightengine) — disqualified for the data-handoff reason
- URL inputs (`POST /verify` accepting a `url=` field)
- Clipboard paste / drag-from-browser
- Public, non-whitelisted bot operation

## Decisions (locked during brainstorm)

| # | Decision | Choice |
|---|---|---|
| 1 | What "validity" means | Composite of authenticity + integrity + provenance, all signals exposed |
| 2 | Bot surface shape | HTTP API as the contract, Telegram bot as the first chat shim |
| 3 | Detection stack | C2PA + SynthID + Titan + local AI-gen classifier (Organika/sdxl-detector) + EXIF forensics + ELA + perceptual-hash lookup |
| 4 | Persistence model | New Foundry ontology pair: `InboundArtifact` 1—N `InboundDetection`, plus existing audit log |
| 5 | Code home | New top-level `defensive/` (sibling of `forensic/`) + `palantir/defensive/` for ontology and Workshop spec |
| 6 | Central-tab input modes | File upload only (drag/drop or picker) |
| 7 | Tab name + nav slot | "Verify", right-end of nav (the slot vacated by Runbook) |
| 8 | Bot identity / auth | Whitelisted Telegram user IDs → mapped operator identities |
| 9 | Verdict UI | Dossier layout (numbered sections, prose conclusions, dossier metadata header) |

## Architecture

Three surfaces all call into one stateless detection engine. The engine reduces seven detector signals into one Verdict and persists it via Foundry's existing bridge plus the audit log.

```
                  ┌──────────────────┐  ┌────────────────────┐  ┌──────────────────┐
                  │  /verify (Tab)   │  │ @verify_bot (TG)   │  │ POST /verify     │
                  │  Next.js page    │  │ python-telegram-bot│  │ FastAPI          │
                  └────────┬─────────┘  └─────────┬──────────┘  └────────┬─────────┘
                           │                      │                       │
                           └──────────────────────┴───────────────────────┘
                                                  │
                                  ┌───────────────▼────────────────┐
                                  │ defensive/engine/composite.py  │
                                  │ Runs 7 detectors in parallel,  │
                                  │ reduces to Verdict             │
                                  └───────────────┬────────────────┘
                                                  │
                          ┌───────────────────────┴────────────────────────┐
                          ▼                                                ▼
              ┌───────────────────────────┐                  ┌────────────────────────────┐
              │ InboundArtifact + N       │                  │ src/mendacity/audit.py     │
              │ InboundDetection rows in  │                  │ append-only line per verify│
              │ Foundry (via existing     │                  │                            │
              │ palantir/bridge/...)      │                  └────────────────────────────┘
              └───────────────────────────┘
```

## Lane discipline

| Owns | Path |
|---|---|
| This session | `defensive/`, `palantir/defensive/`, `frontend/src/app/verify/` |
| Read-only imports | `src/mendacity/{c2pa_report,titan,google_wm,audit}.py` |
| Never touched | `src/mendacity/` (writes), `social/`, `forensic/`, other agents' frontend pages |

## Components

```
defensive/
├── engine/
│   ├── composite.py          # orchestrator: runs detectors in parallel, builds Verdict
│   ├── verdict.py            # Verdict, DetectorSignal, Severity dataclasses
│   └── detectors/
│       ├── c2pa.py           # wraps src/mendacity/c2pa_report.py
│       ├── synthid.py        # wraps src/mendacity/google_wm.py
│       ├── titan.py          # wraps src/mendacity/titan.py
│       ├── ai_classifier.py  # HF Organika/sdxl-detector, lazy-loaded, warmed at boot
│       ├── exif.py           # exifread + suspicious-tag heuristics (Software field, missing EXIF, etc.)
│       ├── ela.py            # PIL-based error level analysis
│       └── phash.py          # imagehash + local stock-corpus lookup
├── api/
│   └── server.py             # FastAPI: POST /verify, GET /verify/{id}
├── bot/
│   ├── telegram.py           # python-telegram-bot, calls api/server.py in-process
│   └── whitelist.py          # Telegram-ID → operator-identity map
├── persistence/
│   ├── foundry_writer.py     # builds action payloads, hands to existing bridge
│   └── audit.py              # thin wrapper over src/mendacity/audit.py
└── tests/
    ├── test_*.py             # detector unit tests (3 per detector)
    ├── test_composite.py     # reduction-rule truth table
    ├── integration/          # POST /verify against fixture set
    └── bot/                  # bot UX tests

palantir/defensive/
├── ontology.md               # InboundArtifact + InboundDetection click-through spec
├── workshop.md               # Verify Console module spec
└── tests/
    └── test_foundry_writer.py # contract tests on action-payload shape

frontend/src/app/verify/
└── page.tsx                  # empty state + drop zone + dossier render + sidebar
frontend/src/app/api/verify/
└── route.ts                  # server-side proxy: stamps operator + source, forwards to FastAPI
```

## Data flow (single verify call)

1. Operator drops image at `/verify` (or DMs bot) → bytes + operator-identity reach `api/server.py:POST /verify`.
2. Server computes `sha256` once, calls `composite.run(bytes, sha256)`.
3. `composite` dispatches all 7 detectors via `asyncio.gather`. CPU-bound detectors run on a `ProcessPoolExecutor`. Each returns a `DetectorSignal{name, severity, score, evidence, latency_ms}`. Per-detector exceptions become `severity=n/a` signals — never propagate.
4. `composite.reduce(signals)` returns a `Verdict{level, confidence, summary}`.
5. `persistence.foundry_writer` upserts 1 `InboundArtifact` + N `InboundDetection` via `palantir/bridge/foundry_bridge.py`.
6. `persistence.audit` appends one log line.
7. Server returns the Verdict JSON. Frontend renders the Dossier; bot replies with one-line summary + permalink.

## Verdict reduction rule

### Per-detector severity semantics

Severity is normalised across detectors so `composite.reduce` can treat them uniformly. **For all detectors, `fail` always means "evidence positive for synthetic / tampered / suspicious", `pass` always means "evidence positive for authentic / untampered", `warn` means "ambiguous or absent signal", `n/a` means the detector errored.**

| Detector | pass | warn | fail |
|---|---|---|---|
| `c2pa` | valid manifest, trusted issuer | manifest absent | manifest present but invalid signature |
| `synthid` | n/a (absence is the norm) | watermark absent | watermark **detected** (i.e., image was generated by Imagen) |
| `titan` | n/a (absence is the norm) | watermark absent | watermark **detected** (i.e., image was generated by Titan) |
| `ai_classifier` | p(artificial) < 0.5 | 0.5 ≤ p(artificial) < 0.85 | p(artificial) ≥ 0.85 |
| `exif` | EXIF coherent and free of generator tags | EXIF missing on a phone-claimed image | EXIF Software tag matches a known generator (Stable Diffusion, Midjourney, DALL-E, etc.) |
| `ela` | ELA score ≤ 0.2 | 0.2 < ELA ≤ 0.4 | ELA > 0.4 |
| `phash` | no stock-corpus match | partial match (Hamming distance ≤ 8) | exact stock-corpus match |

### Verdict level

```
SYNTHETIC  ← any detector at severity == fail
SUSPECT    ← no fails AND any detector at severity == warn (other than absent watermarks alone)
AUTHENTIC  ← otherwise (all signals pass or n/a, with at least one pass)
```

### Verdict confidence

`confidence ∈ [0, 1]` is **the strength of evidence backing the chosen `level`** — it is *not* a probability of being synthetic. A `SYNTHETIC` verdict with confidence 0.95 means strong evidence the image is synthetic; an `AUTHENTIC` verdict with confidence 0.95 means strong evidence the image is authentic.

It is a clamped weighted sum of per-detector contributions, where each detector's contribution is `+weight` if its severity agrees with the verdict level, `0` if `warn` or `n/a`, `−weight × 0.5` if it disagrees:

```
weights = {
  ai_classifier: 0.30,
  exif:          0.20,
  c2pa:          0.15,
  synthid:       0.10,
  titan:         0.10,
  ela:           0.10,
  phash:         0.05,
}
```

Implemented in `defensive/engine/composite.py:reduce`. Pinned by the truth table in `tests/test_composite.py` (≥ 10 cases including each verdict-level transition and the confidence-clamp boundaries). Tunable via constants at the top of the file; changing them requires updating the truth table in the same commit.

## Foundry ontology

Two new object types in `palantir/defensive/ontology.md`. Backing datasets: `mendacity-inboundartifact`, `mendacity-inbounddetection`. Both "Configure without datasource" / Edits-Enabled.

### `InboundArtifact`

| Property | Type | Notes |
|---|---|---|
| `artifact_id` | string (PK) | UUID; SDK param `artifactId` (camelCase, manual add) |
| `sha256` | string | indexed for dedup |
| `file_name` | string | nullable (bot path) |
| `mime` | string | image/jpeg \| image/png \| image/webp |
| `bytes` | int | size |
| `submitted_at` | timestamp | API receive time |
| `submitted_via` | string | verify_tab \| telegram_bot \| api_direct |
| `operator` | string | mapped operator identity |
| `verdict_level` | string | AUTHENTIC \| SUSPECT \| SYNTHETIC |
| `verdict_confidence` | double | 0..1 |
| `verdict_summary` | string | one-line operator-readable conclusion |
| `thumbnail_uri` | string | Foundry media-set URI for 256px thumbnail (nullable) |

### `InboundDetection`

| Property | Type | Notes |
|---|---|---|
| `detection_id` | string (PK) | UUID; SDK param `detectionId` |
| `artifact_id` | string | FK → InboundArtifact.artifact_id |
| `detector_name` | string | c2pa \| synthid \| titan \| ai_classifier \| exif \| ela \| phash |
| `severity` | string | pass \| warn \| fail \| n/a |
| `score` | double | nullable, detector-native |
| `evidence` | string | one-line free text |
| `latency_ms` | int | per-detector elapsed |
| `ran_at` | timestamp | detector-run timestamp |

**Actions:** auto-generated `Create/Edit/Delete` per type. SDK names `create-inbound-artifact`, `edit-inbound-artifact`, `delete-inbound-artifact`. PK params added manually in camelCase per the existing convention. `result_ingester.py`'s upsert pattern (`edit-` → `create-` on missing) reused as-is.

**Link type:** `InboundArtifact` 1—N `InboundDetection` via `artifact_id`.

## API contract

FastAPI app at `defensive/api/server.py`. Bound to localhost only in v1.

### `POST /v1/verify`

Request:
```http
POST /v1/verify
Content-Type: multipart/form-data

image:    <bytes>          # required, ≤ 10 MB, image/jpeg|png|webp
operator: J2-INSCOM-Demo   # required (frontend sends from session, bot sends from whitelist map)
source:   verify_tab       # required: verify_tab | telegram_bot | api_direct
```

Response (HTTP 200):
```json
{
  "artifact_id": "01HXAB7K9P3M4ZQF5N7G2YZTRC",
  "sha256": "4f3a...b21c",
  "verdict": {
    "level": "SUSPECT",
    "confidence": 0.81,
    "summary": "No provenance chain; AI-gen classifier strongly positive; EXIF carries Stable Diffusion software tag."
  },
  "signals": [
    {"detector":"c2pa",          "severity":"warn", "score":null, "evidence":"no manifest",                   "latency_ms": 38},
    {"detector":"synthid",       "severity":"warn", "score":null, "evidence":"absent",                        "latency_ms":120},
    {"detector":"titan",         "severity":"warn", "score":null, "evidence":"absent",                        "latency_ms": 95},
    {"detector":"ai_classifier", "severity":"fail", "score":0.94, "evidence":"p(artificial)=0.94",            "latency_ms":1480},
    {"detector":"exif",          "severity":"fail", "score":null, "evidence":"Software=\"Stable Diffusion\"", "latency_ms": 14},
    {"detector":"ela",           "severity":"pass", "score":0.12, "evidence":"within nominal",                "latency_ms": 89},
    {"detector":"phash",         "severity":"pass", "score":null, "evidence":"no stock-corpus match",         "latency_ms": 42}
  ],
  "submitted_at": "2026-05-03T18:42:11Z",
  "submitted_via": "verify_tab",
  "operator": "J2-INSCOM-Demo",
  "thumbnail_uri": "foundry://media-sets/.../01HXAB7K9P3M4ZQF5N7G2YZTRC.png"
}
```

### `GET /v1/verify/{artifact_id}`

Re-fetch a prior verdict. Same response shape minus the originally-uploaded image bytes (the bytes are not stored; only the thumbnail is).

### Error codes

| HTTP | Code | When |
|---|---|---|
| 400 | unsupported_mime | not jpeg/png/webp |
| 400 | image_too_large | > 10 MB |
| 400 | image_invalid | PIL fails to decode |
| 401 | not_authorized | bot path: sender not in whitelist |
| 404 | artifact_not_found | GET on unknown id |
| 503 | model_loading | classifier model not yet warm; client retries once after 2s |

A single detector raising **never** fails the request. The detector's signal is returned with `severity=n/a` and `evidence` set to the truncated exception class name. The composite verdict is computed from the remaining signals.

### Versioning

Path-prefixed `/v1/`. Future fields are additive only. The first version is the only commitment for the demo.

### Security

No HTTP-level auth in v1; the API is bound to `127.0.0.1` only. Only the bot process and the Next.js server-side proxy route reach it. If exposed beyond localhost in future, gates behind the same whitelist map as the bot.

### Network details

- Bind address: `127.0.0.1`
- Default port: `8788`
- Override via env var `DEFENSIVE_API_PORT`
- The same env var is consumed by the bot process and by the Next.js proxy route so all three components agree without configuration drift.

## UI surfaces

### Verify tab (`frontend/src/app/verify/page.tsx`)

Empty state: dossier-style preamble + drop zone. Sidebar shows "No verifications yet."

After first successful verify: drop zone replaced by the Dossier component (numbered sections — Provenance, Synthesis Indicators, Tamper Evidence — with prose conclusions per the brand's "document, don't decorate" principle). Sidebar populates with one row per session-scoped verify (sha256 prefix + verdict pill). Click a sidebar row → re-render that artifact's dossier.

Sidebar is session-scoped only. Full history lives in Workshop (rationale: keep the operator console focused on the current image).

### Frontend → API path

Browser → Next.js server-side route `frontend/src/app/api/verify/route.ts` → FastAPI `POST /v1/verify` on `127.0.0.1:${DEFENSIVE_API_PORT}`. **The browser never talks to FastAPI directly.** Two reasons:

1. The FastAPI service is bound to localhost; the Next.js proxy is the only network-reachable path that can reach it from the browser.
2. The proxy route resolves the operator identity from the session and stamps it onto the multipart body before forwarding — keeping operator identity out of any client-side code.

The proxy is a thin pass-through: it accepts the file from the browser, attaches `operator` and `source=verify_tab`, forwards to FastAPI, returns the response unchanged.

### Foundry Workshop "Verify Console" module (`palantir/defensive/workshop.md`)

Read-only `InboundArtifact` table view, paginated, sorted by `submitted_at desc`. Columns: submitted_at, operator, source, sha256 prefix, verdict_level (badge), verdict_confidence. Row click opens a detail page that materialises the same Dossier the Verify tab renders, plus a tabbed table of the artifact's `InboundDetection` rows.

Workshop module is read-only. No edit/delete actions surfaced in the UI. Append-only matches the "hide nothing" principle.

## Bot UX

Handle: `@mendacity_verify_bot` (final handle assigned at registration).

| Trigger | Behavior |
|---|---|
| `/start`, `/help` | One-screen capability description. Shows the operator's mapped identity if whitelisted. |
| DM with photo | `POST /v1/verify` with bytes + mapped operator + `source=telegram_bot`. Reply: 4-line summary (verdict, confidence, summary, permalink, ids). |
| DM with photo-as-document | Same as photo (uncompressed path). >10 MB rejected with one line. |
| DM from non-whitelisted ID | One reply: "Not authorized." 60s silent rate-limit on further messages from that ID (log noise reduction; not a security control). |
| Group / channel message | Ignored. Only direct messages. |

Reply format:
```
VERDICT  SUSPECT  (confidence 0.81)
No provenance chain. AI-gen classifier strongly positive. EXIF carries Stable Diffusion software tag.
Dossier · http://localhost:8788/verify/01HXAB7K9P3M4ZQF5N7G2YZTRC
artifact_id: 01HXAB7K9P3M4ZQF5N7G2YZTRC · sha256: 4f3a…b21c
```

Whitelist config: `defensive/bot/whitelist.yaml`, format `{ telegram_user_id: operator_identity }`. For the demo, my Telegram ID is pre-mapped to `J2-INSCOM-Demo` (the operator identity used in PRODUCT.md and PALANTIR_BRIEF.md).

## Error handling matrix

| Surface | Failure | Behavior |
|---|---|---|
| Frontend tab | API 4xx | Inline banner above drop zone, error code + one-line cause. Drop zone primed for retry. |
| Frontend tab | API 5xx (non-detector) | Banner + auto-retry once after 1.5s; if still failing, "API unreachable; check service status." |
| Frontend tab | Single detector failed | Verdict still rendered. Failed detector shown with `severity=n/a` and `evidence="detector unavailable"`. Non-blocking. |
| Frontend tab | Foundry write failed | Verdict still rendered to the operator. Banner: "Verdict rendered, but Foundry persistence failed — see audit log for retry id." Audit log line still written. (Background retry loop deferred to future work.) |
| Bot | API down | Reply: "Verify service unreachable. Try again shortly." |
| Bot | Image > 10 MB | Reply: "Image too large (10 MB max)." |
| Bot | Unsupported format | Reply: "Unsupported format — JPEG, PNG, or WebP only." |
| API | Classifier not warm | First request after boot returns 503 `model_loading`; both clients retry once after 2s. Model warmed at server boot, so this should be rare. |

## Testing

Per global testing rules (`/Users/nicolasdossantos/.claude/rules/testing.md`): describe/it (vitest) or pytest classes; single logical assertion per test; mock external services explicitly; deterministic (no `Math.random`, no `Date.now()` without mocking).

### Unit (`defensive/tests/`, pytest)

- **Per detector (3 tests × 7 detectors = 21):**
  - known-positive fixture
  - known-negative fixture
  - raises-on-corrupt-input fixture
- **`composite.reduce` truth table:** ≥ 10 cases covering each verdict-level transition and the confidence-clamp boundaries.
- **`verdict.py` dataclasses:** serialization round-trip.
- **`whitelist.py`:** lookup hit, lookup miss, malformed config.

### Integration (`defensive/tests/integration/`, pytest)

End-to-end `POST /v1/verify` against a 4-image fixture set:

1. Real iPhone photo with EXIF → expect `AUTHENTIC`.
2. Known DALL-E output → expect `SYNTHETIC`.
3. C2PA-signed image → expect `AUTHENTIC` with c2pa.severity=pass.
4. Corrupt JPEG → expect HTTP 400 `image_invalid`.

Plus `GET /v1/verify/{id}` round-trip from a successful POST.

### Foundry contract (`palantir/defensive/tests/`, pytest)

`foundry_writer` builds correctly-shaped action payloads (camelCase param keys per the existing convention; PK in the right place for "Configure without datasource" types). SDK call mocked.

### Frontend (`frontend/tests/verify.test.tsx`, vitest)

- Empty state renders.
- Drop event triggers `POST /api/verify` (fetch mocked).
- Dossier renders all 7 detector signals from a fixture verdict response.
- Sidebar appends after a successful verify.
- One detector with `severity=n/a` renders as "detector unavailable" without breaking layout.

### Bot (`defensive/tests/bot/`, pytest)

- Non-whitelisted sender → one "Not authorized." reply, no API call, second message within 60s suppressed.
- Whitelisted sender + photo → API called once with correct multipart, reply matches the format above.
- Photo > 10 MB → "Image too large" reply, no API call.
- All telegram-library calls mocked explicitly.

## Open items deferred to spec-execution time

- Final Telegram bot handle (`@mendacity_verify_bot` is the working name; final assignment at registration).
- Local stock-corpus content for `phash.py` (initial corpus = top 100 reverse-image-searched results from `assets/`; expand later).
- Production thumbnail dimensions and compression settings (currently 256px max edge, JPEG quality 80).

## Future work (post-v1)

- Background retry loop for failed Foundry writes.
- Re-run detectors against an existing `InboundArtifact` (would justify graduating to the paired-detection model from a query standpoint).
- URL inputs and clipboard paste for the central tab.
- Cross-mission linking: `InboundArtifact` ↔ `Mission` for "did this inbound image trace back to one of our outbound campaigns?"
- Slack and Discord bot shims (using the same HTTP API).
- Hosted-API detectors as opt-in additional signals (only if data-handoff concerns are resolved).
- Batch verify for triage workflows.
