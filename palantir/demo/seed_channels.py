"""Seed the Channel ontology with the three sandbox channels.

Idempotent: re-running upserts the same 3 rows; never duplicates.

Run after the `Channel` object type is created in Foundry. Reads tenant
config from `palantir/bridge/.env` (so you only configure once).

    cd palantir/demo
    python seed_channels.py

Source of truth here matches `missions/sandbox_channels.json`. If you ever
edit the channel set, edit it here, run this script, and the bridge will
re-sync the JSON file from Foundry on its next sync cycle.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bridge"))
from foundry_bridge import BridgeConfig, make_client  # noqa: E402

LOG = logging.getLogger("mendacity.seed")


CHANNELS = [
    {
        "channel_id": "mendacity_sandbox_demo",
        "platform": "telegram",
        "display_name": "@mendacity_sandbox_demo",
        "is_sandbox": True,
        "audience_profile": "Russian-speaking, pro-regime, junior officers",
    },
    {
        "channel_id": "inscom_lab_sandbox",
        "platform": "telegram",
        "display_name": "@inscom_lab_sandbox",
        "is_sandbox": True,
        "audience_profile": "Mandarin-speaking, semi-active, regional militia adjacent",
    },
    {
        "channel_id": "hackathon_sandbox_alpha",
        "platform": "telegram",
        "display_name": "@hackathon_sandbox_alpha",
        "is_sandbox": True,
        "audience_profile": "Farsi-speaking, fence-sitters, young professional class",
    },
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def upsert_channel(client, ontology_rid: str, row: dict) -> None:
    """Try edit-channel first; fall back to create-channel if it doesn't exist."""
    payload = {**row, "created_at": _now_iso()}
    try:
        client.ontologies.Ontology.Action.apply(
            ontology=ontology_rid,
            action="edit-channel",
            parameters=payload,
        )
        LOG.info("updated channel %s", row["channel_id"])
    except Exception as e_edit:
        try:
            client.ontologies.Ontology.Action.apply(
                ontology=ontology_rid,
                action="create-channel",
                parameters=payload,
            )
            LOG.info("created channel %s", row["channel_id"])
        except Exception as e_create:
            LOG.error(
                "failed to upsert channel %s: edit_err=%s create_err=%s",
                row["channel_id"], e_edit, e_create,
            )
            raise


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        stream=sys.stderr,
    )
    cfg = BridgeConfig.from_env()
    client = make_client(cfg)
    LOG.info("seeding %d channels into ontology %s", len(CHANNELS), cfg.ontology_rid)
    for row in CHANNELS:
        upsert_channel(client, cfg.ontology_rid, row)
    LOG.info("done")


if __name__ == "__main__":
    main()
