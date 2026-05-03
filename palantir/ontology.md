# Mendacity — Foundry Ontology Spec

**Audience:** Nicolas, in Foundry Ontology Manager.
**Purpose:** click-through reference for building the Ontology. Property names and types here are bound exactly to the local engine's emitted result schema (`PALANTIR_REQUESTS.md §3`), so `palantir/aip/result_ingester.py` and the Workshop bindings work without renames.

**Source of truth:** `missions/results/SHADOW-FOX-001.json` and siblings. If something here disagrees with what the engine actually emits today, the engine wins — flag the disagreement in `PALANTIR_REQUESTS.md §3` so we can pin it.

---

## Build order (top-down dependency)

1. Object types in this order: `Channel` → `Persona` → `Mission` → `Artifact` → `DetectionResult`.
2. Link types after all object types exist.
3. Actions last (they reference object types and link types).

Ontology Manager will fight you if you try to create an action that references a type you haven't made yet.

---

## 1. Object types

### 1.1 `Channel`

The sandbox allowlist. Single source of truth for "where is it legal to post." Every `Channel` row must have `is_sandbox = true`; a non-sandbox row would be a constraint violation in this build.

| Property | Type | PK | Required | Notes |
|---|---|---|---|---|
| `channel_id` | string | ✓ | ✓ | e.g. `mendacity_sandbox_demo` (no leading `@` in PK; the `@` lives in `display_name`) |
| `platform` | string (enum) | | ✓ | values: `telegram`. Add more enum values when v2 expands beyond Telegram. |
| `display_name` | string | | ✓ | the canonical handle the engine sees, including `@` (e.g. `@mendacity_sandbox_demo`) |
| `is_sandbox` | boolean | | ✓ | hard-locked to `true`. Use a derived rule or just don't expose a UI to set it false. |
| `audience_profile` | string | | | free-text language/demographic ("Russian-speaking, pro-regime, junior officers") |
| `created_at` | timestamp | | ✓ | when added to allowlist |

**Initial seed rows** (run as part of demo setup; load via the bulk-load script in `palantir/demo/seed_channels.py`):

| channel_id | platform | display_name | audience_profile |
|---|---|---|---|
| `mendacity_sandbox_demo` | telegram | `@mendacity_sandbox_demo` | Russian-speaking, pro-regime, junior officers |
| `inscom_lab_sandbox` | telegram | `@inscom_lab_sandbox` | Mandarin-speaking, semi-active, regional militia adjacent |
| `hackathon_sandbox_alpha` | telegram | `@hackathon_sandbox_alpha` | Farsi-speaking, fence-sitters, young professional class |

These match `missions/sandbox_channels.json`.

---

### 1.2 `Persona`

Fabricated identity used for one mission. One mission, one persona — though personas could be reused in v2.

| Property | Type | PK | Required | Notes |
|---|---|---|---|---|
| `persona_id` | string | ✓ | ✓ | engine-generated (e.g. `disgruntled-junior-officer-f94762`); pulled from `result.stages[?stage='persona_generated'].detail.persona_id` |
| `archetype` | string | | ✓ | e.g. `disgruntled-junior-officer` |
| `display_name` | string | | ✓ | `name_seed` from spec, e.g. `Vlad K.` |
| `language` | string | | | inferred from spec.target.audience_profile or NULL |
| `avatar_path` | string | | | absolute path; nullable (engine emits null when `generate_avatar: false`) |
| `created_for_mission` | string (FK) | | ✓ | `mission_id` of the parent mission |
| `created_at` | timestamp | | ✓ | mirror `Mission.created_at` |

---

### 1.3 `Mission`

The top-level operation. Most-bound type — Workshop's Mission Board, AIP MissionPlanner, both audit views all hang off this.

| Property | Type | PK | Required | Notes |
|---|---|---|---|---|
| `mission_id` | string | ✓ | ✓ | matches `result.mission_id` and inbox filename stem |
| `operator` | string | | ✓ | `result.operator` (free text identity) |
| `authority` | string (enum) | | ✓ | values: `title-10`, `title-50`, `other`. Hard-locked to `title-10` for v1; the MissionPlanner refuses anything else. |
| `target_class` | string (enum) | | ✓ | values: `foreign`, `domestic`, `unspecified`. Hard-locked to `foreign` for v1. |
| `approval_chain` | array of string | | ✓ | from `spec.authorization.approval_chain` |
| `status` | string (enum) | | ✓ | values: `draft`, `pending_approval`, `executing`, `completed`, `failed`, `aborted`. State machine in §1.3.1 below. |
| `target_channel_id` | string (FK) | | ✓ | FK to `Channel.channel_id` |
| `audience_profile` | string | | | denormalized from Channel for fast Workshop reads |
| `artifact_prompt` | string | | ✓ | `spec.artifact.prompt` |
| `must_pass` | array of string | | ✓ | `spec.artifact.must_pass`, e.g. `["c2pa","titan","synthid"]` |
| `strip_watermarks` | boolean | | ✓ | `spec.artifact.strip_watermarks` |
| `dispatched_at` | timestamp | | | set by bridge when spec is dropped to `inbox/`; NULL means bridge hasn't sent yet |
| `created_at` | timestamp | | ✓ | when MissionPlanner finalized the spec |
| `started_at` | timestamp | | | `result.started_at` |
| `finished_at` | timestamp | | | `result.finished_at` |
| `provenance_pass_rate` | double | | | computed: count(`Artifact.passed_all` is true) / count(`Artifact`) for this mission. NULL until first artifact lands. |
| `failure_code` | string | | | `result.error.code` when `status=failed`; NULL otherwise |
| `failure_stage` | string | | | `result.error.stage` when `status=failed` |
| `failure_message` | string | | | `result.error.message` when `status=failed` |
| `dry_run` | boolean | | ✓ | `spec.delivery.dry_run`; demo runs always true |
| `caption_preview` | string | | | `spec.delivery.caption` (or `result.stages[?stage='delivered'].detail.caption_preview` when delivered/skipped) |

#### 1.3.1 Status state machine

```
                   ┌──────────────────────┐
                   │                      ▼
draft ──→ pending_approval ──→ executing ──→ completed
   │            │                  │
   │            │                  └──→ failed
   ▼            ▼
aborted     aborted
```

Transitions, by who:

- `draft → pending_approval`: operator clicks "Plan Mission" in Workshop; `MissionPlanner` agent has produced a valid spec.
- `pending_approval → executing`: operator clicks "Approve and Execute" in Workshop; `approveMission` action fires; bridge will pick this up next poll.
- `executing → completed | failed`: bridge's `ingestMissionResult` action sets terminal state from `result.status`.
- `* → aborted`: operator clicks "Abort"; `abortMission` action.

#### 1.3.2 Stage events

The brief's `Mission.stages` field is denormalized to a separate `MissionStage` object type — see §1.6. The reason: the engine can emit ~7 stages per mission and embedding them as a struct array in `Mission` makes the timeline UI awkward in Workshop. A linked object type is the Foundry-native way to render an event stream.

(If after building you find Workshop renders an embedded array fine, collapse `MissionStage` back into `Mission.stages` — it's the kind of decision worth revisiting once you've seen it on screen.)

---

### 1.4 `Artifact`

One per regenerated/output image. v1: only one Artifact per Mission; the schema permits many to support a v2 regeneration loop.

| Property | Type | PK | Required | Notes |
|---|---|---|---|---|
| `artifact_id` | string | ✓ | ✓ | engine-generated. Currently the engine doesn't emit an explicit `artifact_id`; the bridge constructs it as `<mission_id>-clean` for now. (See `PALANTIR_REQUESTS §3.4` — once the engine emits a real ID, switch.) |
| `mission_id` | string (FK) | | ✓ | parent mission |
| `type` | string (enum) | | ✓ | values: `image`. v1 only. |
| `prompt` | string | | ✓ | `spec.artifact.prompt` |
| `source_path` | string | | | `result.stages[?stage='artifact_selected'].detail.work_path` (the unmodified source) |
| `final_path` | string | | ✓ | `result.final_artifact_path` |
| `source_sha256` | string | | | from `artifact_selected.detail.sha256` |
| `stripped_sha256` | string | | | from `watermark_strip.detail.after_sha` (NULL if `strip_watermarks=false`) |
| `final_sha256` | string | | ✓ | from `final_provenance_report.meta.sha256` (post-EXIF transplant — this is what's "delivered") |
| `passed_c2pa` | boolean | | ✓ | from `provenance_check.detail.passed.per_detector.c2pa` |
| `passed_titan` | boolean | | ✓ | from `provenance_check.detail.passed.per_detector.titan` |
| `passed_synthid` | boolean | | ✓ | from `provenance_check.detail.passed.per_detector.synthid` |
| `passed_all` | boolean | | ✓ | from `provenance_check.detail.passed.all_passed` |
| `watermark_stripped` | boolean | | ✓ | true iff a `watermark_strip` stage emitted `status=ok` |
| `exif_transplanted` | boolean | | ✓ | true iff an `exif_transplant` stage emitted `status=ok` |
| `final_provenance_json` | string | | ✓ | full `final_provenance_report` as inline JSON. Lets Workshop expose the raw audit blob without round-tripping the bridge. |
| `created_at` | timestamp | | ✓ | mirrors `provenance_check.ts` |

---

### 1.5 `DetectionResult`

One row per detector per artifact (so 3 rows per fully-checked artifact: c2pa, titan, synthid). This is the row that makes "we grade ourselves with the same tools the enemy uses" tangible in the Mission Detail view.

| Property | Type | PK | Required | Notes |
|---|---|---|---|---|
| `result_id` | string | ✓ | ✓ | constructed: `<artifact_id>:<detector>` |
| `artifact_id` | string (FK) | | ✓ | parent artifact |
| `detector` | string (enum) | | ✓ | values: `c2pa`, `titan`, `synthid` |
| `passed` | boolean | | ✓ | "image looks real per this detector" — from `passed.per_detector[detector]` |
| `run_status` | string (enum) | | ✓ | values: `ok`, `skipped`, `error`. Reflects whether the cloud call actually ran (`final_provenance_report.<detector>.status`). A `skipped` run with `passed=true` means we *assume* clean since the detector never had a chance to flag — Workshop should render this differently from a real `ok` pass. |
| `raw_response` | string | | | inline JSON of `final_provenance_report.<detector>` |
| `checked_at` | timestamp | | ✓ | `provenance_check.ts` |

**Naming subtlety.** The engine uses `google_synthid` and `titan_watermark` keys in the provenance report. The Ontology uses short names (`synthid`, `titan`) for compactness in Workshop pills. The `result_ingester` does the mapping.

---

### 1.6 `MissionStage`

One row per emitted stage. This is the audit timeline.

| Property | Type | PK | Required | Notes |
|---|---|---|---|---|
| `stage_id` | string | ✓ | ✓ | constructed: `<mission_id>:<seq>` where seq is 0-indexed stage order |
| `mission_id` | string (FK) | | ✓ | parent mission |
| `seq` | integer | | ✓ | 0-indexed within the mission |
| `name` | string | | ✓ | one of: `validated`, `persona_generated`, `artifact_selected`, `watermark_strip`, `exif_transplant`, `provenance_check`, `delivered` |
| `status` | string (enum) | | ✓ | values: `ok`, `error`, `skipped` |
| `ts` | timestamp | | ✓ | from `stage.ts` |
| `detail_json` | string | | ✓ | inline JSON of `stage.detail` |
| `summary` | string | | | one-line operator-readable summary; ProvenanceGrader fills this for the `provenance_check` row, the ingester fills the others heuristically (e.g. for `delivered`/`skipped`: `"Dry-run — would post to {channel}"`) |

---

## 2. Link types

Build after object types are saved.

| From | To | Cardinality | Verb | Notes |
|---|---|---|---|---|
| `Mission` | `Persona` | one-to-one | "uses persona" | inverse "persona of" |
| `Mission` | `Artifact` | one-to-many | "produces artifact" | inverse "artifact of" |
| `Mission` | `Channel` | many-to-one | "targets channel" | inverse "channel of missions" |
| `Mission` | `MissionStage` | one-to-many | "has stage" | inverse "stage of"; sort by `seq` ascending in Workshop |
| `Artifact` | `DetectionResult` | one-to-many | "graded by" | inverse "result of" |

---

## 3. Actions

Build last. Each one is invocable from Workshop and from AIP Logic / the bridge SDK.

### 3.1 `createMissionFromIntent(intent_text: string) → Mission`

Workshop's "New Mission" view calls this. Internally calls the `MissionPlanner` AIP Studio agent (`palantir/aip/mission_planner.md`) to convert free text into a structured spec, then writes a `Mission` with `status = draft`.

Output: the new `Mission.mission_id`, plus the structured spec preview (rendered in Workshop before the operator approves).

### 3.2 `approveMission(mission_id: string) → Mission`

Operator action. Validates the mission is in `draft` or `pending_approval` and the target channel is in the `Channel` allowlist (defense-in-depth — MissionPlanner already enforces this).

State change: `→ executing`. Sets `Mission.dispatched_at = NULL` so the bridge knows to pick it up.

### 3.3 `abortMission(mission_id: string) → Mission`

Operator action. Allowed from any non-terminal state. Sets `status = aborted`, `finished_at = now`. The bridge, on next poll, will see this and (a) not write the spec to inbox if it hasn't already, (b) write an `<mission_id>.abort` flag to inbox if it has — engine should treat that as "drop in-progress work, write a result with `status=aborted`."

> **Engine-side question filed in `PALANTIR_REQUESTS.md §6.7`.** Until that's wired, abort is best-effort: if dispatch already happened, the engine completes anyway and the bridge overwrites status to `aborted` only if no result has landed.

### 3.4 `markDispatched(mission_id: string) → Mission`

Bridge-only action. Sets `Mission.dispatched_at = now()`. Used so the bridge's outbound poll doesn't keep re-dropping the same spec into inbox.

### 3.5 `ingestMissionResult(result_json: string) → Mission`

Bridge-only action. The big one. Takes the entire result JSON as a string, parses it, and:

1. Updates the `Mission` (status, started_at, finished_at, failure fields).
2. Creates / updates the `Persona` from the `persona_generated` stage.
3. Creates / updates the `Artifact` from `artifact_selected` + `watermark_strip` + `exif_transplant` + `provenance_check` stages.
4. Creates 3 `DetectionResult` rows from the per-detector pass map.
5. Creates one `MissionStage` row per `result.stages[i]`, in order.
6. Recomputes `Mission.provenance_pass_rate` from linked `Artifact` rows.

Implementation reference: `palantir/aip/result_ingester.py`.

### 3.6 `seedDemoData() → integer (count)`

One-shot setup action. Wipes and reloads the three demo `Channel` rows and any "before the demo started" pre-baked missions. Used to reset the dashboard between rehearsal runs. Bridge-only — never expose to Workshop.

---

## 4. Property-level constraints (defense in depth)

Foundry won't enforce all of these natively; restate them in the MissionPlanner prompt and the `ingestMissionResult` action so a corrupt spec can't hydrate into the Ontology.

- `Mission.authority = "title-10"` — hard. Reject otherwise.
- `Mission.target_class = "foreign"` — hard. Reject otherwise.
- `Mission.target_channel_id` — must exist in `Channel` AND `Channel.is_sandbox = true`.
- `Mission.must_pass` — must be a non-empty subset of `["c2pa","titan","synthid"]`.
- `Channel.is_sandbox = true` — every row, no exceptions in v1.
- `Mission.dry_run = true` — recommended hard-lock for the hackathon demo to avoid live posts. Set this as a default in the MissionPlanner prompt; allow override only via a Workshop checkbox the demo never clicks.

---

## 5. What's intentionally NOT in this Ontology

- **Generated images as inline binary.** Foundry handles media objects but not gracefully for hackathon time. Workshop will render the Artifact's `final_path` via a Markdown widget that links to the file (or, for a slicker demo, a small base64 thumbnail field added in v1.5).
- **Telegram delivery receipts.** v1 is dry-run-only. When live delivery turns on, add `Mission.telegram_message_url` and a `Delivery` object type.
- **Operator identity as an object type.** v1 treats `operator` as a string. v2 lifts to a `Operator` object type linked to missions for proper audit.
- **C2PA manifest contents.** The raw response is in `DetectionResult.raw_response`; we don't break out claim_generator_info / actions into structured columns. The `ProvenanceGrader` synthesizes a paragraph for human consumption.

---

## 6. After you build this

Give me a one-line confirmation here in this file or in `PALANTIR_REQUESTS.md` and I'll point the bridge at your tenant. I need: tenant URL, API token (service user preferred), and the Ontology rid (Foundry surfaces it once the Ontology is created).
