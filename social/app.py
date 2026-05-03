"""Mendacity operator console — dossier-grade Streamlit dashboard.

Runs as a separate process from the orchestrator daemon. Communicates with
the daemon by reading and writing the shared sqlite DB (and append-only log).
This UI never touches Telethon directly — all Telegram I/O is the daemon's
responsibility.

Aesthetic: dark warm-tinted near-black, Palantir density crossed with a
declassified-document dossier. IBM Plex Sans / Serif / Mono. Status colors
are the only saturated ink on the surface; everything else is warm neutrals.

Run: streamlit run social/app.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Streamlit's script runner only puts the script's own directory on sys.path,
# not the project root. Prepend the project root so `from social.…` works
# whether the app is launched via `streamlit run social/app.py` or via the
# headless test harness.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st

from social.orchestrator import (
    HEARTBEAT_PATH,
    CampaignValidationError,
    Orchestrator,
)
from social.personas import load_personas
from social.storage import (
    Campaign,
    GeneratedPost,
    Storage,
)

CHANNEL_CFG_PATH = Path(__file__).parent / "config" / "channel_config.json"
DB_PATH = Path(__file__).parent / "mendacity.db"

ROLE_OPTIONS = ["seed", "witness", "reaction", "aggregator"]

# Status palette — Full palette per shape brief. Each status owns one named
# dignified hue. These are the ONLY saturated colors on the surface.
STATUS_COLORS: dict[str, str] = {
    "pending_approval": "#C28D2A",  # amber — awaiting decision
    "approved":         "#3F7D78",  # muted teal — committed, queued
    "posted":           "#9B2A2A",  # oxblood — irreversible, live
    "failed":           "#D14E4E",  # vermillion — alert
    "rejected":         "#7A6B7E",  # faded mauve — discarded / redacted
}

STATUS_LABEL: dict[str, str] = {
    "pending_approval": "PENDING APPROVAL",
    "approved":         "APPROVED — POSTING",
    "posted":           "POSTED",
    "failed":           "FAILED — RETRYABLE",
    "rejected":         "REJECTED — DISCARDED",
}

ROLE_GLYPH: dict[str, str] = {
    "seed":       "I",
    "witness":    "II",
    "reaction":   "III",
    "aggregator": "IV",
}

HEARTBEAT_GRACE_SECONDS = 12.0


# ────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────


def _run(coro):
    return asyncio.run(coro)


@st.cache_resource
def _get_personas():
    return load_personas(require_sessions=False)


@st.cache_resource
def _get_orchestrator():
    """UI-only orchestrator instance for routing operator actions into the DB.

    No real PersonaAgents — those need live Telethon sessions and live in
    the daemon process. Validation is overridden to still check roster IDs
    against persona files.
    """
    personas = _get_personas()
    storage = Storage()
    _run(storage.init())

    class _UIOnlyOrch(Orchestrator):
        def __init__(self):
            super().__init__(agents={}, storage=storage)
            self._known_persona_ids = set(personas.keys())

        def _validate_campaign(self, campaign):
            if (
                self.allowed_channels
                and campaign.channel not in self.allowed_channels
            ):
                raise CampaignValidationError(
                    f"channel {campaign.channel} not on the allow-list. "
                    "Edit social/config/channel_config.json."
                )
            self._seed_persona(campaign)
            unknown = [
                pid for pid in campaign.roster if pid not in self._known_persona_ids
            ]
            if unknown:
                raise CampaignValidationError(
                    f"unknown personas in roster: {unknown}"
                )
            lo, hi = campaign.delay_range_seconds
            if lo < 0 or hi < lo:
                raise CampaignValidationError(
                    f"invalid delay range {campaign.delay_range_seconds}"
                )

    return _UIOnlyOrch()


def _allowed_channels() -> list[str]:
    if not CHANNEL_CFG_PATH.exists():
        return []
    return json.loads(CHANNEL_CFG_PATH.read_text(encoding="utf-8")).get(
        "allowed_channels", []
    )


def _operator_id() -> str:
    import os

    return os.getenv("OPERATOR_USER_ID", "UNKNOWN")


def _heartbeat_state() -> tuple[str, float | None]:
    """Return (status_label, age_seconds_or_none)."""
    if not HEARTBEAT_PATH.exists():
        return "OFFLINE", None
    age = time.time() - HEARTBEAT_PATH.stat().st_mtime
    if age > HEARTBEAT_GRACE_SECONDS:
        return "STALE", age
    return "ARMED", age


def _short_channel(channel: str) -> str:
    if channel.startswith("https://"):
        return channel.replace("https://", "")
    return channel


def _format_ts_short(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso).strftime("%H:%M:%S")
    except (ValueError, TypeError):
        return iso[:19]


def _format_ts_full(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        return iso


# ────────────────────────────────────────────────────────────────────────
# Style — injected at top of every render
# ────────────────────────────────────────────────────────────────────────


def _inject_style() -> None:
    css = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Serif:wght@400;600;700&display=swap" rel="stylesheet">
<style>
:root {
  /* Light mode — declassified-dossier palette. Variable names are legacy
     from the dark theme; values now invert (--ink-* = paper tones,
     --paper-* = ink tones). */
  --ink-0: #F1ECE0;          /* page bg — warm cream */
  --ink-1: #E6E0D0;          /* sidebar / banner — card stock */
  --ink-2: #EDE7D7;          /* panel bg (depth 1) */
  --ink-3: #FBF7EC;          /* card bg (depth 2) — bright paper */
  --ink-4: #D9D2BD;          /* hover / inset (depth 3) */
  --rule:  #B8B19C;
  --rule-soft: #D4CDB8;
  --rule-strong: #6B6452;
  --paper: #16140F;          /* primary ink */
  --paper-muted: #5C5749;
  --paper-faint: #8A8472;

  --pending:  #16140F;
  --approved: #16140F;
  --posted:   #16140F;
  --failed:   #16140F;
  --rejected: #8A8472;

  --serif: 'IBM Plex Serif', Georgia, serif;
  --sans:  'IBM Plex Sans', -apple-system, BlinkMacSystemFont, sans-serif;
  --mono:  'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
}

/* Reset Streamlit chrome */
html, body, [data-testid="stAppViewContainer"] {
  background: var(--ink-0) !important;
  color: var(--paper) !important;
  font-family: var(--sans);
}
[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stStatusWidget"],
[data-testid="stDecoration"],
[data-testid="stAppDeployButton"],
.stDeployButton,
.stAppDeployButton,
.stMainMenu {
  display: none !important;
  visibility: hidden !important;
}
.block-container {
  padding-top: 0.5rem !important;
  padding-bottom: 4rem !important;
  padding-left: 2.5rem !important;
  padding-right: 2.5rem !important;
  max-width: 1280px !important;
}
footer { visibility: hidden; }
[data-testid="stMain"] [data-testid="stMainBlockContainer"] { gap: 0 !important; }

/* Type system */
body, p, div, span, li, label {
  font-family: var(--sans);
  font-size: 14.5px;
  line-height: 1.55;
  color: var(--paper);
}
code, pre, kbd, .mono { font-family: var(--mono); }
.mono { font-size: 12.5px; letter-spacing: 0.01em; }

/* ──── classification banner ──── */
.banner {
  position: sticky;
  top: 0;
  z-index: 50;
  border-top: 1px solid var(--rule);
  border-bottom: 1px solid var(--rule);
  padding: 10px 16px 8px 16px;
  margin: -0.25rem -1.5rem 18px -1.5rem;
  background: var(--ink-1);
  font-family: var(--mono);
  font-size: 11.5px;
  letter-spacing: 0.10em;
  color: var(--paper-muted);
  display: flex;
  flex-wrap: wrap;
  gap: 6px 18px;
  align-items: center;
}
.banner .b-title {
  color: var(--paper);
  font-weight: 600;
  letter-spacing: 0.20em;
}
.banner .b-sep {
  color: var(--paper-faint);
  user-select: none;
  opacity: 0.7;
}
.banner .b-key { color: var(--paper-faint); font-size: 10.5px; }
.banner .b-val { color: var(--paper); font-weight: 500; }
.banner .spacer { flex: 1 1 auto; }

/* KPI strip on the right side of the banner */
.kpis { display: inline-flex; gap: 2px; align-items: stretch; }
.kpi {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--rule);
  background: var(--ink-0);
  padding: 4px 11px 3px 11px;
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.18em;
  color: var(--paper-faint);
  text-transform: uppercase;
}
.kpi .n { color: var(--paper); font-size: 13px; font-weight: 600; letter-spacing: 0; }
.kpi.pending  { color: var(--paper); border-color: var(--paper); }
.kpi.pending .n { color: var(--paper); }
.kpi.posted {
  color: var(--ink-0); background: var(--paper); border-color: var(--paper);
}
.kpi.posted .n { color: var(--ink-0); }
.kpi.failed   { color: var(--paper); border-color: var(--paper); border-width: 2px; }
.kpi.failed .n  { color: var(--paper); }
.kpi.active   { color: var(--paper-muted); }
.kpi.active .n  { color: var(--paper); }

.system-armed     { color: var(--paper) !important; }
.system-stale     { color: var(--paper-muted) !important; }
.system-offline   { color: var(--paper-faint) !important; }
.system-dot {
  display: inline-block; width: 6px; height: 6px; border-radius: 50%;
  background: currentColor; margin-right: 6px; vertical-align: middle;
  box-shadow: 0 0 6px currentColor;
}

/* ──── section panels (each section wrapped in its own elevated panel) ──── */
[data-testid="stMain"] [data-testid="stContainer"][class*="border"],
[data-testid="stMain"] [data-testid="stVerticalBlockBorderWrapper"]:has(> [data-testid="stVerticalBlock"]):has([class*="dcard"]) {
  background: var(--ink-2) !important;
  border: 1px solid var(--rule) !important;
  border-radius: 0 !important;
}
.panel-wrap {
  background: var(--ink-2);
  border: 1px solid var(--rule);
  margin-bottom: 32px;
  position: relative;
}
.panel-wrap::before {
  content: '';
  position: absolute;
  top: -1px; left: -1px;
  width: 12px; height: 12px;
  border-top: 1px solid var(--paper-faint);
  border-left: 1px solid var(--paper-faint);
}
.panel-wrap::after {
  content: '';
  position: absolute;
  bottom: -1px; right: -1px;
  width: 12px; height: 12px;
  border-bottom: 1px solid var(--paper-faint);
  border-right: 1px solid var(--paper-faint);
}

/* Section headers (dossier markers, sit at the top of each panel) */
.section-head {
  display: flex; align-items: center; gap: 16px;
  padding: 18px 24px 16px 24px;
  margin: 0;
  background: var(--ink-1);
  border-bottom: 1px solid var(--rule);
  font-family: var(--sans);
  text-transform: uppercase;
  color: var(--paper-muted);
}
.section-head .sn {
  color: var(--paper);
  font-family: var(--serif);
  font-style: italic;
  font-size: 22px;
  letter-spacing: 0.02em;
  font-weight: 700;
  line-height: 1;
  min-width: 38px;
  border-right: 1px solid var(--rule);
  padding-right: 16px;
}
.section-head .stitle {
  color: var(--paper);
  font-weight: 700;
  font-size: 16px;
  letter-spacing: 0.18em;
}
.section-head .sub {
  margin-left: auto;
  color: var(--paper-faint);
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.20em;
}

.section-body {
  padding: 22px 24px 24px 24px;
}

/* ──── stamps ──── */
.stamp {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 4px 10px 3px 10px;
  border: 1px solid currentColor;
  font-family: var(--mono);
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.20em;
  text-transform: uppercase;
  border-radius: 1px;
}
.stamp.pending  { color: var(--paper); border-color: var(--paper); }
.stamp.approved {
  color: var(--paper); border-color: var(--paper);
  background: rgba(22,20,15,0.05);
}
.stamp.posted {
  color: var(--ink-0); background: var(--paper); border-color: var(--paper);
}
.stamp.failed {
  color: var(--paper); border-color: var(--paper); border-width: 2px;
  background: repeating-linear-gradient(
    -45deg, transparent 0 4px, rgba(22,20,15,0.08) 4px 6px
  );
}
.stamp.rejected {
  color: var(--paper-faint); border-color: var(--paper-faint);
  border-style: dashed;
}
.stamp .dot {
  width: 6px; height: 6px; background: currentColor; border-radius: 0;
}
.stamp.posted .dot { background: var(--ink-0); }

/* ──── nested st.container = post card (depth 2) ──── */
[data-testid="stMain"]
  [data-testid="stVerticalBlockBorderWrapper"]
  [data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--ink-3) !important;
  border: 1px solid var(--rule-strong) !important;
  margin-bottom: 14px !important;
  margin-top: 0 !important;
}
[data-testid="stMain"]
  [data-testid="stVerticalBlockBorderWrapper"]
  [data-testid="stVerticalBlockBorderWrapper"]::before,
[data-testid="stMain"]
  [data-testid="stVerticalBlockBorderWrapper"]
  [data-testid="stVerticalBlockBorderWrapper"]::after {
  display: none;
}
[data-testid="stMain"]
  [data-testid="stVerticalBlockBorderWrapper"]
  [data-testid="stVerticalBlockBorderWrapper"]
  > [data-testid="stVerticalBlock"] {
  padding: 0 !important;
}

/* ──── post card internals (head / meta / content label / foot) ──── */
.post-head {
  display: flex; justify-content: space-between; align-items: center;
  gap: 12px;
  padding: 16px 22px;
  background: var(--ink-1);
  border-bottom: 1px solid var(--rule);
}
.post-head-left {
  display: flex; align-items: center; gap: 12px;
}
.post-role-chip {
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.20em;
  color: var(--paper-faint);
  text-transform: uppercase;
  padding-left: 12px;
  border-left: 1px solid var(--rule);
}
.post-head-right {
  font-size: 11px;
  color: var(--paper-faint);
  letter-spacing: 0.10em;
}
.post-meta {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px 24px;
  padding: 18px 22px;
  border-bottom: 1px solid var(--rule-soft);
}
.post-meta > div { display: flex; flex-direction: column; gap: 4px; }
.post-meta .k {
  font-family: var(--mono);
  font-size: 9.5px;
  letter-spacing: 0.20em;
  text-transform: uppercase;
  color: var(--paper-faint);
}
.post-meta .v { color: var(--paper); font-size: 12.5px; }
.post-meta .v.mono { font-family: var(--mono); font-size: 11.5px; color: var(--paper-muted); }
.post-content-label {
  padding: 16px 22px 6px 22px;
  font-family: var(--mono);
  font-size: 9.5px;
  letter-spacing: 0.20em;
  color: var(--paper-faint);
  text-transform: uppercase;
}
.post-foot {
  display: flex; justify-content: space-between; align-items: center;
  gap: 14px;
  padding: 12px 22px;
  margin-top: 6px;
  background: var(--ink-2);
  border-top: 1px solid var(--rule-soft);
  font-size: 10.5px;
  color: var(--paper-faint);
  letter-spacing: 0.10em;
}

/* Push the textarea inside the post card to span edge-to-edge cleanly */
[data-testid="stMain"]
  [data-testid="stVerticalBlockBorderWrapper"]
  [data-testid="stVerticalBlockBorderWrapper"]
  [data-testid="stTextArea"] {
  padding: 0 22px !important;
  margin-top: -6px !important;
}

/* ──── (legacy) dossier card kept for sidebar/active campaigns ──── */
.dcard {
  background: var(--ink-3);
  border: 1px solid var(--rule-strong);
  border-left-width: 1px;
  margin: 0;
  padding: 0;
}
.dcard-head {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px;
  padding: 18px 26px 14px 26px;
  border-bottom: 1px solid var(--rule-soft);
}
.dcard-meta {
  display: grid;
  grid-template-columns: 130px 1fr;
  row-gap: 8px;
  column-gap: 18px;
  padding: 18px 26px 18px 26px;
  border-bottom: 1px solid var(--rule-soft);
  font-size: 12.5px;
}
.dcard-meta .k {
  font-family: var(--mono);
  font-size: 10.5px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--paper-faint);
  align-self: center;
}
.dcard-meta .v {
  color: var(--paper);
}
.dcard-meta .v.mono { font-family: var(--mono); font-size: 11.5px; color: var(--paper-muted); }
.dcard-body {
  padding: 24px 26px 24px 26px;
  font-family: var(--serif);
  font-size: 17px;
  line-height: 1.65;
  color: var(--paper);
}
.dcard-foot {
  display: flex; align-items: center; justify-content: space-between;
  gap: 14px;
  padding: 14px 26px 14px 26px;
  border-top: 1px solid var(--rule-soft);
  font-family: var(--mono);
  font-size: 10.5px;
  color: var(--paper-faint);
  letter-spacing: 0.10em;
}

/* Streamlit text_area styling — match the dossier body */
[data-testid="stTextArea"] textarea {
  background: var(--ink-2) !important;
  border: 1px solid var(--rule) !important;
  border-radius: 1px !important;
  color: var(--paper) !important;
  font-family: var(--serif) !important;
  font-size: 16px !important;
  line-height: 1.55 !important;
  padding: 14px !important;
}
[data-testid="stTextArea"] label,
[data-testid="stTextInput"] label,
[data-testid="stSelectbox"] label,
[data-testid="stNumberInput"] label,
[data-testid="stCheckbox"] label,
[data-testid="stMultiSelect"] label {
  font-family: var(--mono) !important;
  font-size: 10.5px !important;
  letter-spacing: 0.18em !important;
  text-transform: uppercase !important;
  color: var(--paper-faint) !important;
  font-weight: 500 !important;
}
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input {
  background: var(--ink-2) !important;
  border: 1px solid var(--rule) !important;
  border-radius: 1px !important;
  color: var(--paper) !important;
  font-family: var(--mono) !important;
  font-size: 13px !important;
}
[data-testid="stSelectbox"] [data-baseweb="select"] > div {
  background: var(--ink-2) !important;
  border: 1px solid var(--rule) !important;
  border-radius: 1px !important;
  color: var(--paper) !important;
  font-family: var(--mono) !important;
  font-size: 13px !important;
}

/* Buttons */
[data-testid="stButton"] > button,
[data-testid="stFormSubmitButton"] > button {
  background: var(--ink-2) !important;
  border: 1px solid var(--rule) !important;
  border-radius: 1px !important;
  color: var(--paper) !important;
  font-family: var(--mono) !important;
  font-size: 10.5px !important;
  letter-spacing: 0.18em !important;
  text-transform: uppercase !important;
  padding: 6px 12px !important;
  min-height: 0 !important;
  line-height: 1 !important;
  height: 30px !important;
  font-weight: 600 !important;
  transition: background-color 120ms ease-out, color 120ms ease-out, border-color 120ms ease-out;
}
[data-testid="stButton"] > button p,
[data-testid="stFormSubmitButton"] > button p,
[data-testid="stButton"] > button [data-testid="stMarkdownContainer"],
[data-testid="stFormSubmitButton"] > button [data-testid="stMarkdownContainer"] {
  margin: 0 !important;
  line-height: 1 !important;
  white-space: nowrap !important;
}
[data-testid="stButton"] > button,
[data-testid="stFormSubmitButton"] > button {
  white-space: nowrap !important;
}
[data-testid="stButton"] > button:hover,
[data-testid="stFormSubmitButton"] > button:hover {
  background: var(--ink-3) !important;
  border-color: var(--paper-faint) !important;
  color: var(--paper) !important;
}
[data-testid="stButton"] > button[kind="primary"],
[data-testid="stFormSubmitButton"] > button[kind="primary"] {
  background: transparent !important;
  border-color: var(--pending) !important;
  color: var(--pending) !important;
}
[data-testid="stButton"] > button[kind="primary"]:hover,
[data-testid="stFormSubmitButton"] > button[kind="primary"]:hover {
  background: var(--pending) !important;
  color: var(--ink-0) !important;
}

/* Tabs */
[data-baseweb="tab-list"] {
  border-bottom: 1px solid var(--rule) !important;
  gap: 8px !important;
  background: transparent !important;
}
[data-baseweb="tab"] {
  background: transparent !important;
  color: var(--paper-faint) !important;
  font-family: var(--mono) !important;
  font-size: 11px !important;
  letter-spacing: 0.20em !important;
  text-transform: uppercase !important;
  padding: 10px 14px !important;
  border: none !important;
}
[data-baseweb="tab"][aria-selected="true"] {
  color: var(--paper) !important;
  border-bottom: 2px solid var(--pending) !important;
}

/* ──── Sidebar ──── */
[data-testid="stSidebar"] {
  background: var(--ink-1) !important;
  border-right: 1px solid var(--rule) !important;
  min-width: 280px !important;
  max-width: 320px !important;
}
[data-testid="stSidebar"] [data-testid="stSidebarContent"],
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
  background: var(--ink-1) !important;
}
[data-testid="stSidebar"] .block-container {
  padding-top: 1.5rem !important;
  padding-left: 1.25rem !important;
  padding-right: 1.25rem !important;
}
[data-testid="stSidebar"] [data-testid="stButton"] > button {
  height: 26px !important;
  padding: 4px 10px !important;
  font-size: 9.5px !important;
  letter-spacing: 0.18em !important;
  font-weight: 600 !important;
}
[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] { gap: 4px !important; }
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarCollapsedControl"] {
  display: none !important;
}
.sb-brand {
  display: flex; align-items: baseline; gap: 8px;
  font-family: var(--mono);
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--paper);
  font-size: 13px;
  font-weight: 700;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--rule);
  margin-bottom: 18px;
}
.sb-brand .v {
  color: var(--paper-faint);
  font-size: 9.5px;
  font-weight: 500;
}
.sb-section {
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--paper-faint);
  padding: 14px 0 8px 0;
  border-top: 1px solid var(--rule);
  margin-top: 14px;
}
.sb-section:first-of-type { border-top: none; margin-top: 0; padding-top: 0; }
.sb-row {
  display: grid;
  grid-template-columns: 24px 1fr auto;
  gap: 10px;
  padding: 7px 4px;
  border-bottom: 1px solid var(--rule-soft);
  align-items: center;
  font-size: 12px;
}
.sb-row .glyph {
  font-family: var(--serif);
  font-style: italic;
  color: var(--paper-faint);
  text-align: right;
  font-size: 12px;
}
.sb-row .name { color: var(--paper); }
.sb-row .lang {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--paper-faint);
  letter-spacing: 0.15em;
}
.sb-stat {
  display: flex; justify-content: space-between;
  font-family: var(--mono);
  font-size: 11px;
  padding: 6px 4px;
  color: var(--paper-muted);
  border-bottom: 1px solid var(--rule-soft);
}
.sb-stat .v { color: var(--paper); }

.sb-camp {
  border: 1px solid var(--rule);
  background: var(--ink-2);
  padding: 8px 10px;
  margin-bottom: 4px;
}
.sb-camp-head {
  display: flex; justify-content: space-between; align-items: baseline;
  margin-bottom: 4px;
}
.sb-camp-id {
  font-size: 10px;
  color: var(--paper-faint);
  letter-spacing: 0.10em;
}
.sb-camp-status {
  font-family: var(--mono);
  font-size: 9.5px;
  letter-spacing: 0.20em;
  color: var(--paper);
}
.sb-camp-intent {
  font-size: 12px;
  color: var(--paper);
  line-height: 1.4;
  font-family: var(--serif);
}

/* ──────────────────────────────────────────────────────────────────
   shadcn-borrowed patterns: refined header, sidebar groups, avatar,
   subtle elevation. Adapted to dossier aesthetic — sharp corners on
   stamps, soft 3-4px on inputs/buttons, hover bg shifts on menu items.
   ────────────────────────────────────────────────────────────────── */

/* Top classification strip — runs above the main header bar */
.classification-strip {
  position: sticky; top: 0; z-index: 60;
  margin: -0.25rem -1.5rem 0 -1.5rem;
  padding: 4px 18px;
  background: var(--paper);
  color: var(--ink-0);
  font-family: var(--mono);
  font-size: 9.5px;
  letter-spacing: 0.32em;
  text-transform: uppercase;
  display: flex; justify-content: space-between; align-items: center;
  gap: 24px;
}
.classification-strip .cs-left {
  display: flex; gap: 14px; align-items: center;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  min-width: 0;
}
.classification-strip .cs-marker {
  display: inline-block; width: 8px; height: 8px;
  background: var(--ink-0); flex: 0 0 auto;
}
.classification-strip .cs-right { color: var(--ink-3); white-space: nowrap; flex: 0 0 auto; }

/* Main header bar (replaces old .banner usage) */
.hdr {
  position: sticky; top: 22px; z-index: 50;
  margin: 0 -1.5rem 22px -1.5rem;
  padding: 14px 22px 13px 22px;
  background: var(--ink-1);
  border-bottom: 1px solid var(--rule);
  box-shadow: 0 1px 0 0 rgba(22,20,15,0.04), 0 1px 3px -1px rgba(22,20,15,0.06);
  display: flex;
  gap: 14px 18px;
  align-items: center;
  flex-wrap: wrap;
}
.hdr-brand {
  display: flex; align-items: baseline; gap: 12px;
  flex: 0 0 auto;
  white-space: nowrap;
}
.hdr-spacer { flex: 1 1 auto; min-width: 8px; }
.hdr-mark {
  font-family: var(--mono);
  font-size: 14px; font-weight: 700;
  letter-spacing: 0.22em;
  color: var(--paper);
  text-transform: uppercase;
}
.hdr-crumb {
  display: flex; align-items: baseline; gap: 8px;
  font-family: var(--mono);
  font-size: 10.5px;
  letter-spacing: 0.18em;
  color: var(--paper-faint);
  text-transform: uppercase;
}
.hdr-crumb .sep { color: var(--paper-faint); opacity: 0.55; }
.hdr-crumb .cur { color: var(--paper-muted); }

.hdr-status-pill {
  display: inline-flex; align-items: center; gap: 10px;
  padding: 7px 14px 6px 12px;
  border: 1px solid var(--rule-strong);
  background: var(--ink-3);
  border-radius: 3px;
  font-family: var(--mono);
  font-size: 10.5px;
  letter-spacing: 0.20em;
  text-transform: uppercase;
  color: var(--paper);
  white-space: nowrap;
}
.hdr-status-pill .label { color: var(--paper-faint); }
.hdr-status-pill .age { color: var(--paper-muted); font-size: 10px; letter-spacing: 0; }
.hdr-status-pill .dot {
  display: inline-block; width: 7px; height: 7px;
  background: currentColor; box-shadow: 0 0 8px currentColor;
}
.hdr-status-pill.s-armed { color: #2F6B3A; border-color: #B8C8AE; background: #F1F5EA; }
.hdr-status-pill.s-stale { color: #8A6A1F; border-color: #D4C497; background: #F6EFD8; }
.hdr-status-pill.s-offline { color: var(--paper-faint); }

.hdr-right {
  display: flex; align-items: center; gap: 14px; justify-content: flex-end;
}
.hdr-kpis { display: inline-flex; gap: 0; }
.hdr-kpi {
  display: inline-flex; align-items: baseline; gap: 7px;
  padding: 6px 11px 5px 11px;
  border: 1px solid var(--rule);
  background: var(--ink-3);
  font-family: var(--mono);
  font-size: 9.5px;
  letter-spacing: 0.22em;
  color: var(--paper-faint);
  text-transform: uppercase;
  margin-left: -1px;
  transition: background 120ms ease;
}
.hdr-kpi:first-child { margin-left: 0; }
.hdr-kpi:hover { background: var(--ink-4); }
.hdr-kpi .n {
  color: var(--paper); font-size: 14px; font-weight: 600;
  letter-spacing: 0; line-height: 1;
}
.hdr-kpi.posted { background: var(--paper); color: var(--ink-3); border-color: var(--paper); }
.hdr-kpi.posted .n { color: var(--ink-0); }

.hdr-op {
  display: flex; align-items: center; gap: 10px;
  padding: 5px 10px 5px 5px;
  border: 1px solid var(--rule);
  background: var(--ink-3);
  border-radius: 3px;
}
.hdr-op:hover { background: var(--ink-4); }
.hdr-op-avatar {
  width: 26px; height: 26px;
  background: var(--paper);
  color: var(--ink-0);
  display: inline-flex; align-items: center; justify-content: center;
  font-family: var(--mono);
  font-size: 10.5px; font-weight: 700;
  letter-spacing: 0.05em;
}
.hdr-op-meta {
  display: flex; flex-direction: column; line-height: 1.1;
}
.hdr-op-name {
  font-family: var(--mono); font-size: 11px; color: var(--paper);
  letter-spacing: 0.12em; font-weight: 600; text-transform: uppercase;
}
.hdr-op-role {
  font-family: var(--mono); font-size: 8.5px; color: var(--paper-faint);
  letter-spacing: 0.20em; text-transform: uppercase;
}

/* ──── Sidebar — shadcn group / menu / footer pattern ──── */
.sb-head {
  display: flex; align-items: center; gap: 10px;
  padding: 4px 4px 16px 4px;
  border-bottom: 1px solid var(--rule);
  margin-bottom: 16px;
}
.sb-head-mark {
  width: 30px; height: 30px;
  background: var(--paper); color: var(--ink-0);
  display: inline-flex; align-items: center; justify-content: center;
  font-family: var(--mono); font-size: 13px; font-weight: 700;
  letter-spacing: 0.04em;
}
.sb-head-meta { display: flex; flex-direction: column; line-height: 1.15; }
.sb-head-name {
  font-family: var(--mono); font-size: 13px; font-weight: 700;
  letter-spacing: 0.20em; color: var(--paper); text-transform: uppercase;
}
.sb-head-sub {
  font-family: var(--mono); font-size: 9px; color: var(--paper-faint);
  letter-spacing: 0.22em; text-transform: uppercase;
}

.sb-group { padding: 14px 0 8px 0; }
.sb-group + .sb-group { border-top: 1px solid var(--rule-soft); }
.sb-group-label {
  display: flex; align-items: center; justify-content: space-between;
  font-family: var(--mono);
  font-size: 9.5px;
  letter-spacing: 0.28em;
  text-transform: uppercase;
  color: var(--paper-faint);
  padding: 0 4px 8px 4px;
}
.sb-group-label .count {
  font-size: 9px;
  color: var(--paper-muted);
  letter-spacing: 0.10em;
}

.sb-menu { display: flex; flex-direction: column; gap: 1px; }
.sb-menu-item {
  display: grid;
  grid-template-columns: 22px 1fr auto;
  gap: 10px; align-items: center;
  padding: 7px 8px;
  border-radius: 3px;
  font-family: var(--sans);
  font-size: 12.5px;
  color: var(--paper);
  text-decoration: none !important;
  cursor: pointer;
  transition: background 100ms ease;
}
.sb-menu-item:hover { background: var(--ink-4); }
.sb-menu-item.active { background: var(--ink-4); }
.sb-menu-item .icon {
  font-family: var(--serif); font-style: italic;
  color: var(--paper-faint); font-size: 12px; text-align: right;
}
.sb-menu-item.active .icon { color: var(--paper); }
.sb-menu-item .meta {
  font-family: var(--mono); font-size: 9.5px;
  color: var(--paper-faint); letter-spacing: 0.16em;
}

/* sidebar persona row — refined with avatar block */
.sb-persona {
  display: grid;
  grid-template-columns: 28px 1fr auto;
  gap: 10px; align-items: center;
  padding: 6px 4px;
  border-radius: 3px;
}
.sb-persona:hover { background: var(--ink-4); }
.sb-persona-av {
  width: 26px; height: 26px;
  background: var(--ink-2);
  border: 1px solid var(--rule);
  color: var(--paper);
  display: inline-flex; align-items: center; justify-content: center;
  font-family: var(--serif); font-style: italic;
  font-size: 12px;
}
.sb-persona-name {
  font-family: var(--sans); font-size: 12.5px;
  color: var(--paper); line-height: 1.15;
}
.sb-persona-handle {
  font-family: var(--mono); font-size: 9.5px;
  color: var(--paper-faint); letter-spacing: 0.10em;
}
.sb-persona-lang {
  font-family: var(--mono); font-size: 9.5px;
  color: var(--paper-muted); letter-spacing: 0.18em;
  padding: 2px 6px; border: 1px solid var(--rule);
}

/* sidebar system stat with status dot */
.sb-stat-row {
  display: flex; justify-content: space-between; align-items: center;
  padding: 5px 4px;
  font-family: var(--mono); font-size: 11px;
  color: var(--paper-muted);
}
.sb-stat-row .label { display: inline-flex; align-items: center; gap: 8px; letter-spacing: 0.05em; }
.sb-stat-row .v { color: var(--paper); letter-spacing: 0.04em; }
.sb-stat-row .dot {
  display: inline-block; width: 6px; height: 6px;
  background: currentColor;
}
.sb-stat-row.s-armed   .dot { background: #4F8C5C; }
.sb-stat-row.s-stale   .dot { background: #B79844; }
.sb-stat-row.s-offline .dot { background: var(--paper-faint); }

/* sidebar footer — operator block pinned to bottom */
.sb-footer {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--rule);
  display: flex; align-items: center; gap: 10px;
}
.sb-footer-av {
  width: 32px; height: 32px;
  background: var(--paper); color: var(--ink-0);
  display: inline-flex; align-items: center; justify-content: center;
  font-family: var(--mono); font-size: 12px; font-weight: 700;
  letter-spacing: 0.05em;
}
.sb-footer-meta { display: flex; flex-direction: column; line-height: 1.15; }
.sb-footer-name {
  font-family: var(--mono); font-size: 11.5px; font-weight: 600;
  letter-spacing: 0.18em; color: var(--paper); text-transform: uppercase;
}
.sb-footer-role {
  font-family: var(--mono); font-size: 9px; color: var(--paper-faint);
  letter-spacing: 0.22em; text-transform: uppercase;
}

/* Empty-state SITREP block */
.standby {
  border: 1px dashed var(--rule);
  padding: 24px 28px;
  text-align: center;
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.30em;
  color: var(--paper-faint);
  text-transform: uppercase;
}

/* Audit log feed */
.audit {
  font-family: var(--mono);
  font-size: 12px;
  line-height: 1.7;
}
.audit .row {
  display: grid;
  grid-template-columns: 90px 180px 1fr;
  gap: 14px;
  padding: 6px 12px;
  border-bottom: 1px solid var(--rule-soft);
  color: var(--paper-muted);
}
.audit .row:hover { background: var(--ink-2); color: var(--paper); }
.audit .ts { color: var(--paper-faint); }
.audit .ev {
  color: var(--paper);
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  font-size: 10.5px;
}
.audit .body { color: var(--paper-muted); }
.audit .body.fail { color: var(--failed); }
.audit .body.post { color: var(--posted); }

/* Channel mirror — each posted message is its own card-like record */
.tg-row {
  display: grid;
  grid-template-columns: 150px 1fr;
  background: var(--ink-3);
  border: 1px solid var(--rule-strong);
  margin-bottom: 10px;
  padding: 0;
  gap: 0;
}
.tg-meta {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--paper-faint);
  letter-spacing: 0.14em;
  padding: 14px 16px;
  background: var(--ink-2);
  border-right: 1px solid var(--rule-strong);
  display: flex; flex-direction: column; gap: 6px;
  text-transform: uppercase;
}
.tg-meta > span { display: block; }
.tg-meta .tg-msgid { color: var(--paper); font-size: 11px; }
.tg-meta .tg-time { color: var(--paper-muted); }
.tg-meta .tg-persona { color: var(--paper-muted); margin-top: 4px; padding-top: 6px; border-top: 1px solid var(--rule); }
.tg-body {
  font-family: var(--serif);
  font-size: 15.5px;
  color: var(--paper);
  line-height: 1.6;
  padding: 18px 22px;
}

/* Campaign roster row */
.roster-row {
  display: grid;
  grid-template-columns: 26px 1fr 130px 60px;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid var(--rule-soft);
  align-items: center;
}
.roster-row .glyph {
  font-family: var(--serif);
  font-style: italic;
  color: var(--paper-faint);
  font-size: 13px;
  text-align: right;
}
.roster-row .pname { color: var(--paper); font-size: 13px; }
.roster-row .pid { color: var(--paper-faint); font-family: var(--mono); font-size: 11px; }

/* ──── dashboard column shells ──── */
[data-testid="stMain"] [data-testid="stVerticalBlock"] {
  gap: 1.25rem !important;
}
[data-testid="stMain"] [data-testid="stHorizontalBlock"]
  [data-testid="stVerticalBlock"] { gap: 0.6rem !important; }

/* Each st.container(border=True) becomes a section panel — depth 1 from page bg. */
[data-testid="stMain"] [data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--ink-2) !important;
  border: 1px solid var(--rule) !important;
  border-radius: 0 !important;
  padding: 0 !important;
  margin-bottom: 28px !important;
  position: relative;
}
[data-testid="stMain"] [data-testid="stVerticalBlockBorderWrapper"]::before {
  content: '';
  position: absolute;
  top: -1px; left: -1px;
  width: 14px; height: 14px;
  border-top: 1px solid var(--paper-faint);
  border-left: 1px solid var(--paper-faint);
  pointer-events: none;
}
[data-testid="stMain"] [data-testid="stVerticalBlockBorderWrapper"]::after {
  content: '';
  position: absolute;
  bottom: -1px; right: -1px;
  width: 14px; height: 14px;
  border-bottom: 1px solid var(--paper-faint);
  border-right: 1px solid var(--paper-faint);
  pointer-events: none;
}
/* Inner block needs internal padding (the wrapper sets padding:0 to allow
   the section-head bg to extend edge-to-edge). */
[data-testid="stMain"] [data-testid="stVerticalBlockBorderWrapper"]
  > [data-testid="stVerticalBlock"] {
  padding: 0 !important;
  gap: 0 !important;
}
/* The section-head sits flush at top; following content gets generous padding */
[data-testid="stMain"] [data-testid="stVerticalBlockBorderWrapper"]
  > [data-testid="stVerticalBlock"]
  > [data-testid="stElementContainer"]:not(:has(.section-head)) {
  padding: 0 24px !important;
}
[data-testid="stMain"] [data-testid="stVerticalBlockBorderWrapper"]
  > [data-testid="stVerticalBlock"]
  > [data-testid="stElementContainer"]:nth-child(2) {
  padding-top: 22px !important;
}
[data-testid="stMain"] [data-testid="stVerticalBlockBorderWrapper"]
  > [data-testid="stVerticalBlock"]
  > [data-testid="stElementContainer"]:last-child {
  padding-bottom: 24px !important;
}
.panel {
  border: 1px solid var(--rule);
  background: var(--ink-1);
  margin-bottom: 14px;
}
.panel > .section-head {
  border-top: none;
  margin: 0;
  border-bottom: 1px solid var(--rule);
}
.panel-body { padding: 14px 14px 12px 14px; }
.rail .dcard { margin-bottom: 0; }
.rail .dcard-body { font-size: 14px; padding: 12px 14px 12px 14px; }
.rail .dcard-meta { padding: 10px 14px 10px 14px; grid-template-columns: 90px 1fr; row-gap: 3px; }
.rail .dcard-foot { padding: 8px 14px; }

/* Compact column gutters in Streamlit's column blocks */
[data-testid="stHorizontalBlock"] { gap: 8px !important; }

/* Buttons that immediately follow a dcard should attach to it visually */
.rail [data-testid="stHorizontalBlock"] {
  margin-top: -1px !important;
  margin-bottom: 14px;
}
.rail [data-testid="stHorizontalBlock"] [data-testid="stButton"] > button {
  border-radius: 0 !important;
  width: 100% !important;
}

/* In-card actions row */
.dcard-actions {
  display: flex; gap: 8px;
  padding: 10px 14px 14px 14px;
  border-top: 1px solid var(--rule-soft);
}

/* Streamlit elements that follow a dcard should hug it (no big gap) */
.tight + [data-testid="stHorizontalBlock"],
.tight + [data-testid="stButton"] { margin-top: -8px; }

/* Section row separators */
[data-testid="stExpander"] {
  border: 1px solid var(--rule) !important;
  border-radius: 1px !important;
  background: var(--ink-1) !important;
}
[data-testid="stExpander"] summary,
[data-testid="stExpander"] details > summary {
  font-family: var(--mono) !important;
  font-size: 10.5px !important;
  letter-spacing: 0.20em !important;
  text-transform: uppercase !important;
  color: var(--paper) !important;
  padding: 12px 14px !important;
}

/* Reduce motion */
@media (prefers-reduced-motion: reduce) {
  * { transition: none !important; animation: none !important; }
}
</style>
"""
    # Strip CSS comments — Streamlit's markdown processor treats indented CSS
    # like a code block and silently truncates the rest of the rule set.
    # st.html bypasses markdown entirely; we still strip comments as belt-and-
    # suspenders against any future renderer that might trip on them.
    import re
    cleaned = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    st.html(cleaned)


# ────────────────────────────────────────────────────────────────────────
# Banner
# ────────────────────────────────────────────────────────────────────────


def _live_counts() -> dict[str, int]:
    """Pull KPI counts from sqlite for the banner strip."""
    orch = _get_orchestrator()
    pending = len(_run(orch.storage.list_pending()))
    active = _run(orch.storage.list_active_campaigns())
    posted = 0
    failed = 0
    for c in active:
        posted += len(
            _run(orch.storage.list_posts_for_campaign(c.id, statuses=("posted",)))
        )
        failed += len(
            _run(orch.storage.list_posts_for_campaign(c.id, statuses=("failed",)))
        )
    running = sum(1 for c in active if c.status == "running")
    return {"pending": pending, "posted": posted, "failed": failed, "active": running}


def render_banner() -> None:
    sys_status, age = _heartbeat_state()
    sys_class = {"ARMED": "s-armed", "STALE": "s-stale", "OFFLINE": "s-offline"}[sys_status]
    age_str = "—" if age is None else f"{age:0.1f}s"
    channel_short = "—"
    allowed = _allowed_channels()
    if allowed:
        channel_short = _short_channel(allowed[0])
    now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    operator = _operator_id().upper()
    op_initials = (operator[:2] if operator else "—").upper()
    k = _live_counts()

    html = f"""
<div class="classification-strip">
  <div class="cs-left">
    <span class="cs-marker"></span>
    <span>CLASSIFIED · OPERATOR EYES ONLY</span>
    <span>·</span>
    <span>CH {channel_short}</span>
  </div>
  <div class="cs-right">{now}</div>
</div>
<div class="hdr">
  <div class="hdr-brand">
    <span class="hdr-mark">// MENDACITY</span>
  </div>
  <div class="hdr-spacer"></div>
  <div class="hdr-status-pill {sys_class}">
    <span class="dot"></span>
    <span class="label">SYS</span>
    <span>{sys_status}</span>
    <span class="age">· {age_str}</span>
  </div>
  <div class="hdr-kpis">
    <span class="hdr-kpi pending"><span class="n">{k["pending"]}</span> Pending</span>
    <span class="hdr-kpi posted"><span class="n">{k["posted"]}</span> Posted</span>
    <span class="hdr-kpi failed"><span class="n">{k["failed"]}</span> Failed</span>
    <span class="hdr-kpi active"><span class="n">{k["active"]}</span> Active</span>
  </div>
  <div class="hdr-op">
    <span class="hdr-op-avatar">{op_initials}</span>
    <span class="hdr-op-meta">
      <span class="hdr-op-name">{operator}</span>
      <span class="hdr-op-role">OPERATOR</span>
    </span>
  </div>
</div>
"""
    st.html(html)


# ────────────────────────────────────────────────────────────────────────
# Section: Operational Directive (campaign creator + active list)
# ────────────────────────────────────────────────────────────────────────


_SECTION_ANCHOR = {"I": "section-directive", "II": "section-queue", "III": "section-audit"}


def _section_head(numeral: str, title: str, sub: str = "") -> None:
    sub_html = f'<span class="sub">{sub}</span>' if sub else ""
    anchor = _SECTION_ANCHOR.get(numeral, "")
    anchor_attr = f' id="{anchor}"' if anchor else ""
    st.markdown(
        f'<div class="section-head"{anchor_attr}><span class="sn">§ {numeral}</span>'
        f'<span class="stitle">{title}</span>{sub_html}</div>',
        unsafe_allow_html=True,
    )


def section_active_campaigns_compact() -> None:
    """Sidebar-only compact view: one row per active campaign with action menu."""
    orch = _get_orchestrator()
    active = _run(orch.storage.list_active_campaigns())
    running = [c for c in active if c.status in ("running", "paused")]

    st.html('<div class="sb-section">ACTIVE CAMPAIGNS</div>')
    if not running:
        st.html(
            '<div class="sb-stat" style="border-bottom:none;color:var(--paper-faint);">'
            '<span>NONE</span></div>'
        )
        return

    for c in running:
        intent_short = c.intent if len(c.intent) <= 60 else c.intent[:57] + "…"
        st.html(
            f'<div class="sb-camp">'
            f'<div class="sb-camp-head">'
            f'<span class="sb-camp-id mono">{c.id[-6:]}</span>'
            f'<span class="sb-camp-status">{c.status.upper()}</span>'
            f'</div>'
            f'<div class="sb-camp-intent">{intent_short}</div>'
            f'</div>'
        )
        cols = st.columns(2)
        with cols[0]:
            label = "RESUME" if c.status == "paused" else "PAUSE"
            if st.button(label, key=f"pp_{c.id}", use_container_width=True):
                if c.status == "paused":
                    _run(orch.resume(c.id))
                else:
                    _run(orch.pause(c.id))
                st.rerun()
        with cols[1]:
            if st.button("ABORT", key=f"ab_{c.id}", use_container_width=True):
                _run(orch.abort(c.id))
                st.rerun()


def section_new_directive() -> None:
    """Right-rail collapsible: new directive form."""
    orch = _get_orchestrator()
    personas = _get_personas()
    allowed = _allowed_channels()
    running_count = sum(
        1 for c in _run(orch.storage.list_active_campaigns()) if c.status == "running"
    )

    _section_head("I", "ISSUE DIRECTIVE", "")
    with st.expander("OPEN FORM", expanded=(running_count == 0)):
        with st.form("new_campaign", clear_on_submit=False):
            intent = st.text_area(
                "INTENT (operator's words)",
                placeholder="e.g. unusual movement on M-04 around dawn",
                height=80,
            )

            if allowed:
                channel = st.selectbox("CHANNEL", allowed, format_func=_short_channel)
            else:
                channel = st.text_input("CHANNEL", value="")

            st.html(
                '<div style="font-family:var(--mono);font-size:10.5px;'
                'letter-spacing:0.18em;color:var(--paper-faint);'
                'text-transform:uppercase;margin:14px 0 6px 0;">'
                'ROSTER &mdash; exactly one SEED'
                '</div>'
            )
            roster: dict[str, str] = {}
            persona_list = list(personas.items())
            for i, (pid, p) in enumerate(persona_list):
                cols = st.columns([0.3, 2, 1.4, 0.6])
                with cols[0]:
                    included = st.checkbox(
                        " ", value=True, key=f"inc_{pid}", label_visibility="collapsed"
                    )
                with cols[1]:
                    st.html(
                        f'<div style="padding-top:6px;font-size:13px;color:var(--paper);">'
                        f'{p.name} <span class="mono" style="color:var(--paper-faint);font-size:11px;">'
                        f'{pid}</span></div>'
                    )
                with cols[2]:
                    role = st.selectbox(
                        "role", ROLE_OPTIONS,
                        index=0 if i == 0 else min(i, 3),
                        key=f"role_{pid}",
                        label_visibility="collapsed",
                    )
                with cols[3]:
                    st.html(
                        f'<div style="padding-top:8px;font-family:var(--mono);'
                        f'font-size:10.5px;color:var(--paper-faint);text-align:right;">'
                        f'{p.language.upper()}</div>'
                    )
                if included:
                    roster[pid] = role

            cdelay1, cdelay2 = st.columns(2)
            with cdelay1:
                delay_min = st.number_input("DELAY MIN (s)", min_value=0, value=300, step=30)
            with cdelay2:
                delay_max = st.number_input("DELAY MAX (s)", min_value=0, value=1800, step=60)

            submitted = st.form_submit_button("ISSUE DIRECTIVE", type="primary",
                                              use_container_width=True)
            if submitted:
                try:
                    c = Campaign.new(
                        intent=intent.strip(),
                        channel=channel,
                        delay_range_seconds=(int(delay_min), int(delay_max)),
                        created_by=_operator_id(),
                        roster=roster,
                    )
                    _run(orch.submit_campaign(c))
                    st.session_state["_last_directive"] = c.id
                    st.rerun()
                except CampaignValidationError as exc:
                    st.error(str(exc))
                except Exception as exc:
                    st.error(f"directive rejected: {exc}")


# ────────────────────────────────────────────────────────────────────────
# Section: Approval Queue
# ────────────────────────────────────────────────────────────────────────


def _stamp_html(status: str) -> str:
    cls = {
        "pending_approval": "pending",
        "approved": "approved",
        "posted": "posted",
        "failed": "failed",
        "rejected": "rejected",
    }.get(status, "pending")
    return (
        f'<span class="stamp {cls}"><span class="dot"></span>'
        f'{STATUS_LABEL.get(status, status.upper())}</span>'
    )


def section_approval_queue() -> None:
    orch = _get_orchestrator()
    personas = _get_personas()
    pending = _run(orch.storage.list_pending())
    sub = f"{len(pending)} AWAITING DECISION" if pending else "STANDBY"
    _section_head("II", "APPROVAL QUEUE", sub)

    if not pending:
        st.markdown(
            '<div class="standby">// NO POSTS PENDING APPROVAL · QUEUE STANDBY //</div>',
            unsafe_allow_html=True,
        )
        return

    armed_id = st.session_state.get("_armed_post_id")
    armed_at = st.session_state.get("_armed_at", 0)
    if armed_id and time.time() - armed_at > 4:
        st.session_state["_armed_post_id"] = None  # auto-disarm

    for post in pending:
        persona = personas.get(post.persona_id)
        name = persona.name if persona else post.persona_id
        lang = persona.language.upper() if persona else "?"
        glyph = ROLE_GLYPH.get(post.role, "·")
        is_armed = (st.session_state.get("_armed_post_id") == post.id)

        with st.container(border=True):
            st.html(
                f"""
<div class="post-head">
  <div class="post-head-left">
    {_stamp_html("pending_approval")}
    <span class="post-role-chip">ROLE {glyph} · {post.role.upper()}</span>
  </div>
  <div class="post-head-right mono">
    {post.id}
  </div>
</div>
<div class="post-meta">
  <div><span class="k">PERSONA</span><span class="v">{name} <span class="mono" style="color:var(--paper-faint);">({post.persona_id})</span></span></div>
  <div><span class="k">LANG</span><span class="v mono">{lang}</span></div>
  <div><span class="k">GENERATED</span><span class="v mono">{_format_ts_full(post.generated_at)}</span></div>
  <div><span class="k">CAMPAIGN</span><span class="v mono">{post.campaign_id[-8:]}</span></div>
</div>
<div class="post-content-label">// POST CONTENT — EDITABLE</div>
"""
            )

            edited = st.text_area(
                "post content",
                value=post.generated_content,
                key=f"edit_{post.id}",
                height=120,
                label_visibility="collapsed",
            )
            char_count = len(edited)
            edited_flag = (edited.strip() != post.generated_content.strip())

            st.html(
                f"""
<div class="post-foot mono">
  <span>{char_count} CHARS</span>
  <span>SHA256 <span style="color:var(--paper);">{__import__("hashlib").sha256(edited.encode("utf-8")).hexdigest()[:16]}…</span></span>
</div>
"""
            )

            action_cols = st.columns([1.2, 1.7, 1, 1, 3.5])
        with action_cols[0]:
            if not is_armed:
                if st.button("APPROVE", key=f"ap_{post.id}", type="primary"):
                    st.session_state["_armed_post_id"] = post.id
                    st.session_state["_armed_at"] = time.time()
                    st.session_state["_armed_with_edit"] = False
                    st.rerun()
            else:
                with_edit = st.session_state.get("_armed_with_edit", False)
                label = "CONFIRM EDIT & POST" if with_edit else "CONFIRM POST"
                if st.button(label, key=f"cf_{post.id}", type="primary"):
                    arg = edited if with_edit else None
                    _run(orch.approve(post.id, edited_content=arg))
                    st.session_state["_armed_post_id"] = None
                    st.rerun()
        with action_cols[1]:
            if not is_armed:
                if st.button(
                    "EDIT · APPROVE",
                    key=f"ea_{post.id}",
                    disabled=not edited_flag,
                ):
                    st.session_state["_armed_post_id"] = post.id
                    st.session_state["_armed_at"] = time.time()
                    st.session_state["_armed_with_edit"] = True
                    st.rerun()
            else:
                if st.button("CANCEL", key=f"cn_{post.id}"):
                    st.session_state["_armed_post_id"] = None
                    st.rerun()
        with action_cols[2]:
            if st.button("REJECT", key=f"rj_{post.id}", disabled=is_armed):
                _run(orch.reject(post.id))
                st.rerun()
        with action_cols[3]:
            if st.button("REGEN", key=f"rg_{post.id}", disabled=is_armed):
                _run(orch.reject(post.id, regenerate=True))
                st.rerun()


# ────────────────────────────────────────────────────────────────────────
# Section: Audit Trace
# ────────────────────────────────────────────────────────────────────────


_EVENT_TONE = {
    "post_failed": "fail",
    "generation_failed": "fail",
    "post_sent": "post",
    "campaign_aborted": "fail",
}


def section_audit_trace() -> None:
    orch = _get_orchestrator()
    personas = _get_personas()
    _section_head("III", "AUDIT TRACE", "APPEND-ONLY")

    tabs = st.tabs(["CHANNEL", "EVENTS", "CAMPAIGNS"])

    with tabs[0]:
        active = _run(orch.storage.list_active_campaigns())
        any_posts = False
        for c in active:
            posted = _run(
                orch.storage.list_posts_for_campaign(c.id, statuses=("posted",))
            )
            for p in posted:
                any_posts = True
                persona = personas.get(p.persona_id)
                name = persona.name if persona else p.persona_id
                st.html(
                    f"""
<div class="tg-row">
  <div class="tg-meta">
    {_stamp_html("posted")}
    <span class="tg-msgid">MSG #{p.telegram_message_id}</span>
    <span class="tg-time">{_format_ts_short(p.posted_at)}</span>
    <span class="tg-persona">{name} · {p.role.upper()}</span>
  </div>
  <div class="tg-body">{p.final_content}</div>
</div>
"""
                )
        if not any_posts:
            st.markdown(
                '<div class="standby">// NO POSTS HAVE REACHED THE CHANNEL YET //</div>',
                unsafe_allow_html=True,
            )

    with tabs[1]:
        log = orch.storage.tail_log(120)
        if not log:
            st.markdown(
                '<div class="standby">// AUDIT TRACE OPENS WITH FIRST EVENT //</div>',
                unsafe_allow_html=True,
            )
        else:
            rows_html = ['<div class="audit">']
            for entry in reversed(log):
                ts = _format_ts_short(entry.get("ts", ""))
                ev = entry.get("event", "?").replace("_", " ")
                cid = entry.get("campaign_id") or ""
                pid = entry.get("persona_id") or ""
                role = entry.get("role") or ""
                content = entry.get("content")
                tone_class = _EVENT_TONE.get(entry.get("event"), "")
                meta_pieces = []
                if cid:
                    meta_pieces.append(f"CAMP {cid[-6:]}")
                if pid:
                    meta_pieces.append(pid)
                if role:
                    meta_pieces.append(role.upper())
                meta = " · ".join(meta_pieces) or "—"
                snippet = ""
                if content:
                    text = content if len(content) <= 120 else content[:117] + "…"
                    snippet = text.replace("<", "&lt;").replace(">", "&gt;")
                rows_html.append(
                    f'<div class="row">'
                    f'<span class="ts">{ts}</span>'
                    f'<span class="ev">{ev}</span>'
                    f'<span class="body {tone_class}">{meta}'
                    f'{" — " + snippet if snippet else ""}'
                    f'</span></div>'
                )
            rows_html.append("</div>")
            st.markdown("".join(rows_html), unsafe_allow_html=True)

    with tabs[2]:
        all_camps = _run(orch.storage.list_campaigns())
        if not all_camps:
            st.markdown(
                '<div class="standby">// NO CAMPAIGNS ON RECORD //</div>',
                unsafe_allow_html=True,
            )
        else:
            for c in all_camps[:20]:
                roster_count = len(c.roster)
                st.markdown(
                    f"""
<div class="dcard" style="margin-bottom:8px;">
  <div class="dcard-head">
    <div>{_stamp_html(
        "approved" if c.status == "running"
        else ("rejected" if c.status == "aborted" else "posted")
    )}</div>
    <div class="mono" style="color:var(--paper-faint);font-size:11px;">
      {c.id} · {c.status.upper()} · {_format_ts_full(c.created_at)}
    </div>
  </div>
  <div class="dcard-meta">
    <div class="k">INTENT</div>   <div class="v">{c.intent}</div>
    <div class="k">CHANNEL</div>  <div class="v mono">{_short_channel(c.channel)}</div>
    <div class="k">ROSTER</div>   <div class="v">{roster_count} PERSONAS</div>
  </div>
</div>
""",
                    unsafe_allow_html=True,
                )


# ────────────────────────────────────────────────────────────────────────
# Shell
# ────────────────────────────────────────────────────────────────────────


def render_sidebar() -> None:
    orch = _get_orchestrator()
    personas = _get_personas()
    sys_status, age = _heartbeat_state()
    counts = _live_counts()

    with st.sidebar:
        # Header — monogram mark + wordmark + version
        st.html(
            '<div class="sb-head">'
            '<span class="sb-head-mark">M</span>'
            '<span class="sb-head-meta">'
            '<span class="sb-head-name">MENDACITY</span>'
            '<span class="sb-head-sub">v0.1 · ISSUE #3</span>'
            '</span>'
            '</div>'
        )

        # Group: Active Campaigns — primary operator-actionable content
        section_active_campaigns_compact()

        # Group: Personas roster — context for who's on the bench
        st.html(
            '<div class="sb-group">'
            f'<div class="sb-group-label"><span>Personas</span><span class="count">{len(personas)}</span></div>'
            '</div>'
        )
        default_roles = ["seed", "witness", "reaction", "aggregator"]
        rows = []
        for i, (pid, p) in enumerate(personas.items()):
            role = default_roles[min(i, len(default_roles) - 1)]
            glyph = ROLE_GLYPH.get(role, "·")
            rows.append(
                f'<div class="sb-persona">'
                f'<span class="sb-persona-av">{glyph}</span>'
                f'<span class="sb-persona-name">{p.name}</span>'
                f'<span class="sb-persona-lang">{p.language.upper()}</span>'
                f'</div>'
            )
        st.html("".join(rows))

        # Footer — operator avatar block
        op = _operator_id().upper()
        op_initials = (op[:2] if op else "—").upper()
        st.html(
            f'<div class="sb-footer">'
            f'<span class="sb-footer-av">{op_initials}</span>'
            f'<span class="sb-footer-meta">'
            f'<span class="sb-footer-name">{op}</span>'
            f'<span class="sb-footer-role">OPERATOR · SIGNED IN</span>'
            f'</span>'
            f'</div>'
        )


def main() -> None:
    st.set_page_config(
        page_title="Mendacity / Operator Console",
        page_icon=None,
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _inject_style()
    render_sidebar()
    render_banner()

    # Single-column main with each section inside its own panel.
    with st.container(border=True):
        section_new_directive()
    with st.container(border=True):
        section_approval_queue()
    with st.container(border=True):
        section_audit_trace()


main()
