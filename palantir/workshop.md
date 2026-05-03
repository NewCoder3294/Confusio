# Mendacity — Foundry Workshop dashboard build sheet

**Audience:** Nicolas, in Foundry Workshop.
**Purpose:** click-through reference for building the three views from `PALANTIR_BRIEF.md §7`. Designed so you can build without re-reading the brief — every binding, every action, every filter is pre-named to match `palantir/ontology.md`.

**Voice cue:** the dashboard reads as a working dossier, not an interface around one (`PRODUCT.md`, Design Principle #2: "Document, don't decorate"). Lean on Workshop defaults — no custom CSS unless something actively offends. Speed > polish, but never at the cost of operator-grade restraint.

---

## 0. One Workshop module, three pages

Create a new Workshop module named **`Mendacity Operator Console`**.
Three pages inside it, in this nav order:

1. **Mission Board**     (default landing)
2. **New Mission**
3. **Authorization & Audit**

Top-of-module banner (a single Markdown widget, full width):

```
MENDACITY OPERATOR CONSOLE — TITLE 10 §1631 — SANDBOX ONLY
{{operator}}  ·  {{wall_clock}}  ·  build {{commit_short}}
```

Wire `{{operator}}` to the Workshop session user. `{{wall_clock}}` is a
`now()` formula. `{{commit_short}}` can be a static "v0.1" until we wire
something better.

The banner is the first thing a judge reads. It does three things at once:
declares legal lane, declares posture (sandbox), declares operator identity.
Don't soften it.

---

## 1. Page: Mission Board (landing page)

**Layout:** three-row stack.

### 1.1 Row 1 — stat tiles (height: ~96px)

Three metric tiles, side by side. Each tile has a single number and a
single line of label copy. No sparklines for v1; tiles are a header, not a
charting surface.

| Tile | Value (Workshop formula) | Label copy |
|---|---|---|
| Active missions | `count(Mission where status = 'executing')` | EXECUTING |
| Completed today | `count(Mission where status = 'completed' AND finished_at >= startOfDay(now()))` | COMPLETED TODAY |
| Provenance pass rate (recent 5) | `avg(provenance_pass_rate over last 5 Missions where status = 'completed' order by finished_at desc)` | RECENT PASS RATE |

If the third tile is hard to express as a single Workshop formula, fall back
to a denormalized field on Mission (`provenance_pass_rate`) and average over
the table directly.

### 1.2 Row 2 — split pane (height: fill)

**Left pane (40% width):** filtered object list of `Mission`.

- Filter chip group at top: All, Executing, Pending Approval, Completed,
  Failed, Aborted. (Defaults to All.)
- Sort: `created_at` descending.
- Each row shows: `mission_id` (mono), status pill (color-coded; see §1.4),
  `target_channel.display_name`, `created_at` (relative — "3 min ago").
- Selection drives the right pane.

**Right pane (60% width):** Mission Detail. Renders the selected Mission.
If nothing is selected, render an empty state with copy:

> Select a mission from the list. Or open New Mission to plan one.

(No illustrated empty-state graphic. No emoji.)

#### 1.2.1 Mission Detail layout

Top: header strip.

```
SHADOW-FOX-001                     [Status pill]
operator: J2-INSCOM-Demo
target:   @mendacity_sandbox_demo  ·  Russian-speaking, pro-regime, junior officers
created:  2026-05-03 05:14 UTC     finished: 2026-05-03 05:14 UTC (2.0s)
```

Below the header, **3 stacked sections** in this order:

##### Section A — Stage timeline

A sequenced list of `MissionStage` objects linked to this Mission, sorted by
`seq` ascending. Each row:

```
[icon] [name in mono]      ts (relative)         summary (italic)
```

- icon: ✓ for `status=ok`, · for `skipped`, ✗ for `error`.
- `name`: monospaced; one of the seven canonical stage names.
- `summary`: the `MissionStage.summary` field (already populated by
  `result_ingester`; falls back to status if null).

Don't add any "step 1 of 7" / "loading" indicators. The timeline is a record,
not a progress bar.

##### Section B — Final artifact + provenance verdict

Two columns:

- **Left:** the rendered final artifact image. Workshop's media reference
  with `Artifact.final_path`. If Workshop won't render local-file paths
  inline, fall back to a Markdown widget with a link and a base64 thumbnail
  injected via a Code-Workspace transform. (If neither works, a single
  Markdown widget reading `Path: <final_path>` is acceptable for the demo
  laptop where the path is reachable.)
- **Right:** three large detector pills, vertically stacked:
  - `C2PA — PASS / FLAG`
  - `Titan — PASS / FLAG`
  - `SynthID — PASS / FLAG`
  - Pill color: green (`#1a9d4f`) for PASS, amber (`#c79100`) for "passed but skipped" (run_status=skipped), red (`#c4302b`) for FLAG.
  - Below each pill, a one-line caption from
    `DetectionResult.run_status` ("verified clean", "not run during grade",
    "flagged by detector").

##### Section C — Operator brief paragraph

A single Markdown widget bound to a computed property on Artifact. Run the
`provenance_grader.summarize_artifact(...)` Foundry Function on the linked
Artifact and bind the result. Renders the 60–120 word paragraph; this is the
piece a judge will actually read.

If the function isn't wired yet at demo time, fall back to a static template:

```markdown
Artifact {{artifact_id}} {{treatment_phrase}} **{{verdict_phrase}}**.
{{detector_lines}}
{{outlook_phrase}}
```

…populated client-side from the Ontology fields. Less ideal than the function
call (no nuance) but still recognizably the same surface.

##### Section D — JSON drawer (collapsed by default)

Final detail: a collapsible Markdown/JSON widget showing
`Artifact.final_provenance_json`. Heading: "Raw provenance report
(audit-source)". Collapsed by default. This is the "Hide nothing" principle
from `PRODUCT.md` — surface the audit source directly, don't summarize it
away.

### 1.3 Row 3 — actions strip (height: ~56px)

Buttons, left-aligned:

- **Approve and Execute** — visible iff `Mission.status in (draft, pending_approval)`. Calls `approveMission` action with the selected `mission_id`. Confirmation dialog: "This will dispatch the mission to the engine. Approval is recorded with operator identity {{operator}} and a permanent timestamp."
- **Abort Mission** — visible iff `Mission.status in (draft, pending_approval, executing)`. Calls `abortMission`. Confirmation dialog: "Abort will mark the mission aborted and best-effort halt the engine."
- **Re-grade Artifact** — visible iff a linked Artifact exists AND `Mission.status = completed`. Calls a `regradeArtifact` action that re-runs `analyze_image()` on the same `final_path`. (Optional v1.5; skip if time-pressed. Useful for the demo "live re-run" beat.)

Don't put Approve / Abort behind a single-click. Workshop's confirmation
dialog is the design principle "approval should never be a single thoughtless
tap" (`PRODUCT.md` Design Principle #1).

### 1.4 Status pill colors

Define a Workshop color rule on `Mission.status`:

| status | text color | bg color | label |
|---|---|---|---|
| `draft` | `#6b6b6b` | `#1f1f1f` | DRAFT |
| `pending_approval` | `#c79100` | `#2a2010` | PENDING APPROVAL |
| `executing` | `#1a9dc4` | `#0e2530` | EXECUTING |
| `completed` | `#1a9d4f` | `#0e2818` | COMPLETED |
| `failed` | `#c4302b` | `#2a1010` | FAILED |
| `aborted` | `#6b6b6b` | `#1f1f1f` | ABORTED |

(These are dossier-grade — saturated enough to read from row 5, restrained
enough to not look like a SOC.)

---

## 2. Page: New Mission

**Layout:** single-column, narrow (max-width 720px).

### 2.1 Section 1 — Operator intent

A multi-line text input, full width, ~5 rows. Label: "Operator intent". No
placeholder filler; the empty state speaks for itself.

Below the input, a single button: **Plan Mission**. On click:

1. Calls the `createMissionFromIntent` action with the textarea contents.
2. Action invokes the `MissionPlanner` AIP Studio agent
   (`palantir/aip/mission_planner.md`).
3. On success → renders Section 2 below the button.
4. On refusal → renders Section 3.

The button is disabled while the action is running. Replace the label with
`Planning…` for the duration. No spinner, no countdown timer (`PRODUCT.md`
Design Principle #5: "Calm under pressure").

### 2.2 Section 2 — Planned spec preview (only on success)

Two stacked panels:

- **Top: rationale paragraph.** Bound to the agent's `rationale` output. Plain
  text, normal weight, ~14px. This is the piece the operator reads to decide
  whether the agent understood them.

- **Bottom: structured spec card.** A read-only Markdown widget rendering the
  parsed YAML as a labeled table. Columns: field, value. Rows pulled from the
  Mission row that was just created with `status=draft`. Show:
  `mission_id`, `target_channel`, `audience_profile`, `persona.archetype`,
  `persona.name_seed`, `artifact.prompt`, `artifact.must_pass`,
  `delivery.dry_run`. Skip fields the operator can't change in v1.

Below the panels, two buttons:

- **Approve and Execute** — calls `approveMission`. Same confirmation dialog
  as in the Mission Board. On success, navigates to the Mission Board with
  the new mission selected.
- **Discard Draft** — calls `abortMission` (status → aborted).

If `dry_run=false` was set by the planner (because the operator explicitly
asked for a live post), render a **third row above the buttons** as a
classified-banner-style strip:

```
LIVE POST AUTHORIZED — channel: @mendacity_sandbox_demo (sandbox)
```

Yellow text on near-black background. Force the operator to see it before
clicking Approve.

### 2.3 Section 3 — Refusal (only on agent refusal)

A single panel with three labeled lines:

```
Refused.
Reason:       <agent.refusal_reason>
Remediation:  <agent.refusal_remediation>
```

No retry button. The operator edits the intent textarea and re-clicks Plan
Mission. (Adding an explicit retry button invites the operator to bash on a
constraint without changing inputs.)

### 2.4 Page-level guards

- If the `Channel` ontology has zero rows where `is_sandbox=true`, the page
  should render a top-of-page warning: "No sandbox channels configured.
  Operator cannot create missions." Disable the Plan Mission button. (This is
  defensive; in practice the seed script populates channels at setup.)

---

## 3. Page: Authorization & Audit

This is the page that closes the legal-lane question for a NATSEC judge. It
is mostly cosmetic but must look *correct*. Lean into the dossier aesthetic
hardest here.

### 3.1 Top — banner

A single full-width Markdown widget. Plain monospace, no styling beyond the
border:

```
TITLE 10 § 1631 — MILITARY INFORMATION OPERATIONS
TARGETS: foreign actors only       AUTHORITY: military intelligence
SANDBOX:  {{count_sandbox_channels}} channels currently authorized
LIVE DELIVERY: disabled in this build   (set per-mission delivery.dry_run=false to override)
```

`{{count_sandbox_channels}}` is `count(Channel where is_sandbox=true)`. The
"LIVE DELIVERY: disabled" line should derive from a tenant-wide flag if you
add one; for v1 just hardcode it to "disabled in this build" since every
demo mission is dry-run.

### 3.2 Middle — authority chain card

A static card listing the approval chain:

```
J2 (Director of Intelligence)
  ↓
OGC (Office of General Counsel — review)
  ↓
Mission Operator (executing authority)
```

Pure decoration; no data binding. Useful as a focal point when a judge asks
"who signs off on this." The MissionPlanner already enforces the
authorization fields; this card is the human-readable mirror.

### 3.3 Bottom — recent audit trail

An Object Table widget on `Mission`:

- Columns: `created_at`, `mission_id`, `operator`, `status`, `target_channel.display_name`, `dry_run`, `failure_code` (visible only when present).
- Sort: `created_at` descending.
- Limit: 25 rows.
- Above the table, a count: `{{count_total_missions}} total missions, {{count_completed}} completed, {{count_failed}} failed.`
- Row click → navigates to Mission Board with that mission selected.

This is the table the judge will scroll through if they want to verify "you
really do log every mission." It must be there. It must be readable.

### 3.4 Optional — agent call log

If time allows, add a fourth section: an Object Table on a
`MissionPlannerCalls` dataset (see `mission_planner.md §6`). Columns:
`timestamp`, `intent_text`, `refused`, `refusal_reason`. Demonstrates that
operator intent itself is audited, not just executed missions.

If time-pressed, skip. The `Mission` audit table covers the core story.

---

## 4. Cross-cutting concerns

### 4.1 Empty states

For every list / table on this dashboard:

- **No data**: a single line of italic copy, left-aligned, no illustration.
  Examples: "No missions yet." / "No sandbox channels configured." / "No
  audit trail rows."
- **Loading**: nothing. Workshop's default loading state is restrained
  enough; do not add custom spinners.
- **Error**: a single line in `#c4302b` text. "Failed to load missions
  (refresh to retry)." No "oops" copy, no apology.

### 4.2 Reduced motion

Workshop respects the OS-level `prefers-reduced-motion` by default. Don't
add custom transitions on top.

### 4.3 Keyboard

If you add keyboard nav (`PRODUCT.md` accessibility note), use:
- `j` / `k` / arrow keys: navigate Mission list.
- `enter`: open selected mission in detail pane.
- `a`: focus Approve button (no auto-click).
- `e`: focus Plan Mission textarea.

This is a v1.5 polish item — skip if time-pressed; mouse paths are fine for
the live demo.

### 4.4 Demo data

Run `palantir/demo/seed_channels.py` once before the demo to populate
`Channel` rows. The four `SHADOW-FOX-{001..004}` results that already exist
in `missions/results/` will hydrate automatically once the bridge is
running, so the Mission Board has live density on first load. (See
`palantir/demo/README.md` for the full pre-demo runbook — coming next.)

---

## 5. Build order

Estimated cumulative time given a fresh Workshop module: 2.5 hours, assuming
the Ontology is already in place.

1. (15 min) Module skeleton: top banner, three blank pages.
2. (45 min) Mission Board: stat tiles → list → detail pane (header + stage
   timeline only).
3. (30 min) Mission Board detail: artifact + detector pills section.
4. (15 min) Mission Board: action buttons (Approve, Abort).
5. (30 min) New Mission page end-to-end.
6. (15 min) Authorization & Audit page.
7. (?? min) Polish, empty states, color rules, copy review.

If something has to be cut, cut in this order: optional agent call log
(§3.4), keyboard nav (§4.3), Re-grade Artifact button (§1.3), the operator
brief paragraph function call (§ Section C, fall back to client-side
template).

Never cut: stat tiles, status pills, detector pills, the Authorization &
Audit banner. Those four are the demo's recognizable surface.

---

## 6. Smoke test before the demo

1. Mission Board renders all 4 SHADOW-FOX missions, sorted newest first.
2. Click each in turn. Each Mission Detail renders without error.
3. The artifact image renders for at least one mission.
4. All three detector pills render with the right color.
5. The operator brief paragraph reads cleanly.
6. New Mission: type one of the §5 happy-path intents from
   `mission_planner.md`; planner returns a valid spec; Approve and Execute
   creates a Mission and dispatches it.
7. Watch the bridge log: spec written to inbox, result file appears in
   results/, mission status flips to completed.
8. Authorization & Audit renders all 5+ missions in the trail.

If any of those fail, fall back to demo-only mode (transport Option C) and
hardcode the result hydration via the bulk-load script.
