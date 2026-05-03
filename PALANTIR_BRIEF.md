# Mendacity — Palantir Foundry / AIP Brief

**For: parallel Claude Code session working on Palantir AIP + Foundry**
**Submission deadline: tomorrow (May 3, 2026) at 12:00 PT — ~14 hours from now**
**Hackathon: 3rd Annual NATSEC Hackathon, Cerebral Valley**

You have zero prior context on this project. This document is your full brief. The other Claude Code session is working in parallel on the local codebase and will not be touching anything in Foundry. Stay in your lane (defined below) and the demo comes together.

---

## 1. Project in one paragraph

**Mendacity is an offensive synthetic-deception toolchain for U.S. Army intelligence units (Title 10 authorities, foreign actors only).** It generates synthetic personas + synthetic imagery, validates that the imagery passes the same provenance detection stacks an adversary's vetting pipeline would deploy (C2PA, Amazon Titan watermark, Google SynthID), and delivers content via fabricated personas on closed messaging channels. It's a red-team-in-a-box with a built-in self-grading loop: if Mendacity's own provenance check flags an artifact, the artifact is regenerated or watermark-stripped before it ships. The thesis: deception capability is only useful if it survives the detectors the enemy actually uses, so we grade ourselves with the same tools.

**Customer:** U.S. Army intelligence (INSCOM, 1st IO Command, theater MI brigades). Authority: Title 10 military information operations. Foreign actors only. Not Title 50, not domestic.

**The two arms:**
- **Local engine (`src/mendacity/`, `social/`, `scripts/`):** the actual capability — image generation, provenance verification, watermark stripping, persona post to sandboxed Telegram. Owned by the other Claude session.
- **Palantir layer (yours):** Foundry Ontology + AIP Logic agents + Workshop dashboard. This is the front-of-house for the demo and the layer that makes the tool legible to an Army audience.

---

## 2. Why Palantir matters for winning this hackathon

The Army uses Foundry. Vantage and Gaia are Foundry deployments. A NATSEC judge with an Army background sees Foundry Workshop and instantly recognizes the operating environment. The demo win condition is: **judges believe this could be deployed inside an actual Army intelligence workflow within 30 days.** Foundry + AIP is what gets us there.

Streamlit (the existing local operator console) is the fallback if Foundry isn't ready. **Aim to make Foundry the front-of-house for the demo.**

---

## 3. Strict lane split

| You own (Palantir) | Other Claude owns (local) |
|---|---|
| Foundry Ontology (entities, properties, relations, actions) | `mendacity run-mission <spec.yaml>` CLI spine |
| AIP Logic functions (mission orchestration, agent calls) | Image generation pipeline (existing `scripts/`) |
| Foundry Workshop dashboard (operator UI) | Provenance verification loop (`src/mendacity/pipeline.py`) |
| AIP Studio agent that interprets natural-language operator intent | SynthIDBye watermark stripping (`vendor/SynthIDBye/`) |
| Mock data ingestion (CSV/JSON seeds) for demo | Telegram sandbox post (`social/orchestrator.py`) |
| Slide content for "Foundry integration" architecture slide | Slide content for "engine + provenance" slides |
| Demo script for Foundry segment of the live demo | Demo script for engine segment |

**Do not touch the local codebase.** Don't modify `src/mendacity/`, `social/`, `scripts/`, or `vendor/`. If you need a function exposed differently, write a note in `PALANTIR_REQUESTS.md` at the repo root and the other Claude will adapt. Coordination via files, not direct edits.

---

## 4. Interface contract between Foundry and the local engine

This is the only place the two lanes meet. **Lock this contract first.** Both Claudes implement against the same schema.

### 4.1 Mission spec (input to the engine)

The engine accepts a `MissionSpec` YAML or JSON. Foundry/AIP produces it from operator intent and hands it off via webhook or filesystem (TBD — see §4.4).

```yaml
mission_id: SHADOW-FOX-001                  # set by Foundry; UUID acceptable
operator: J2-INSCOM-Demo                     # operator identity (free text)
authorization:
  authority: title-10
  target_class: foreign                      # always foreign for demo
  approval_chain: ["J2", "OGC-reviewed"]     # decorative for demo
target:
  platform: telegram
  channel: "@adversary_cell_demo"            # MUST be in sandbox allowlist
  audience_profile: "Russian-speaking pro-regime, junior officers"
persona:
  archetype: "disgruntled-junior-officer"
  name_seed: "Vlad K."
  generate_avatar: true
artifact:
  type: image
  prompt: "leaked regiment movement order, smudged unit stamp, low-light phone photo"
  must_pass: [c2pa, titan, synthid]          # red-team grading thresholds
delivery:
  schedule: immediate                        # or ISO-8601
  thread_strategy: cold_post                 # or reply, quote, etc.
```

### 4.2 Mission result (output from the engine)

The engine writes a `MissionResult` JSON when it finishes (or fails) a mission. Foundry's pipeline ingests this back into the Ontology.

```json
{
  "mission_id": "SHADOW-FOX-001",
  "status": "completed",
  "stages": [
    {"stage": "persona_generated", "ts": "2026-05-03T03:14:00Z", "persona_id": "vlad-k-7a2", "avatar_path": "/tmp/missions/SHADOW-FOX-001/avatar.jpg"},
    {"stage": "artifact_generated", "ts": "...", "artifact_path": "/tmp/missions/SHADOW-FOX-001/artifact.jpg"},
    {"stage": "provenance_check", "ts": "...", "provenance_report": { "...full pipeline.py output..." }, "passed": true},
    {"stage": "watermark_strip", "ts": "...", "tool": "synthidbye", "before_sha": "...", "after_sha": "..."},
    {"stage": "delivered", "ts": "...", "telegram_message_id": 12345, "channel": "@adversary_cell_demo"}
  ],
  "final_artifact_path": "/tmp/missions/SHADOW-FOX-001/artifact_clean.jpg",
  "final_provenance_report": { "c2pa": {"status": "manifest_not_found"}, "titan_watermark": {"status": "ok", "detectionResult": "MACHINE_GENERATED_NOT_DETECTED"}, "google_synthid": {"status": "ok", "watermark_verification_result": "NOT_WATERMARKED"} }
}
```

### 4.3 Provenance report shape

The local engine's `analyze_image()` already returns a structured dict. The Foundry side should ingest it as-is. Schema (existing, do not redesign):

```json
{
  "meta": {"sha256": "...", "mime_inferred": "image/jpeg", "size_bytes": 123456, "path": "..."},
  "c2pa": {"status": "ok|manifest_not_found|error", "validation_state": "...", "summary": {"claim_generator_info": [...], "actions": [...]}},
  "titan_watermark": {"status": "ok|skipped|error", "detectionResult": "...", "confidenceLevel": "..."},
  "google_synthid": {"status": "ok|skipped|error", "watermark_verification_result": "..."}
}
```

### 4.4 Transport between Foundry and local engine

Pick one, document the choice in `PALANTIR_REQUESTS.md`:

- **Option A (recommended for hackathon time):** filesystem dropbox. Foundry writes mission specs to `~/Mendacity/missions/inbox/<mission_id>.yaml`, engine watches the dir, writes results to `~/Mendacity/missions/results/<mission_id>.json`. Foundry watches the results dir.
- **Option B (cleaner but slower to wire up):** local FastAPI sidecar exposing `POST /missions` and `GET /missions/{id}`. AIP Logic calls it via HTTP function. Requires tunneling for cloud-hosted Foundry.
- **Option C (demo-only fake):** AIP Logic runs against pre-baked `MissionResult` JSONs in `fixtures/missions/` for the live demo. Real engine runs separately for credibility shots. Use this if §A and §B are at risk.

**Default to A. Fall back to C if anything slips.**

---

## 5. Foundry Ontology design

Build these in the Ontology Manager. Keep property names exact so AIP Logic and Workshop bindings work without renames.

### 5.1 Object types

**`Mission`** — the top-level operation.
- `mission_id` (string, primary key)
- `operator` (string)
- `authority` (string, enum: `title-10`, `title-50`, `other`)
- `status` (string, enum: `draft`, `pending_approval`, `executing`, `completed`, `failed`, `aborted`)
- `target_channel` (string)
- `audience_profile` (string)
- `created_at` (timestamp)
- `completed_at` (timestamp, nullable)
- `provenance_pass_rate` (double, 0.0-1.0) — derived: % of artifacts that passed all required checks first try

**`Persona`** — fabricated identity.
- `persona_id` (string, PK)
- `archetype` (string)
- `display_name` (string)
- `avatar_path` (string)
- `language` (string)
- `created_for_mission` (FK → Mission)

**`Artifact`** — generated content (image only for v1).
- `artifact_id` (string, PK)
- `mission_id` (FK → Mission)
- `type` (string, enum: `image`)
- `prompt` (string)
- `path` (string)
- `sha256` (string)
- `passed_c2pa` (boolean)
- `passed_titan` (boolean)
- `passed_synthid` (boolean)
- `watermark_stripped` (boolean) — true if SynthIDBye was applied
- `final_provenance_json` (string, inline JSON of the full provenance report)

**`Channel`** — sandboxed delivery target.
- `channel_id` (string, PK)
- `platform` (string, enum: `telegram`)
- `display_name` (string)
- `is_sandbox` (boolean) — must be `true` for any mission to execute
- `audience_profile` (string)

**`DetectionResult`** — one row per provenance check run.
- `result_id` (string, PK)
- `artifact_id` (FK → Artifact)
- `detector` (string, enum: `c2pa`, `titan`, `synthid`)
- `passed` (boolean) — true if "image looks real" per this detector
- `raw_response` (string)
- `checked_at` (timestamp)

### 5.2 Link types

- `Mission` → `Persona` (one-to-one, "uses persona")
- `Mission` → `Artifact` (one-to-many, "produces artifact")
- `Mission` → `Channel` (many-to-one, "targets channel")
- `Artifact` → `DetectionResult` (one-to-many, "graded by")

### 5.3 Actions

Wire these in the Ontology Manager so they're invocable from Workshop and AIP Logic:

- **`createMission(intent_text)`** → AIP Logic agent parses the natural-language intent into a `MissionSpec`, creates a `Mission` object in `draft` status.
- **`approveMission(mission_id)`** → flips status `draft` → `pending_approval` → `executing`, drops the spec file into the engine inbox (transport §4.4).
- **`abortMission(mission_id)`** → writes abort flag, status → `aborted`.
- **`ingestMissionResult(result_json)`** → called by a scheduled pipeline that watches the results dir, hydrates `Artifact`/`DetectionResult` objects, updates `Mission.status` and `provenance_pass_rate`.

---

## 6. AIP Logic specs

### 6.1 `MissionPlanner` (AIP Studio agent)

Natural-language operator intent → structured `MissionSpec`. Operator types something like:

> "Plant a leaked-orders post in the pro-regime junior officer channel from a disgruntled lieutenant persona. Image should look like a smudged regimental movement order shot on a phone."

Agent output: a populated `MissionSpec` matching §4.1 schema.

System prompt skeleton:

```
You are MissionPlanner, an Army intelligence mission-planning assistant operating
under Title 10 authority for foreign-targeted information operations. The operator
gives you a free-text intent. You produce a strict YAML MissionSpec matching this
schema: [paste §4.1 schema].

Hard constraints:
- target.platform must be telegram (v1)
- target.channel must come from the allowlist: [list from Channel ontology where is_sandbox=true]
- artifact.must_pass must always include all three: c2pa, titan, synthid
- authorization.authority must be title-10
- authorization.target_class must be foreign

If the operator's intent violates any constraint, refuse and explain which one.
```

### 6.2 `ProvenanceGrader` (AIP Logic function)

Input: `Artifact` object. Output: a one-paragraph natural-language summary of whether the artifact will survive adversary detection, citing the three sub-detector results. Used in the Workshop "Mission Detail" view to make provenance results legible to non-technical operators.

### 6.3 `MissionDispatcher` (AIP Logic function)

Triggered by the `approveMission` action. Serializes the `MissionSpec` to YAML, writes it to the engine inbox dir (§4.4 Option A) or POSTs to the sidecar (Option B). Polls the result dir; on result file appearing, calls `ingestMissionResult`.

### 6.4 `ResultIngester` (scheduled pipeline)

Runs every 5s during the demo. Watches `~/Mendacity/missions/results/`. Parses each new result JSON, invokes `ingestMissionResult` action.

---

## 7. Foundry Workshop dashboard

One module, three views. Keep the visual aesthetic dark, dense, dossier-grade — pull from existing `social/app.py` styling cues if you can, but prefer Workshop defaults over custom CSS. Speed > polish.

### 7.1 View: "Mission Board"

- Top: stat tiles
  - Active missions (count of `Mission.status = executing`)
  - Completed today
  - Provenance pass rate (avg across recent missions)
- Left pane: object list of `Mission` filtered by status
- Right pane: selected mission detail
  - Status pill, operator, channel, audience profile
  - Stage timeline (pulled from `Mission.stages` if denormalized, or via linked `Artifact`/`DetectionResult` queries)
  - Final artifact image (rendered via `Artifact.path` — Foundry needs a media reference; if not feasible, embed a Markdown widget linking to local file)
  - Provenance pass/fail badges (C2PA / Titan / SynthID)

### 7.2 View: "New Mission"

- Free-text textarea: "Operator intent"
- Channel dropdown (bound to `Channel` where `is_sandbox=true`)
- Submit button → triggers `MissionPlanner` agent → preview the planned `MissionSpec` → "Approve and Execute" button → triggers `approveMission` action

### 7.3 View: "Authorization & Audit"

Mostly cosmetic but critical for the judge. Shows:
- Banner: **"Operating under Title 10 §1631 — military information operations against foreign actors. All channel targets validated as sandbox."**
- Recent mission audit trail (timestamp, operator, mission_id, status changes)
- Authority chain card (J2 → OGC review → execute)

This is the slide that answers "what's the legal lane" in the demo. If a judge asks about authorization, the operator clicks this view.

---

## 8. Demo flow — where Foundry fits

3-minute live demo. Foundry segments marked **[FOUNDRY]**. Total Foundry stage time: ~90s of the 180s.

| Time | Segment | Owner |
|---|---|---|
| 0:00–0:20 | Slide 1: Problem — Army needs deception capability that survives adversary vetting | Pitcher |
| 0:20–0:35 | Slide 2: Customer (INSCOM) + authority (Title 10) — show the **Authorization & Audit view** in Foundry | **[FOUNDRY]** |
| 0:35–1:00 | **Mission Board** showing 1 completed mission as warmup — narrator walks through stage timeline and provenance pass | **[FOUNDRY]** |
| 1:00–1:30 | Live: open **New Mission** view, type operator intent, MissionPlanner agent generates spec, click Approve | **[FOUNDRY]** |
| 1:30–2:15 | Cut to local engine (terminal + image preview) — show generation, watermark strip, provenance pass | Other Claude's lane |
| 2:15–2:35 | Cut back to Foundry: result has flowed back into Ontology, Mission Board shows new mission completed | **[FOUNDRY]** |
| 2:35–3:00 | Slide: "30-day deployment story" — Foundry-native, drops into existing Army Vantage tenants | Pitcher |

Your job: make the Foundry segments tight. Pre-bake demo data so the Mission Board has 3-5 completed missions to look impressive, even if only one is genuinely live during the demo.

---

## 9. Time budget — what to ship by when

**Tonight (next 4 hours):**
- Lock interface contract §4 — write `PALANTIR_REQUESTS.md` with chosen transport (A/B/C) so other Claude can match
- Build Ontology object types and link types in Foundry
- Stub out Mission Board view with hardcoded data
- Get one round-trip working: a hardcoded `MissionSpec` JSON ingested into Ontology

**Tomorrow morning (4 hours, before submission window):**
- Wire `MissionPlanner` AIP agent
- Build New Mission view + Approve flow
- Build Authorization & Audit view
- Pre-bake 3-5 demo missions for visual density
- End-to-end rehearsal with other Claude's CLI

**If anything slips:** drop to demo-only mode (transport Option C), hardcode the result JSONs, run the live engine separately. The Foundry side still tells the story.

---

## 10. Hard constraints — read carefully

1. **Sandbox channels only.** Every `Channel` object you create must have `is_sandbox = true`. The `MissionPlanner` agent must refuse any target that isn't on the allowlist. No live targeting.
2. **Title 10 framing everywhere.** No Title 50, no domestic. The Authorization & Audit view says it explicitly. The agent system prompt enforces it.
3. **Don't soften the offensive framing.** This is a synthetic-deception toolchain. Use words like "synthetic persona," "fabricated artifact," "adversary detection bypass," "watermark strip." Do not say "deception-aware" or "counter-deception" — that's a different product. Operator intent should sound like SOCOM MISO doctrine, not academic AI ethics.
4. **No commits, no pushes.** Anything you build in the local repo (e.g., the `PALANTIR_REQUESTS.md` coordination file, demo data CSVs under `fixtures/`) — do not commit unless the user (Nicolas) explicitly approves. Foundry-side work lives in Foundry; nothing to commit there anyway.
5. **Ask before deviating.** If the contract in §4 doesn't fit Foundry's reality, write a note in `PALANTIR_REQUESTS.md` describing the issue and the proposed change. Don't silently diverge.

---

## 11. What you're optimizing for

**Win the hackathon.** Specifically: a 3-minute demo that makes a NATSEC judge with an Army background say "this could be in Vantage by next month." Foundry + AIP is the part of the demo that closes that sale. The local engine proves the capability is real; Foundry proves it would deploy.

**Quality over speed of delivery** — Nicolas's standing rule. Shortcuts are fine if they're invisible to the judge (pre-baked data, demo-only transport). Shortcuts that show up on screen are not fine.

**No MVP language in the pitch.** Nicolas builds for billion-dollar scale. The pitch is "this is the platform," not "this is a prototype."

---

## 12. Repo layout reference (read-only for you)

```
~/Mendacity/
├── src/mendacity/             # Local engine (provenance CLI) — DO NOT TOUCH
│   ├── cli.py                 # mendacity-check (current); mendacity run-mission (incoming)
│   ├── pipeline.py            # analyze_image() — returns provenance report
│   ├── c2pa_report.py
│   ├── titan.py
│   └── google_wm.py
├── social/                    # Local engine (persona + Telegram) — DO NOT TOUCH
│   ├── orchestrator.py        # campaign daemon
│   ├── persona_agent.py
│   ├── telegram_client.py
│   └── app.py                 # Streamlit operator console (will be the fallback if Foundry slips)
├── scripts/                   # Image manipulation utilities
│   ├── apply_jpeg_exif.py
│   └── synthidbye_run.ts      # SynthID watermark strip
├── vendor/SynthIDBye/         # Vendored watermark stripper
├── fixtures/                  # EXIF templates and test data
├── assets/                    # Test images
├── missions/                  # NEW: created by other Claude — your transport drops here
│   ├── inbox/                 #   <mission_id>.yaml — Foundry writes
│   └── results/               #   <mission_id>.json — engine writes
└── PALANTIR_BRIEF.md          # this doc
```

---

## 13. First three actions for you

1. Read this doc.
2. Read the existing `README.md`, `social/README.md` (if it exists), and `src/mendacity/cli.py` — get a feel for the local engine's voice and capabilities. **Read only — no edits to these files.**
3. Create `PALANTIR_REQUESTS.md` at the repo root with:
   - Your chosen transport (A/B/C from §4.4)
   - Any clarifications you want from the local engine
   - Your start-of-work timestamp

Then build.

Good hunting.
