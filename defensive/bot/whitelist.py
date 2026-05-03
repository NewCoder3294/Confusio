"""Telegram whitelist config loader. Maps user IDs to operator identities."""
from __future__ import annotations

import os
from pathlib import Path

import yaml


def default_path() -> Path:
    override = os.environ.get("DEFENSIVE_WHITELIST_PATH")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "whitelist.yaml"


def load(path: Path | None = None) -> dict[int, str]:
    """Load { telegram_user_id: operator_identity } from YAML.
    Returns empty dict if the file is missing — bot then rejects everyone.
    """
    p = path or default_path()
    if not p.exists():
        return {}
    raw = yaml.safe_load(p.read_text()) or {}
    return {int(k): str(v) for k, v in raw.items()}


def lookup(user_id: int, mapping: dict[int, str] | None = None) -> str | None:
    m = mapping if mapping is not None else load()
    return m.get(user_id)
