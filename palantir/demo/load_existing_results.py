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

`hydrate()` is idempotent — it does upsert via try-create-then-edit. The
slim 4-type schema means hydrate covers everything in one pass: Mission
gets persona + stages denormalized; Artifact + 3 DetectionResults are
created if the result has a final artifact.
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


def load_one(client, ontology_rid: str, path: Path) -> None:
    LOG.info("loading %s", path.name)
    with open(path) as f:
        result = json.load(f)
    plan = hydrate(result, client, ontology_rid)
    LOG.info("loaded %s — %s", path.name, plan)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        stream=sys.stderr,
    )

    if len(sys.argv) > 1:
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
