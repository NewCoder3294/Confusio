"""Hydrate the 4 SHADOW-FOX results already on disk into Foundry.

Run once after the Ontology is built and channels are seeded. Populates the
Mission Board with visual density before the live demo, so the dashboard
isn't empty even if the live segment slips.

Idempotent — re-running just upserts the same rows. The bridge's normal
ingest loop is *not* needed for this; this is the pre-demo backfill.

    cd palantir/demo
    python load_existing_results.py

To load only a subset, pass result filenames:

    python load_existing_results.py SHADOW-FOX-001.json SHADOW-FOX-002.json

For the demo, you also need Mission rows to exist before hydrate() can update
them — the engine's results don't include all the planning-phase fields the
Ontology expects. So this script:

  1. Creates a minimal Mission row for each result (status=draft initially).
  2. Calls approveMission to mark it executing (so the bridge won't try to
     re-dispatch).
  3. Calls hydrate() to fill in everything else from the result.

Side effect: Mission.dispatched_at is set to result.started_at so the
bridge's outbound loop ignores them on its next pass.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO_ROOT / "missions" / "results"

sys.path.insert(0, str(REPO_ROOT / "palantir" / "bridge"))
sys.path.insert(0, str(REPO_ROOT / "palantir" / "aip"))

from foundry_bridge import BridgeConfig, make_client  # noqa: E402
from result_ingester import hydrate  # noqa: E402

LOG = logging.getLogger("mendacity.load")


def ensure_mission_row(client, ontology_rid: str, result: dict) -> None:
    """Create a Mission row sufficient for hydrate() to update.

    The Ontology has required fields (target_channel_id, must_pass, ...) that
    aren't in the result top-level — they're in result.spec. Mirror them onto
    the Mission row so foreign keys resolve.
    """
    spec = result.get("spec") or {}
    target = spec.get("target") or {}
    persona = spec.get("persona") or {}
    artifact = spec.get("artifact") or {}
    delivery = spec.get("delivery") or {}
    auth = spec.get("authorization") or {}

    # Map Channel display_name → channel_id (strip leading @, replace - with _).
    channel_display = target.get("channel", "")
    channel_id = channel_display.lstrip("@").replace("-", "_")

    fields = {
        "mission_id": result["mission_id"],
        "operator": result.get("operator", "J2-INSCOM-Demo"),
        "authority": auth.get("authority", "title-10"),
        "target_class": auth.get("target_class", "foreign"),
        "approval_chain": auth.get("approval_chain", ["J2", "OGC-reviewed"]),
        "status": "draft",   # hydrate() will overwrite from result.status
        "target_channel_id": channel_id,
        "audience_profile": target.get("audience_profile", ""),
        "artifact_prompt": artifact.get("prompt", ""),
        "must_pass": artifact.get("must_pass", ["c2pa", "titan", "synthid"]),
        "strip_watermarks": artifact.get("strip_watermarks", True),
        "dispatched_at": result.get("started_at"),
        "created_at": result.get("started_at"),
        "dry_run": delivery.get("dry_run", True),
        "caption_preview": delivery.get("caption", ""),
    }

    try:
        client.ontologies.Ontology.Action.apply(
            ontology=ontology_rid,
            action="edit-mission",
            parameters=fields,
        )
    except Exception:
        client.ontologies.Ontology.Action.apply(
            ontology=ontology_rid,
            action="create-mission",
            parameters=fields,
        )


def load_one(client, ontology_rid: str, path: Path) -> None:
    LOG.info("loading %s", path.name)
    with open(path) as f:
        result = json.load(f)
    ensure_mission_row(client, ontology_rid, result)
    plan = hydrate(result, client, ontology_rid)
    LOG.info("loaded %s — %s", path.name, plan)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        stream=sys.stderr,
    )

    if len(sys.argv) > 1:
        # Specific files, named relative to RESULTS_DIR or absolute.
        targets: list[Path] = []
        for arg in sys.argv[1:]:
            p = Path(arg)
            if not p.is_absolute():
                p = RESULTS_DIR / arg
            if not p.exists():
                LOG.error("not found: %s", p)
                sys.exit(1)
            targets.append(p)
    else:
        targets = sorted(RESULTS_DIR.glob("SHADOW-FOX-*.json"))

    if not targets:
        LOG.error("no result files matched")
        sys.exit(1)

    cfg = BridgeConfig.from_env()
    client = make_client(cfg)
    LOG.info("loading %d result file(s) into ontology %s", len(targets), cfg.ontology_rid)
    for p in targets:
        load_one(client, cfg.ontology_rid, p)
    LOG.info("done — Mission Board should now show %d missions", len(targets))


if __name__ == "__main__":
    main()
