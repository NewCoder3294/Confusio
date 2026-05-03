# Foundry Bridge

The local process that connects Foundry to the Mendacity engine. Lives on the
operator laptop. Owns both directions of the Option-A filesystem transport.

## What it does

```
Foundry ──poll──▶ bridge ──write──▶ missions/inbox/<id>.yaml ──▶ engine
   ▲                                                                │
   └─ingestMissionResult─── bridge ◀──watch── missions/results/<id>.json
```

Three loops, all running concurrently:

- **Outbound (every 2s):** find Mission objects in Foundry with
  `status='executing'` and no `dispatched_at`. Write the YAML spec to
  `missions/inbox/<id>.yaml` atomically. Call the `markDispatched` action.
- **Inbound (every 1s):** scan `missions/results/` for new `<id>.json`. Call
  `ingestMissionResult` action with the JSON. Move processed file to
  `missions/results/processed/`.
- **Watchdog (every 10s):** any mission still `executing` with `dispatched_at`
  older than 4 minutes and no result file → mark failed via
  `ingestMissionResult` with `error.code='engine_timeout'`.

A fourth loop (every 60s) syncs the `Channel` allowlist from the Ontology
down to `missions/sandbox_channels.json` so the engine's hard channel check
stays in step with Foundry.

## Why it exists

AIP Logic functions can't write to the laptop filesystem (they execute inside
Foundry). The brief's MissionDispatcher in §6.3 is replaced by this bridge.
See `PALANTIR_REQUESTS.md §1.1` for the full reasoning.

## Running it

```bash
cd palantir/bridge
cp .env.example .env
# Edit .env and fill in FOUNDRY_TOKEN and FOUNDRY_ONTOLOGY_RID.

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Sanity: one tick then exit, useful for verifying connectivity:
python foundry_bridge.py --once -v

# Then run for real:
python foundry_bridge.py
```

The bridge is meant to run in a long-lived terminal during the demo. Logs to
stderr; redirect to a file if you want a record:

```bash
python foundry_bridge.py 2>&1 | tee bridge-$(date +%Y%m%d-%H%M%S).log
```

## Gotchas

- **SDK surface drift.** The exact method names (`OntologyObject.search`,
  `Action.apply`) follow the current `foundry-platform-sdk` API. If your tenant
  expects OSDK-style typed access, the surface differs — adapt the four
  `client.ontologies...` calls in `foundry_bridge.py`. The structure of what
  the bridge does doesn't change; only how it talks to Foundry does.
- **Idempotency by design.** `outbound_tick` skips dispatch if either
  `missions/results/<id>.json` or `missions/inbox/<id>.yaml` exists — so you
  can crash the bridge and restart it during the demo without double-firing
  any mission.
- **Atomic writes everywhere.** Specs are written `<id>.yaml.tmp` then
  renamed. The engine should match (and we asked it to in
  `PALANTIR_REQUESTS.md §1.3`).
- **The watchdog is conservative.** It only marks a mission failed if there's
  truly no result file *and* dispatched_at is old. A delay between the engine
  writing and the bridge ingesting won't trigger a false failure.

## What this bridge intentionally does NOT do

- It doesn't define the Ontology. Build that in Foundry by hand
  (`palantir/ontology.md` is the spec).
- It doesn't author missions. The MissionPlanner AIP agent does that
  (`palantir/aip/mission_planner.md`).
- It doesn't render Workshop views. That's GUI-only
  (`palantir/workshop.md`).
- It doesn't talk to Telegram, generate images, or run provenance checks. The
  local engine (`src/mendacity/`, `social/`) owns all of that. The bridge is
  the dumb postal worker between Foundry and the engine.
