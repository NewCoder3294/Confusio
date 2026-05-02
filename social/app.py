"""Streamlit operator console.

Runs as a separate process from the orchestrator daemon. Communicates with
the daemon by reading and writing the shared sqlite DB (and append-only log).
This UI never touches Telethon directly — all Telegram I/O is the daemon's
responsibility.

Run: streamlit run social/app.py
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

import streamlit as st

from social.orchestrator import (
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

ROLE_OPTIONS = ["seed", "witness", "reaction", "aggregator"]
ROLE_BADGE_COLOR = {
    "seed": "#9b1c1c",
    "witness": "#1c4f9b",
    "reaction": "#1c9b4e",
    "aggregator": "#7a1c9b",
}


def _run(coro):
    return asyncio.run(coro)


@st.cache_resource
def _get_personas():
    # require_sessions=False so the UI loads even before sessions exist;
    # the orchestrator daemon enforces sessions at startup.
    return load_personas(require_sessions=False)


@st.cache_resource
def _get_orchestrator():
    """A UI-only orchestrator instance for routing operator actions into the DB.

    No PersonaAgent objects — those need real Telethon sessions and live in
    the daemon process. Construct with empty agents and override the
    validation hook so submit_campaign still validates roster IDs against
    persona files.
    """
    personas = _get_personas()
    storage = Storage()
    _run(storage.init())

    # We need persona-id awareness for validation but no live agents.
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
                    f"channel {campaign.channel} not in allow-list. "
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


def _role_badge(role: str) -> str:
    color = ROLE_BADGE_COLOR.get(role, "#444")
    return (
        f"<span style='background:{color};color:white;padding:2px 8px;"
        f"border-radius:10px;font-size:11px;font-weight:600;'>{role.upper()}</span>"
    )


def _format_ts(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%H:%M:%S")
    except (ValueError, TypeError):
        return iso or ""


# ---------- sections ----------


def section_campaign_creator() -> None:
    st.subheader("A. Campaign creator")
    personas = _get_personas()
    orch = _get_orchestrator()
    allowed = _allowed_channels()

    with st.form("new_campaign", clear_on_submit=False):
        intent = st.text_area(
            "Intent",
            placeholder="e.g. Unusual military movement near M-04 highway around dawn",
            height=80,
        )

        if allowed:
            channel = st.selectbox("Channel (allow-list)", allowed)
        else:
            channel = st.text_input("Channel", value="@mendacity_demo_channel")

        st.markdown("**Persona roster** — assign exactly one seed.")
        roster: dict[str, str] = {}
        cols = st.columns(2)
        for i, (pid, p) in enumerate(personas.items()):
            with cols[i % 2]:
                included = st.checkbox(
                    f"{p.name} ({pid}) · {p.language}", value=True, key=f"inc_{pid}"
                )
                if included:
                    role = st.selectbox(
                        f"role for {p.name}",
                        ROLE_OPTIONS,
                        index=0 if pid == list(personas)[0] else 1,
                        key=f"role_{pid}",
                    )
                    roster[pid] = role

        c1, c2 = st.columns(2)
        with c1:
            delay_min = st.number_input(
                "Delay min (s)", min_value=0, value=300, step=30
            )
        with c2:
            delay_max = st.number_input(
                "Delay max (s)", min_value=0, value=1800, step=60
            )

        submitted = st.form_submit_button("Start campaign", type="primary")
        if submitted:
            try:
                c = Campaign.new(
                    intent=intent.strip(),
                    channel=channel,
                    delay_range_seconds=(int(delay_min), int(delay_max)),
                    created_by="nick",
                    roster=roster,
                )
                _run(orch.submit_campaign(c))
                st.success(f"Campaign {c.id} submitted (status: running)")
                st.rerun()
            except CampaignValidationError as exc:
                st.error(f"Validation error: {exc}")
            except Exception as exc:
                st.error(f"Error: {exc}")


def section_approval_queue() -> None:
    st.subheader("B. Approval queue")
    orch = _get_orchestrator()
    personas = _get_personas()
    pending: list[GeneratedPost] = _run(orch.storage.list_pending())

    if not pending:
        st.info("No posts awaiting approval.")
        return

    for post in pending:
        persona = personas.get(post.persona_id)
        name = persona.name if persona else post.persona_id
        lang = persona.language if persona else "?"
        with st.container(border=True):
            top = st.columns([3, 1, 1, 1])
            with top[0]:
                st.markdown(f"**{name}** &nbsp; {_role_badge(post.role)}", unsafe_allow_html=True)
                st.caption(
                    f"persona={post.persona_id} · lang={lang} · "
                    f"generated_at={_format_ts(post.generated_at)} · "
                    f"chars={len(post.generated_content)}"
                )
            edited_key = f"edit_{post.id}"
            edited = st.text_area(
                "Content",
                value=post.generated_content,
                key=edited_key,
                height=110,
                label_visibility="collapsed",
            )
            actions = st.columns(4)
            with actions[0]:
                if st.button("APPROVE", key=f"ap_{post.id}", type="primary"):
                    _run(orch.approve(post.id))
                    st.rerun()
            with actions[1]:
                if st.button("EDIT & APPROVE", key=f"ea_{post.id}"):
                    _run(orch.approve(post.id, edited_content=edited))
                    st.rerun()
            with actions[2]:
                if st.button("REJECT", key=f"rj_{post.id}"):
                    _run(orch.reject(post.id))
                    st.rerun()
            with actions[3]:
                if st.button("REJECT + REGEN", key=f"rg_{post.id}"):
                    _run(orch.reject(post.id, regenerate=True))
                    st.rerun()


def section_log_and_mirror() -> None:
    st.subheader("C. Live channel mirror + log feed")
    orch = _get_orchestrator()
    personas = _get_personas()

    tabs = st.tabs(["Channel mirror (sent posts)", "Audit log"])
    with tabs[0]:
        active = _run(orch.storage.list_active_campaigns())
        if not active:
            st.caption("No active campaigns.")
        for c in active:
            st.markdown(
                f"**Campaign** `{c.id}` · channel `{c.channel}` · status `{c.status}`"
            )
            posted = [
                p
                for p in _run(
                    orch.storage.list_posts_for_campaign(c.id, statuses=("posted",))
                )
            ]
            if not posted:
                st.caption("No posts sent yet.")
                continue
            for p in posted:
                persona = personas.get(p.persona_id)
                name = persona.name if persona else p.persona_id
                with st.container(border=True):
                    st.markdown(
                        f"**{name}** {_role_badge(p.role)} · "
                        f"posted_at={_format_ts(p.posted_at or '')} · "
                        f"tg_msg_id={p.telegram_message_id}",
                        unsafe_allow_html=True,
                    )
                    st.write(p.final_content)

    with tabs[1]:
        log = orch.storage.tail_log(80)
        if not log:
            st.caption("Audit log is empty.")
        for entry in reversed(log):
            ts = _format_ts(entry.get("ts", ""))
            ev = entry.get("event", "?")
            cid = entry.get("campaign_id") or ""
            pid = entry.get("persona_id") or ""
            role = entry.get("role") or ""
            content = entry.get("content")
            head = f"`{ts}` **{ev}**"
            if cid:
                head += f" · campaign=`{cid[-6:]}`"
            if pid:
                head += f" · {pid}"
            if role:
                head += f" · {role}"
            st.markdown(head)
            if content:
                with st.expander("content", expanded=False):
                    st.write(content)


# ---------- shell ----------


def main() -> None:
    st.set_page_config(page_title="Mendacity", layout="wide")
    st.title("Mendacity — operator console")
    st.caption(
        "Issue #3. Operator-in-the-loop is mandatory. Every post requires "
        "explicit approval. Channel allow-list enforced."
    )

    daemon_warning = st.empty()
    if not Path(__file__).parent.joinpath("mendacity.db").exists():
        daemon_warning.warning(
            "DB not initialized yet. Start the orchestrator daemon: "
            "`python -m social.orchestrator`"
        )

    left, right = st.columns([1, 1])
    with left:
        section_campaign_creator()
        section_approval_queue()
    with right:
        section_log_and_mirror()

    st.divider()
    if st.button("Refresh"):
        st.rerun()


if __name__ == "__main__":
    main()
else:
    main()  # Streamlit imports the module
