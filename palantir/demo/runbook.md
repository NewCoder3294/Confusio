# Pre-demo runbook

**When to run this:** the morning of the demo, two hours before the
submission deadline. This is the click-by-click sequence that takes you from
"Foundry tenant exists, Ontology is empty" to "Mission Board shows 4 missions
and the live New Mission flow works end-to-end."

**Total time, working briskly:** ~75 minutes.

If at any step something breaks, **drop to demo-only mode** (transport Option
C from `PALANTIR_BRIEF.md §4.4`): skip the bridge entirely, run the engine
separately for credibility shots, and rely on `load_existing_results.py` for
Foundry-side density. The Foundry segment of the demo still tells the story.

---

## Step 0 — Prereqs (5 min)

- Foundry tenant URL: `https://nicolasdossantos.usw-18.palantirfoundry.com/`
- Service-user token, freshly generated. Account → Settings → Tokens → New
  token. Treat like a secret. Copy once; you can't view it again.
- Local Python 3.12+ venv:

```bash
cd ~/Mendacity/palantir/bridge
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: paste FOUNDRY_TOKEN. Leave FOUNDRY_ONTOLOGY_RID blank for now.
```

- Engine side already running on its own (other Claude session). Sanity check:
  `ls missions/results/` — should show the 4 SHADOW-FOX result files.

---

## Step 1 — Build the Ontology (30 min)

Open Ontology Manager. Reference: `palantir/ontology.md` is the click-through
spec for everything below. Build object types in this order: `Channel` →
`Persona` → `Mission` → `Artifact` → `DetectionResult` → `MissionStage`. Then
link types. Then actions.

**Time-budget cuts if behind:**
- Skip `MissionStage` — denormalize stages back into `Mission.stages` as a
  string array. The detail view loses the timeline, but everything else
  works.
- Skip the `regradeArtifact` action (§3.3 in `ontology.md`) — it's optional.

**At the end of this step:** copy the Ontology rid from the URL (looks like
`ri.ontology.main.ontology.<uuid>`) into `palantir/bridge/.env` →
`FOUNDRY_ONTOLOGY_RID=...`.

---

## Step 2 — Seed channels + load existing results (5 min)

```bash
cd ~/Mendacity/palantir/demo
python seed_channels.py
python load_existing_results.py
```

Expected output: `done — Mission Board should now show 4 missions`.

If `seed_channels.py` errors with "action not found," the Channel object
type's auto-generated `create-channel` / `edit-channel` actions weren't
created. In Ontology Manager, find the Channel type → mark "Editable" — that
generates the actions. Re-run.

---

## Step 3 — Sanity-check the bridge (5 min)

```bash
cd ~/Mendacity/palantir/bridge
source .venv/bin/activate
python foundry_bridge.py --once -v
```

Expected: connects to Foundry, syncs channels, finds zero executing missions
(the seeded ones are `completed`), exits clean. If anything errors, fix
before moving on — the bridge is the round-trip.

Then start it for real:

```bash
python foundry_bridge.py 2>&1 | tee bridge-$(date +%Y%m%d-%H%M%S).log
```

Leave this terminal visible during the demo. It's part of the credibility
surface.

---

## Step 4 — Build Workshop module (45 min)

Reference: `palantir/workshop.md` is the click-through spec.

Build pages in this order:
1. **Module skeleton + banner** (10 min)
2. **Mission Board** — stat tiles → list → detail pane (25 min)
3. **New Mission** — depends on `MissionPlanner` agent existing (defer until
   step 5)
4. **Authorization & Audit** (10 min)

**Time-budget cuts if behind:**
- Skip the operator brief paragraph function call (§ Section C) → fall back
  to client-side template.
- Skip Re-grade Artifact button (§1.3).
- Skip the optional agent call log on Authorization page (§3.4).

---

## Step 5 — Build MissionPlanner AIP Studio agent (15 min)

In AIP Studio, create a new agent named `MissionPlanner`. Paste the system
prompt from `palantir/aip/mission_planner.md` §2 verbatim.

Wire grounding (§4):
- Channel allowlist as a dynamic resource: query `Channel where is_sandbox=true`.
- Recent missions: `Mission ORDER BY created_at DESC LIMIT 5`.

Wire I/O binding (§3):
- Input: single `intent_text` string.
- Output: structured object with `mission_spec_yaml`, `rationale`, `refused`,
  `refusal_reason`, `refusal_remediation`.

Wrap the agent in a `createMissionFromIntent` Ontology action that:
- Calls the agent with the textarea contents.
- On success, parses the YAML, calls `create-mission` to insert a draft row.
- On refusal, returns the refusal payload to Workshop without creating a row.

Run §5 evaluation cases from `mission_planner.md` to validate. Don't move on
until at least cases 5.1, 5.3, 5.4, 5.5 behave correctly (one happy path, three
refusal types).

Then return to Workshop and finish the New Mission page (§2 in
`workshop.md`).

---

## Step 6 — End-to-end rehearsal (10 min)

Cycle the full flow at least three times before the live demo:

1. Open New Mission page.
2. Type one of the §5 happy-path intents from `mission_planner.md`.
3. Click Plan Mission. Spec preview renders.
4. Click Approve and Execute. Mission appears on Mission Board with
   `status=executing`.
5. Bridge log shows: `wrote spec to missions/inbox/<id>.yaml`.
6. Within ~5 seconds, engine writes `missions/results/<id>.json`.
7. Bridge log shows: `hydrated <id>.json`.
8. Refresh Workshop. Mission flips to `completed`. Detail pane shows full
   stage timeline + all three detector pills green.

If any step fails, fix it. Don't take a known-broken flow into the live demo.

---

## Step 7 — Demo dress (5 min)

- Close any other browser tabs. Foundry only.
- Workshop in **dark theme**.
- Browser zoom to ~110% (projector glare; row 5 readability).
- Have `palantir/demo/script.md` open in a separate window/space, ready to
  glance at if you blank.
- Bridge terminal visible, sized so the most recent ~15 lines are readable.

You're ready.

---

## Failure mode reference

| Symptom | First fix to try |
|---|---|
| Bridge can't reach Foundry | Token expired? Regenerate. Re-paste in `.env`. |
| `Action 'create-channel' not found` | Channel type isn't marked Editable in Ontology Manager. |
| Bridge runs but never hydrates | Result files have non-UTF-8? Check `missions/failed/`. |
| Mission stuck in `executing` | Engine isn't watching `missions/inbox/`. Check engine terminal. |
| MissionPlanner refuses everything | Channel grounding empty. Re-run `seed_channels.py`. |
| Workshop shows zero missions | `load_existing_results.py` hasn't run, or Mission rows didn't link to Channel rows correctly. Re-run after fixing FK. |
| Detector pills all show "skipped" | That's correct — engine ran with `--titan` and `--google` disabled in this build. The grader honestly says "not run during grade — assumed clean," which is the right behavior. |

---

## Drop-to-demo-only mode (Option C)

If 30 minutes before the deadline anything is structurally broken:

1. Stop the bridge.
2. Run `load_existing_results.py` again to ensure all 4 missions are
   hydrated.
3. The New Mission live segment of the demo is replaced with: "Here's the
   intent the operator typed; here's the spec the planner produced," shown
   on a slide instead of live.
4. The local-engine demo segment runs against a separately-launched engine
   (no Foundry connection) for the credibility shot.

This keeps the Foundry surface visible (Mission Board + Authorization &
Audit views) without depending on the live round-trip. The demo still wins
on "Foundry-native, drops into existing Army Vantage tenants" — the live
loop just becomes recorded.
