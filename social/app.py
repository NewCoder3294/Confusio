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
import time
from datetime import datetime, timezone
from pathlib import Path

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
  --ink-0: #0E0D0B;          /* deepest near-black, warm */
  --ink-1: #15130F;          /* main surface */
  --ink-2: #1C1916;          /* card surface */
  --ink-3: #28231D;          /* hover / active */
  --rule:  #3A3127;          /* warm-dark border */
  --rule-soft: #2A2419;      /* softer divider */
  --paper: #E8E2D6;          /* primary text — warm off-white */
  --paper-muted: #9C928A;    /* secondary text */
  --paper-faint: #6B6259;    /* tertiary / metadata */

  --pending:  #C28D2A;
  --approved: #3F7D78;
  --posted:   #9B2A2A;
  --failed:   #D14E4E;
  --rejected: #7A6B7E;

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
[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stToolbar"] { display: none !important; }
.block-container {
  padding-top: 0.5rem !important;
  padding-bottom: 4rem !important;
  max-width: 1280px !important;
}
footer { visibility: hidden; }

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
  border-top: 1px solid var(--rule);
  border-bottom: 1px solid var(--rule);
  padding: 10px 14px 8px 14px;
  margin-bottom: 24px;
  background: var(--ink-1);
  font-family: var(--mono);
  font-size: 11.5px;
  letter-spacing: 0.10em;
  color: var(--paper-muted);
  display: flex;
  flex-wrap: wrap;
  gap: 14px 22px;
  align-items: center;
}
.banner .b-title {
  color: var(--paper);
  font-weight: 600;
  letter-spacing: 0.18em;
}
.banner .b-sep {
  color: var(--paper-faint);
  user-select: none;
}
.banner .b-key { color: var(--paper-faint); }
.banner .b-val { color: var(--paper); font-weight: 500; }

.system-armed     { color: var(--approved) !important; }
.system-stale     { color: var(--pending) !important; }
.system-offline   { color: var(--failed) !important; }
.system-dot {
  display: inline-block; width: 6px; height: 6px; border-radius: 50%;
  background: currentColor; margin-right: 6px; vertical-align: middle;
  box-shadow: 0 0 6px currentColor;
}

/* ──── section headers (dossier markers) ──── */
.section-head {
  display: flex; align-items: baseline; gap: 14px;
  border-top: 1px solid var(--rule);
  padding-top: 18px;
  margin: 32px 0 18px 0;
  font-family: var(--mono);
  font-size: 11.5px;
  letter-spacing: 0.20em;
  color: var(--paper-muted);
  text-transform: uppercase;
}
.section-head .sn {
  color: var(--paper-faint);
  font-family: var(--serif);
  font-style: italic;
  font-size: 13px;
  letter-spacing: 0.05em;
  font-weight: 600;
}
.section-head .stitle {
  color: var(--paper);
  font-weight: 600;
}
.section-head .sub {
  margin-left: auto;
  color: var(--paper-faint);
  font-size: 11px;
  letter-spacing: 0.18em;
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
.stamp.pending  { color: var(--pending); }
.stamp.approved { color: var(--approved); }
.stamp.posted   { color: var(--posted); }
.stamp.failed   { color: var(--failed); }
.stamp.rejected { color: var(--rejected); }
.stamp .dot {
  width: 6px; height: 6px; background: currentColor; border-radius: 1px;
}

/* ──── dossier card (pending post / posted record) ──── */
.dcard {
  background: var(--ink-1);
  border: 1px solid var(--rule);
  border-left-width: 1px;       /* explicit — never side-stripe */
  margin-bottom: 18px;
  padding: 0;
}
.dcard-head {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px;
  padding: 14px 20px 10px 20px;
  border-bottom: 1px solid var(--rule-soft);
}
.dcard-meta {
  display: grid;
  grid-template-columns: 110px 1fr;
  row-gap: 4px;
  column-gap: 16px;
  padding: 12px 20px 12px 20px;
  border-bottom: 1px solid var(--rule-soft);
  font-size: 12px;
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
  padding: 18px 22px 18px 22px;
  font-family: var(--serif);
  font-size: 16px;
  line-height: 1.6;
  color: var(--paper);
}
.dcard-foot {
  display: flex; align-items: center; justify-content: space-between;
  gap: 14px;
  padding: 10px 20px 10px 20px;
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
  font-size: 11px !important;
  letter-spacing: 0.20em !important;
  text-transform: uppercase !important;
  padding: 9px 16px !important;
  font-weight: 600 !important;
  transition: background-color 120ms ease-out, color 120ms ease-out, border-color 120ms ease-out;
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

/* Channel mirror message bubble — looks like a stamped record */
.tg-row {
  display: grid;
  grid-template-columns: 130px 1fr;
  border-bottom: 1px solid var(--rule-soft);
  padding: 14px 6px;
  gap: 18px;
}
.tg-meta {
  font-family: var(--mono);
  font-size: 10.5px;
  color: var(--paper-faint);
  letter-spacing: 0.10em;
}
.tg-body {
  font-family: var(--serif);
  font-size: 14.5px;
  color: var(--paper);
  line-height: 1.55;
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

/* Reduce motion */
@media (prefers-reduced-motion: reduce) {
  * { transition: none !important; animation: none !important; }
}
</style>
"""
    st.markdown(css, unsafe_allow_html=True)


# ────────────────────────────────────────────────────────────────────────
# Banner
# ────────────────────────────────────────────────────────────────────────


def render_banner() -> None:
    sys_status, age = _heartbeat_state()
    sys_class = {
        "ARMED": "system-armed",
        "STALE": "system-stale",
        "OFFLINE": "system-offline",
    }[sys_status]
    age_str = "—" if age is None else f"{age:0.1f}s"
    channel_short = "—"
    allowed = _allowed_channels()
    if allowed:
        channel_short = _short_channel(allowed[0])
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    operator = _operator_id().upper()

    html = f"""
<div class="banner">
  <span class="b-title">// MENDACITY OPERATOR CONSOLE</span>
  <span class="b-sep">//</span>
  <span><span class="b-key">OPERATOR</span> <span class="b-val">{operator}</span></span>
  <span class="b-sep">//</span>
  <span><span class="b-key">CHANNEL</span> <span class="b-val mono">{channel_short}</span></span>
  <span class="b-sep">//</span>
  <span><span class="b-key">SYSTEM</span> <span class="b-val {sys_class}"><span class="system-dot"></span>{sys_status}</span> <span class="b-key">({age_str})</span></span>
  <span class="b-sep">//</span>
  <span class="b-key mono">{now}</span>
  <span class="b-sep">//</span>
</div>
"""
    st.markdown(html, unsafe_allow_html=True)


# ────────────────────────────────────────────────────────────────────────
# Section: Operational Directive (campaign creator + active list)
# ────────────────────────────────────────────────────────────────────────


def _section_head(numeral: str, title: str, sub: str = "") -> None:
    sub_html = f'<span class="sub">{sub}</span>' if sub else ""
    st.markdown(
        f'<div class="section-head"><span class="sn">§ {numeral}</span>'
        f'<span class="stitle">{title}</span>{sub_html}</div>',
        unsafe_allow_html=True,
    )


def section_operational_directive() -> None:
    orch = _get_orchestrator()
    personas = _get_personas()
    allowed = _allowed_channels()
    active = _run(orch.storage.list_active_campaigns())
    running = [c for c in active if c.status == "running"]

    sub = "ISSUE NEW DIRECTIVE" if not running else f"{len(running)} ACTIVE"
    _section_head("I", "OPERATIONAL DIRECTIVE", sub)

    if running:
        for c in running:
            roster_summary = ", ".join(
                f"{personas[pid].name if pid in personas else pid} ({role})"
                for pid, role in c.roster.items()
            )
            st.markdown(
                f"""
<div class="dcard">
  <div class="dcard-head">
    <div>
      <span class="stamp pending"><span class="dot"></span>{STATUS_LABEL.get(c.status, c.status.upper())}</span>
    </div>
    <div class="mono" style="color:var(--paper-faint);font-size:11px;letter-spacing:0.10em;">
      {c.id} · ISSUED {_format_ts_full(c.created_at)}
    </div>
  </div>
  <div class="dcard-meta">
    <div class="k">INTENT</div>     <div class="v">{c.intent}</div>
    <div class="k">CHANNEL</div>    <div class="v mono">{_short_channel(c.channel)}</div>
    <div class="k">ROSTER</div>     <div class="v">{roster_summary}</div>
    <div class="k">DELAY WIN.</div> <div class="v mono">{c.delay_range_seconds[0]}–{c.delay_range_seconds[1]} s</div>
  </div>
</div>
""",
                unsafe_allow_html=True,
            )
            cols = st.columns([1, 1, 1, 6])
            with cols[0]:
                if st.button("PAUSE", key=f"pause_{c.id}"):
                    _run(orch.pause(c.id))
                    st.rerun()
            with cols[1]:
                if st.button("ABORT", key=f"abort_{c.id}"):
                    _run(orch.abort(c.id))
                    st.rerun()

    with st.expander("ISSUE NEW DIRECTIVE" if running else "OPEN DIRECTIVE FORM",
                     expanded=not running):
        with st.form("new_campaign", clear_on_submit=False):
            intent = st.text_area(
                "INTENT — what must be conveyed (operator's words)",
                placeholder="e.g. unusual movement on the M-04 highway around dawn",
                height=90,
            )

            if allowed:
                channel = st.selectbox("CHANNEL", allowed, format_func=_short_channel)
            else:
                channel = st.text_input("CHANNEL", value="")

            st.markdown(
                '<div style="font-family:var(--mono);font-size:10.5px;'
                'letter-spacing:0.18em;color:var(--paper-faint);'
                'text-transform:uppercase;margin:14px 0 6px 0;">'
                'ROSTER &mdash; assign exactly one SEED'
                '</div>',
                unsafe_allow_html=True,
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
                    st.markdown(
                        f'<div style="padding-top:6px;font-size:13px;color:var(--paper);">'
                        f'{p.name} <span class="mono" style="color:var(--paper-faint);font-size:11px;">'
                        f'{pid}</span></div>',
                        unsafe_allow_html=True,
                    )
                with cols[2]:
                    role = st.selectbox(
                        "role", ROLE_OPTIONS,
                        index=0 if i == 0 else min(i, 3),
                        key=f"role_{pid}",
                        label_visibility="collapsed",
                    )
                with cols[3]:
                    st.markdown(
                        f'<div style="padding-top:8px;font-family:var(--mono);'
                        f'font-size:10.5px;color:var(--paper-faint);text-align:right;">'
                        f'{p.language.upper()}</div>',
                        unsafe_allow_html=True,
                    )
                if included:
                    roster[pid] = role

            cdelay1, cdelay2, _spacer = st.columns([1, 1, 4])
            with cdelay1:
                delay_min = st.number_input("DELAY MIN (s)", min_value=0, value=300, step=30)
            with cdelay2:
                delay_max = st.number_input("DELAY MAX (s)", min_value=0, value=1800, step=60)

            submitted = st.form_submit_button("ISSUE DIRECTIVE", type="primary")
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

        st.markdown(
            f"""
<div class="dcard">
  <div class="dcard-head">
    <div>{_stamp_html("pending_approval")}</div>
    <div class="mono" style="color:var(--paper-faint);font-size:11px;letter-spacing:0.10em;">
      ROLE {glyph} · {post.role.upper()}
    </div>
  </div>
  <div class="dcard-meta">
    <div class="k">PERSONA</div>   <div class="v">{name} <span class="mono" style="color:var(--paper-faint);">({post.persona_id})</span></div>
    <div class="k">LANGUAGE</div>  <div class="v mono">{lang}</div>
    <div class="k">GENERATED</div> <div class="v mono">{_format_ts_full(post.generated_at)}</div>
    <div class="k">CAMPAIGN</div>  <div class="v mono">{post.campaign_id}</div>
  </div>
</div>
""",
            unsafe_allow_html=True,
        )

        edited = st.text_area(
            "POST CONTENT — editable",
            value=post.generated_content,
            key=f"edit_{post.id}",
            height=120,
        )
        char_count = len(edited)
        edited_flag = (edited.strip() != post.generated_content.strip())

        st.markdown(
            f"""
<div class="dcard-foot">
  <span>{char_count} CHARS · ID {post.id}</span>
  <span>SHA256: <span class="mono" style="color:var(--paper-muted);">{__import__("hashlib").sha256(edited.encode("utf-8")).hexdigest()[:16]}…</span></span>
</div>
""",
            unsafe_allow_html=True,
        )

        action_cols = st.columns([1.4, 1.4, 1, 1, 4])
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
                    "EDIT & APPROVE",
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
    _section_head("III", "AUDIT TRACE", "APPEND-ONLY · SOURCE OF TRUTH")

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
                st.markdown(
                    f"""
<div class="tg-row">
  <div class="tg-meta">
    {_stamp_html("posted")}<br>
    <span style="color:var(--paper-faint);">MSG #{p.telegram_message_id}</span><br>
    <span style="color:var(--paper-faint);">{_format_ts_short(p.posted_at)}</span><br>
    <span style="color:var(--paper-muted);">{name} · {p.role.upper()}</span>
  </div>
  <div class="tg-body">{p.final_content}</div>
</div>
""",
                    unsafe_allow_html=True,
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


def main() -> None:
    st.set_page_config(
        page_title="Mendacity / Operator Console",
        page_icon=None,
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    _inject_style()
    render_banner()
    section_operational_directive()
    section_approval_queue()
    section_audit_trace()


main()
