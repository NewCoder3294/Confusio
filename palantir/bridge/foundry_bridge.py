"""Mendacity ↔ Foundry bridge process.

Lives on the operator laptop. Owns both directions of the Option-A filesystem
transport (see PALANTIR_REQUESTS.md §1.1):

    Foundry ──poll──▶ bridge ──write──▶ missions/inbox/<id>.yaml ──▶ engine
       ▲                                                                │
       └──ingestMissionResult action──── bridge ◀──watch── missions/results/<id>.json

This is the *only* component that touches both the laptop filesystem and the
Foundry tenant. AIP Logic functions cannot reach the operator laptop, so the
brief's MissionDispatcher (§6.3) is replaced by this bridge.

The bridge is intentionally boring: tight loops, atomic writes, idempotent
action calls. If something goes wrong it logs and keeps going — never wedge
the demo because of a transient error.

Usage:
    cp .env.example .env
    # fill in FOUNDRY_TOKEN
    pip install -r requirements.txt
    python foundry_bridge.py

Run with --once for a single poll cycle (useful for debugging).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import signal
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# The Foundry SDK import is wrapped so the bridge fails loudly with a useful
# message if the dependency isn't installed yet — better than a cryptic
# ModuleNotFoundError mid-demo.
try:
    from foundry_sdk import FoundryClient
    from foundry_sdk import UserTokenAuth
except ImportError as e:  # pragma: no cover
    raise SystemExit(
        "foundry-platform-sdk is not installed. Run `pip install -r requirements.txt`."
    ) from e

# Hydration logic lives in palantir/aip/result_ingester.py — the bridge imports
# it so result parsing is testable independent of the Foundry SDK.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "aip"))
from result_ingester import hydrate as hydrate_result  # noqa: E402


# ──────────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[2]
MISSIONS_DIR = REPO_ROOT / "missions"
INBOX_DIR = MISSIONS_DIR / "inbox"
RESULTS_DIR = MISSIONS_DIR / "results"
PROCESSED_DIR = RESULTS_DIR / "processed"
FAILED_DIR = MISSIONS_DIR / "failed"
SANDBOX_CHANNELS_FILE = MISSIONS_DIR / "sandbox_channels.json"

# Polling cadence
OUTBOUND_POLL_SECONDS = 2.0          # Foundry → engine
INBOUND_POLL_SECONDS = 1.0           # results dir scan
CHANNEL_SYNC_SECONDS = 60.0          # sandbox_channels.json refresh
MISSION_TIMEOUT_SECONDS = 240.0      # 4 minutes — see PALANTIR_REQUESTS §6.5

LOG = logging.getLogger("mendacity.bridge")


# ──────────────────────────────────────────────────────────────────────────────
# Foundry client
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class BridgeConfig:
    foundry_host: str
    foundry_token: str
    ontology_rid: str

    @classmethod
    def from_env(cls) -> "BridgeConfig":
        load_dotenv(Path(__file__).parent / ".env")
        host = os.environ.get("FOUNDRY_HOST", "https://nicolasdossantos.usw-18.palantirfoundry.com")
        token = os.environ.get("FOUNDRY_TOKEN")
        ontology_rid = os.environ.get("FOUNDRY_ONTOLOGY_RID")
        if not token:
            raise SystemExit(
                "FOUNDRY_TOKEN is not set. Copy .env.example to .env and fill in the service-user token."
            )
        if not ontology_rid:
            raise SystemExit(
                "FOUNDRY_ONTOLOGY_RID is not set. Open the Ontology in Foundry, copy the rid from the URL, set it in .env."
            )
        return cls(foundry_host=host, foundry_token=token, ontology_rid=ontology_rid)


def make_client(cfg: BridgeConfig) -> FoundryClient:
    auth = UserTokenAuth(token=cfg.foundry_token)
    return FoundryClient(auth=auth, hostname=cfg.foundry_host)


# ──────────────────────────────────────────────────────────────────────────────
# Atomic file I/O
# ──────────────────────────────────────────────────────────────────────────────


def atomic_write_text(path: Path, content: str) -> None:
    """Write content to path via tmp + os.rename so a watcher never sees a half file."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.fsync(tmp.open("rb").fileno()) if False else None  # left as a hint; rename is atomic on POSIX
    os.replace(tmp, path)


def safe_move(src: Path, dst_dir: Path) -> Path:
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / src.name
    if dst.exists():
        # Don't clobber; suffix with timestamp so the audit trail is preserved.
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dst = dst_dir / f"{src.stem}.{stamp}{src.suffix}"
    shutil.move(str(src), str(dst))
    return dst


# ──────────────────────────────────────────────────────────────────────────────
# Outbound: Foundry → engine
# ──────────────────────────────────────────────────────────────────────────────


def fetch_executing_missions(client: FoundryClient, ontology_rid: str) -> list[dict[str, Any]]:
    """Return Mission objects with status='executing' AND dispatched_at IS NULL.

    SDK call shape — adjust to your generated client. The pattern below uses the
    object-set search; if your tenant uses OSDK, swap to the typed query.
    """
    # NOTE: foundry-platform-sdk surface varies across versions. Either of:
    #   client.ontologies.objects.list(ontology=ontology_rid, type="Mission", filter=...)
    #   client.ontology(ontology_rid).objects("Mission").search(...)
    # works depending on SDK version. Pin and adapt once we know the exact installed version.
    response = client.ontologies.Ontology.OntologyObject.search(
        ontology=ontology_rid,
        object_type="Mission",
        where={
            "type": "and",
            "value": [
                {"type": "eq", "field": "status", "value": "executing"},
                {"type": "isNull", "field": "dispatched_at"},
            ],
        },
    )
    return [obj.to_dict() if hasattr(obj, "to_dict") else dict(obj) for obj in response.data]


def write_spec_to_inbox(mission: dict[str, Any]) -> Path:
    """Render the Mission ontology object back into a YAML MissionSpec and drop in inbox."""
    mission_id = mission["mission_id"]

    # Recover the channel display_name (with @) from the linked Channel object.
    # In the real call we'd resolve the FK; for now the bridge expects the
    # ingestion side to denormalize Channel.display_name onto Mission as well.
    channel_display = mission.get("target_channel_display_name") or mission["target_channel_id"]

    spec = {
        "mission_id": mission_id,
        "operator": mission["operator"],
        "authorization": {
            "authority": mission["authority"],
            "target_class": mission["target_class"],
            "approval_chain": mission.get("approval_chain", ["J2", "OGC-reviewed"]),
        },
        "target": {
            "platform": "telegram",
            "channel": channel_display,
            "audience_profile": mission.get("audience_profile", ""),
        },
        "persona": {
            # The Mission row carries the persona spec inline pre-execution.
            # Once executed, a Persona ontology row is created from the result.
            "archetype": mission.get("persona_archetype", "operator-supplied"),
            "name_seed": mission.get("persona_name_seed", "Operator"),
            "generate_avatar": False,
        },
        "artifact": {
            "type": "image",
            "prompt": mission["artifact_prompt"],
            "source": mission.get("artifact_source", "fixture:assets/Gemini_Generated_Image_uzqgniuzqgniuzqg_apple_meta.jpg"),
            "exif_template": "fixtures/koze_iphonex_gist.json",
            "must_pass": mission.get("must_pass", ["c2pa", "titan", "synthid"]),
            "strip_watermarks": mission.get("strip_watermarks", True),
        },
        "delivery": {
            "schedule": "immediate",
            "thread_strategy": mission.get("thread_strategy", "cold_post"),
            "caption": mission.get("caption_preview", "[caption supplied at runtime]"),
            "dry_run": mission.get("dry_run", True),
        },
    }

    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    out = INBOX_DIR / f"{mission_id}.yaml"
    atomic_write_text(out, yaml.safe_dump(spec, sort_keys=False, allow_unicode=True))
    LOG.info("wrote spec to %s", out)
    return out


def call_mark_dispatched(client: FoundryClient, ontology_rid: str, mission_id: str) -> None:
    client.ontologies.Ontology.Action.apply(
        ontology=ontology_rid,
        action="markDispatched",
        parameters={"mission_id": mission_id},
    )


def outbound_tick(client: FoundryClient, cfg: BridgeConfig) -> None:
    try:
        missions = fetch_executing_missions(client, cfg.ontology_rid)
    except Exception as e:
        LOG.warning("outbound fetch failed: %s", e)
        return
    for m in missions:
        mid = m["mission_id"]
        # Idempotency: if a result already exists, the engine has already finished;
        # don't re-drop the spec. Also don't re-drop if the inbox file is present.
        if (RESULTS_DIR / f"{mid}.json").exists():
            LOG.debug("skip dispatch for %s — result already on disk", mid)
            continue
        if (INBOX_DIR / f"{mid}.yaml").exists():
            LOG.debug("skip dispatch for %s — already in inbox", mid)
            continue
        try:
            write_spec_to_inbox(m)
            call_mark_dispatched(client, cfg.ontology_rid, mid)
        except Exception as e:
            LOG.error("failed to dispatch %s: %s", mid, e)


# ──────────────────────────────────────────────────────────────────────────────
# Inbound: engine → Foundry
# ──────────────────────────────────────────────────────────────────────────────


def inbound_tick(client: FoundryClient, cfg: BridgeConfig) -> None:
    if not RESULTS_DIR.exists():
        return
    for path in sorted(RESULTS_DIR.glob("*.json")):
        if path.name.endswith(".tmp"):
            continue  # half-written, skip this tick
        try:
            content = path.read_text(encoding="utf-8")
            result = json.loads(content)
        except json.JSONDecodeError as e:
            LOG.error("malformed result %s: %s", path, e)
            safe_move(path, FAILED_DIR)
            continue
        try:
            plan = hydrate_result(result, client, cfg.ontology_rid)
            LOG.info("hydrated %s: %s", path.name, plan)
        except Exception as e:
            LOG.error("hydration failed for %s: %s — leaving in results/ for retry", path, e)
            continue
        moved_to = safe_move(path, PROCESSED_DIR)
        LOG.info("ingested %s → %s", path.name, moved_to)


# ──────────────────────────────────────────────────────────────────────────────
# Channel sync: Foundry → laptop
# ──────────────────────────────────────────────────────────────────────────────


def sync_sandbox_channels(client: FoundryClient, cfg: BridgeConfig) -> None:
    """Refresh missions/sandbox_channels.json from the Channel ontology.

    Atomic write (tmp + rename). Engine is guaranteed to never see a partial file.
    """
    try:
        response = client.ontologies.Ontology.OntologyObject.search(
            ontology=cfg.ontology_rid,
            object_type="Channel",
            where={"type": "eq", "field": "is_sandbox", "value": True},
        )
        channels = [
            obj.to_dict() if hasattr(obj, "to_dict") else dict(obj)
            for obj in response.data
        ]
    except Exception as e:
        LOG.warning("channel sync fetch failed: %s — leaving file untouched", e)
        return

    payload = {
        "_comment": (
            "Hard allowlist of sandbox-only channels. Source: Foundry Ontology "
            "(Channel where is_sandbox=true). Synced by palantir/bridge/foundry_bridge.py. "
            "Do not edit directly — edits will be overwritten on next sync."
        ),
        "_synced_at": datetime.now(timezone.utc).isoformat(),
        "allowed_channels": sorted(c["display_name"] for c in channels),
    }
    atomic_write_text(SANDBOX_CHANNELS_FILE, json.dumps(payload, indent=2) + "\n")
    LOG.info("synced %d channels to %s", len(channels), SANDBOX_CHANNELS_FILE)


# ──────────────────────────────────────────────────────────────────────────────
# Watchdog: missions stuck in 'executing' too long → fail them
# ──────────────────────────────────────────────────────────────────────────────


def watchdog_tick(client: FoundryClient, cfg: BridgeConfig) -> None:
    try:
        # Re-use outbound query but filter for missions dispatched > timeout ago without a result.
        response = client.ontologies.Ontology.OntologyObject.search(
            ontology=cfg.ontology_rid,
            object_type="Mission",
            where={"type": "eq", "field": "status", "value": "executing"},
        )
    except Exception as e:
        LOG.warning("watchdog fetch failed: %s", e)
        return

    now = datetime.now(timezone.utc)
    for obj in response.data:
        m = obj.to_dict() if hasattr(obj, "to_dict") else dict(obj)
        dispatched = m.get("dispatched_at")
        if not dispatched:
            continue
        # Tolerate ISO-8601 with or without trailing Z.
        try:
            dt = datetime.fromisoformat(dispatched.replace("Z", "+00:00"))
        except ValueError:
            continue
        if (now - dt).total_seconds() < MISSION_TIMEOUT_SECONDS:
            continue
        mid = m["mission_id"]
        if (RESULTS_DIR / f"{mid}.json").exists():
            # Result is on disk; let inbound_tick handle it. Don't fail prematurely.
            continue
        LOG.warning("mission %s exceeded timeout — marking failed", mid)
        try:
            synthetic_result = {
                "mission_id": mid,
                "status": "failed",
                "started_at": dispatched,
                "finished_at": now.isoformat(),
                "stages": [],
                "final_artifact_path": None,
                "final_provenance_report": None,
                "error": {
                    "stage": "engine",
                    "code": "engine_timeout",
                    "message": f"No result file after {MISSION_TIMEOUT_SECONDS:.0f}s",
                },
                "spec": None,
            }
            hydrate_result(synthetic_result, client, cfg.ontology_rid)
        except Exception as e:
            LOG.error("watchdog ingest failed for %s: %s", mid, e)


# ──────────────────────────────────────────────────────────────────────────────
# Main loop
# ──────────────────────────────────────────────────────────────────────────────


_running = True


def _handle_signal(signum, frame):  # pragma: no cover
    global _running
    LOG.info("received signal %d, shutting down", signum)
    _running = False


def run(once: bool = False) -> None:
    cfg = BridgeConfig.from_env()
    client = make_client(cfg)

    LOG.info("bridge starting — host=%s ontology=%s", cfg.foundry_host, cfg.ontology_rid)

    # Ensure dirs exist on first run.
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    FAILED_DIR.mkdir(parents=True, exist_ok=True)

    # First sync of channel allowlist before anything else, so the engine has a
    # fresh file to validate against on its next mission.
    sync_sandbox_channels(client, cfg)
    last_channel_sync = time.monotonic()

    if once:
        outbound_tick(client, cfg)
        inbound_tick(client, cfg)
        watchdog_tick(client, cfg)
        return

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    last_outbound = 0.0
    last_inbound = 0.0
    last_watchdog = 0.0

    while _running:
        now = time.monotonic()
        if now - last_outbound >= OUTBOUND_POLL_SECONDS:
            outbound_tick(client, cfg)
            last_outbound = now
        if now - last_inbound >= INBOUND_POLL_SECONDS:
            inbound_tick(client, cfg)
            last_inbound = now
        if now - last_watchdog >= 10.0:  # watchdog every 10s — cheap, single query
            watchdog_tick(client, cfg)
            last_watchdog = now
        if now - last_channel_sync >= CHANNEL_SYNC_SECONDS:
            sync_sandbox_channels(client, cfg)
            last_channel_sync = now
        time.sleep(0.25)

    LOG.info("bridge stopped cleanly")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--once", action="store_true", help="single tick then exit (debugging)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        stream=sys.stderr,
    )
    run(once=args.once)


if __name__ == "__main__":
    main()
