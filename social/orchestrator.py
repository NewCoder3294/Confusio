"""Campaign orchestrator daemon.

Runs as a long-lived async process (PRD architecture choice B). Streamlit
talks to it through sqlite — Streamlit writes operator intent (start/approve/
reject/edit/pause/abort), this daemon performs all Telegram I/O.

Loop responsibilities:
- Generate the seed post for each freshly-created campaign.
- After seed is approved + posted, schedule non-seed roles with jittered delays.
- Generate scheduled non-seed posts when their time arrives.
- Send approved posts to Telegram; record telegram_message_id.
- Honor pause/abort.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

from social.llm import LLMClient
from social.persona_agent import PersonaAgent
from social.personas import Persona, Role, load_personas
from social.prompts import PreviousPost
from social.storage import (
    Campaign,
    GeneratedPost,
    Storage,
    now_iso,
)
from social.telegram_client import (
    PersonaTelegramClient,
    RateLimitedError,
    SessionExpiredError,
    TelegramError,
)

_ENV_PATH = Path(__file__).parent / "config" / "api_credentials.env"
_CHANNEL_CFG_PATH = Path(__file__).parent / "config" / "channel_config.json"
HEARTBEAT_PATH = Path(__file__).parent / ".heartbeat"
load_dotenv(_ENV_PATH)

log = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 1.5


def _load_allowed_channels() -> list[str]:
    if not _CHANNEL_CFG_PATH.exists():
        return []
    return json.loads(_CHANNEL_CFG_PATH.read_text(encoding="utf-8")).get(
        "allowed_channels", []
    )


def _operator() -> str:
    return os.getenv("OPERATOR_USER_ID", "unknown")


class CampaignValidationError(ValueError):
    pass


class Orchestrator:
    def __init__(
        self,
        agents: dict[str, PersonaAgent],
        storage: Storage,
        *,
        allowed_channels: list[str] | None = None,
        auto_approve_sandbox: bool = False,
    ) -> None:
        self.agents = agents
        self.storage = storage
        self.allowed_channels = allowed_channels or _load_allowed_channels()
        self.auto_approve_sandbox = auto_approve_sandbox
        self._joined: set[tuple[str, str]] = set()  # (persona_id, channel)

    # ---------- public API (called by Streamlit via direct DB writes,
    #            or directly when in-process) ----------

    async def submit_campaign(self, campaign: Campaign) -> Campaign:
        """Validate + persist a new campaign. Does NOT generate yet —
        the daemon poll loop picks it up."""
        self._validate_campaign(campaign)
        await self.storage.insert_campaign(campaign)
        self.storage.append_log(
            "campaign_created",
            campaign_id=campaign.id,
            operator=campaign.created_by,
            extra={
                "intent": campaign.intent,
                "channel": campaign.channel,
                "roster": campaign.roster,
                "delay_range_seconds": list(campaign.delay_range_seconds),
            },
        )
        # Mark running so the poll loop will act on it.
        await self.storage.update_campaign_status(campaign.id, "running")
        return campaign

    async def approve(
        self, post_id: str, *, edited_content: str | None = None
    ) -> None:
        post = await self.storage.get_post(post_id)
        if not post:
            raise ValueError(f"unknown post {post_id}")
        if post.status != "pending_approval":
            raise ValueError(f"post {post_id} not pending (status={post.status})")
        await self.storage.update_post_decision(
            post_id,
            status="approved",
            decided_by=_operator(),
            edited_content=edited_content,
        )
        self.storage.append_log(
            "post_approved",
            campaign_id=post.campaign_id,
            persona_id=post.persona_id,
            role=post.role,
            content=edited_content or post.generated_content,
            operator=_operator(),
            extra={"edited": edited_content is not None},
        )

    async def reject(self, post_id: str, *, regenerate: bool = False) -> None:
        post = await self.storage.get_post(post_id)
        if not post:
            raise ValueError(f"unknown post {post_id}")
        if post.status != "pending_approval":
            raise ValueError(f"post {post_id} not pending (status={post.status})")
        await self.storage.update_post_decision(
            post_id, status="rejected", decided_by=_operator()
        )
        self.storage.append_log(
            "post_rejected",
            campaign_id=post.campaign_id,
            persona_id=post.persona_id,
            role=post.role,
            content=post.generated_content,
            operator=_operator(),
            extra={"regenerate": regenerate},
        )
        if regenerate:
            await self.storage.upsert_schedule_for_regen(
                post.campaign_id, post.persona_id, post.role, now_iso()
            )

    async def pause(self, campaign_id: str) -> None:
        await self.storage.update_campaign_status(campaign_id, "paused")
        self.storage.append_log(
            "campaign_paused", campaign_id=campaign_id, operator=_operator()
        )

    async def resume(self, campaign_id: str) -> None:
        await self.storage.update_campaign_status(campaign_id, "running")
        self.storage.append_log(
            "campaign_resumed", campaign_id=campaign_id, operator=_operator()
        )

    async def abort(self, campaign_id: str) -> None:
        await self.storage.update_campaign_status(campaign_id, "aborted")
        await self.storage.delete_schedule_for_campaign(campaign_id)
        # Mark any pending posts as rejected so they leave the queue.
        pending = [
            p
            for p in await self.storage.list_posts_for_campaign(campaign_id)
            if p.status == "pending_approval"
        ]
        for p in pending:
            await self.storage.update_post_decision(
                p.id, status="rejected", decided_by=_operator()
            )
        self.storage.append_log(
            "campaign_aborted",
            campaign_id=campaign_id,
            operator=_operator(),
            extra={"cancelled_pending": len(pending)},
        )

    # ---------- daemon loop ----------

    async def run_forever(self) -> None:
        log.info(
            "orchestrator daemon up: %d agents, allowed=%s",
            len(self.agents),
            self.allowed_channels,
        )
        # Connect every persona once at startup so we fail fast on bad sessions.
        for agent in self.agents.values():
            try:
                await agent.start()
            except SessionExpiredError as exc:
                log.error("persona %s session bad: %s", agent.id, exc)
                raise

        while True:
            try:
                await self._tick()
                HEARTBEAT_PATH.touch()
            except Exception:
                log.exception("orchestrator tick error")
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    async def _tick(self) -> None:
        # 0. (optional) Auto-approve corroborator posts on sandbox channels.
        if self.auto_approve_sandbox:
            await self._auto_approve_sandbox_posts()
        # 1. Send approved posts.
        await self._post_approved()
        # 2. For each running campaign: ensure seed exists; on seed posted,
        #    materialize the schedule for non-seed roles.
        for campaign in await self.storage.list_active_campaigns():
            if campaign.status != "running":
                continue
            await self._tick_campaign(campaign)
        # 3. Generate due scheduled posts.
        await self._generate_due()

    async def _tick_campaign(self, campaign: Campaign) -> None:
        seed_persona_id = self._seed_persona(campaign)
        all_posts = await self.storage.list_posts_for_campaign(campaign.id)
        seed_posts = [p for p in all_posts if p.role == "seed"]

        if not seed_posts:
            await self._generate_one(campaign, seed_persona_id, "seed")
            return

        seed = seed_posts[-1]
        if seed.status == "rejected":
            # Operator's reject(regenerate=True) writes a schedule row that
            # _generate_due will pick up. Pure reject (regenerate=False) leaves
            # the campaign stalled until operator acts (per FR-5.5).
            return
        if seed.status != "posted":
            return  # waiting for approval / posting

        # Seed is live → ensure schedule rows exist for all non-seed roles.
        await self._ensure_schedule(campaign, seed.posted_at or now_iso())

    async def _generate_one(
        self, campaign: Campaign, persona_id: str, role: Role
    ) -> None:
        agent = self.agents.get(persona_id)
        if not agent:
            log.error("no agent for persona %s in campaign %s", persona_id, campaign.id)
            return
        previous = await self._previous_posts(campaign.id)
        self.storage.append_log(
            "generation_requested",
            campaign_id=campaign.id,
            persona_id=persona_id,
            role=role,
        )
        try:
            post = await agent.generate(campaign, role, previous)
        except Exception as exc:
            log.exception("generation failed")
            self.storage.append_log(
                "generation_failed",
                campaign_id=campaign.id,
                persona_id=persona_id,
                role=role,
                extra={"error": str(exc)},
            )
            return
        await self.storage.insert_post(post)
        self.storage.append_log(
            "content_generated",
            campaign_id=campaign.id,
            persona_id=persona_id,
            role=role,
            content=post.generated_content,
        )

    async def _ensure_schedule(self, campaign: Campaign, anchor_iso: str) -> None:
        seed_id = self._seed_persona(campaign)
        existing = {
            (pid, role)
            for (pid, role) in [
                (p.persona_id, p.role)
                for p in await self.storage.list_posts_for_campaign(campaign.id)
            ]
        }
        anchor = datetime.fromisoformat(anchor_iso)
        lo, hi = campaign.delay_range_seconds
        for persona_id, role in campaign.roster.items():
            if persona_id == seed_id:
                continue
            if (persona_id, role) in existing:
                continue
            jitter = random.randint(lo, hi)
            scheduled = (anchor + timedelta(seconds=jitter)).isoformat()
            await self.storage.insert_schedule(
                campaign.id, persona_id, role, scheduled
            )

    async def _generate_due(self) -> None:
        due = await self.storage.list_due_schedule(now=now_iso())
        for campaign_id, persona_id, role, _scheduled in due:
            campaign = await self.storage.get_campaign(campaign_id)
            if not campaign:
                continue
            await self._generate_one(campaign, persona_id, role)
            await self.storage.mark_schedule_generated(campaign_id, persona_id, role)

    async def _auto_approve_sandbox_posts(self) -> None:
        """Flip pending_approval → approved for sandbox-channel posts.

        Only runs when ``auto_approve_sandbox`` is enabled. In sandbox mode
        seed posts are also auto-approved so the operator console can drive
        the full cascade end-to-end without manual gating.
        """
        for campaign in await self.storage.list_active_campaigns():
            if campaign.status != "running":
                continue
            if self.allowed_channels and campaign.channel not in self.allowed_channels:
                continue
            pending = await self.storage.list_posts_for_campaign(
                campaign.id, statuses=("pending_approval",)
            )
            for post in pending:
                await self.storage.update_post_decision(
                    post.id,
                    status="approved",
                    decided_by="auto_approve_sandbox",
                )
                self.storage.append_log(
                    "post_approved",
                    campaign_id=post.campaign_id,
                    persona_id=post.persona_id,
                    role=post.role,
                    content=post.generated_content,
                    operator="auto_approve_sandbox",
                    extra={"auto": True, "channel": campaign.channel},
                )

    async def _post_approved(self) -> None:
        # Find approved posts across all running campaigns.
        for campaign in await self.storage.list_active_campaigns():
            if campaign.status != "running":
                continue
            posts = await self.storage.list_posts_for_campaign(
                campaign.id, statuses=("approved",)
            )
            for post in posts:
                agent = self.agents.get(post.persona_id)
                if not agent:
                    await self.storage.update_post_failed(
                        post.id, error=f"no agent for persona {post.persona_id}"
                    )
                    continue
                # Image-bearing campaigns: the seed always rides on the
                # generated artifact, so defer until that file lands. For
                # corroborators we attach a perspective image only if one
                # exists on disk — text-only replies are valid (and expected)
                # for the chorus around the single supporting image.
                if self._campaign_expects_image(campaign):
                    image_path = self._image_for(campaign, post)
                    if post.role == "seed" and image_path is None:
                        log.info(
                            "deferring %s post for %s/%s — image not ready",
                            post.role, campaign.id, post.persona_id,
                        )
                        continue
                else:
                    image_path = None
                try:
                    join_key = (agent.id, campaign.channel)
                    if join_key not in self._joined:
                        await agent.join(campaign.channel)
                        self._joined.add(join_key)
                    if image_path is not None:
                        result = await agent.post_image(
                            str(image_path), post.final_content, campaign.channel
                        )
                    else:
                        result = await agent.post(
                            post.final_content, campaign.channel
                        )
                except RateLimitedError as exc:
                    await self.storage.update_post_failed(
                        post.id, error=f"rate limited after retries: {exc.seconds}s"
                    )
                    self.storage.append_log(
                        "post_failed",
                        campaign_id=post.campaign_id,
                        persona_id=post.persona_id,
                        role=post.role,
                        extra={"error": "rate_limited", "wait": exc.seconds},
                    )
                    continue
                except (SessionExpiredError, TelegramError) as exc:
                    await self.storage.update_post_failed(post.id, error=str(exc))
                    self.storage.append_log(
                        "post_failed",
                        campaign_id=post.campaign_id,
                        persona_id=post.persona_id,
                        role=post.role,
                        extra={"error": str(exc)},
                    )
                    continue
                await self.storage.update_post_posted(
                    post.id,
                    telegram_message_id=result.telegram_message_id,
                    posted_at=result.posted_at,
                )
                self.storage.append_log(
                    "post_sent",
                    campaign_id=post.campaign_id,
                    persona_id=post.persona_id,
                    role=post.role,
                    content=post.final_content,
                    extra={"telegram_message_id": result.telegram_message_id},
                )

    # ---------- helpers ----------

    async def _previous_posts(self, campaign_id: str) -> list[PreviousPost]:
        """Approved-and-posted posts in chronological order."""
        posts = await self.storage.list_posts_for_campaign(
            campaign_id, statuses=("posted",)
        )
        anchor = datetime.fromisoformat(posts[0].posted_at) if posts else None
        out: list[PreviousPost] = []
        for p in posts:
            offset = "T+0"
            if anchor and p.posted_at:
                delta = datetime.fromisoformat(p.posted_at) - anchor
                mins = int(delta.total_seconds() // 60)
                offset = f"T+{mins}m"
            persona = self.agents[p.persona_id].persona
            out.append(
                PreviousPost(
                    persona_name=persona.name,
                    role=p.role,
                    content=p.final_content,
                    posted_at_offset=offset,
                    language=persona.language,
                )
            )
        return out

    def _campaign_expects_image(self, campaign: Campaign) -> bool:
        """Operator-console-dispatched campaigns always carry a generated
        artifact. Their ids are namespaced as ``c_SHADOW-FOX-...``."""
        return campaign.id.startswith("c_SHADOW-FOX-")

    def _image_for(self, campaign: Campaign, post: GeneratedPost) -> Path | None:
        """Return the artifact image path to attach when sending `post`, or
        None if it isn't ready yet. Seed posts ride on the seed artifact
        ``missions/generated/{mission_id}.{jpg|png}``. Corroborator posts
        ride on their own perspective image
        ``missions/generated/{mission_id}-{persona_id}.{jpg|png}`` (produced
        by ``mendacity.cascade_images``). JPEG preferred over PNG."""
        mission_id = (
            campaign.id[2:] if campaign.id.startswith("c_") else campaign.id
        )
        gen_dir = Path(__file__).resolve().parent.parent / "missions" / "generated"
        if post.role == "seed":
            stems = [mission_id]
        else:
            stems = [f"{mission_id}-{post.persona_id}"]
        for stem in stems:
            for ext in ("jpg", "png"):
                candidate = gen_dir / f"{stem}.{ext}"
                if candidate.exists() and candidate.stat().st_size > 0:
                    return candidate
        return None

    def _seed_persona(self, campaign: Campaign) -> str:
        seeds = [pid for pid, role in campaign.roster.items() if role == "seed"]
        if len(seeds) != 1:
            raise CampaignValidationError(
                f"campaign {campaign.id} must have exactly one seed (got {len(seeds)})"
            )
        return seeds[0]

    def _validate_campaign(self, campaign: Campaign) -> None:
        if self.allowed_channels and campaign.channel not in self.allowed_channels:
            raise CampaignValidationError(
                f"channel {campaign.channel} not in allow-list "
                f"({self.allowed_channels}). Edit social/config/channel_config.json."
            )
        # exactly one seed
        self._seed_persona(campaign)
        # roster persona ids must exist
        unknown = [pid for pid in campaign.roster if pid not in self.agents]
        if unknown:
            raise CampaignValidationError(f"unknown personas in roster: {unknown}")
        # delay range sanity
        lo, hi = campaign.delay_range_seconds
        if lo < 0 or hi < lo:
            raise CampaignValidationError(
                f"invalid delay range {campaign.delay_range_seconds}"
            )


def build_orchestrator(
    *,
    require_sessions: bool = True,
    auto_approve_sandbox: bool = False,
) -> Orchestrator:
    """Wire personas → agents → orchestrator. Used by the daemon entrypoint.

    library_only personas (no Telethon session of their own) are paired with
    a carrier persona's client at post time. The orchestrator still treats
    them as first-class agents — the LLM prompt uses the library persona's
    voice, the post body carries that voice, and the post is sent through
    the carrier's logged-in session. Carriers are picked round-robin so the
    load spreads.
    """
    personas = load_personas(require_sessions=require_sessions)
    llm = LLMClient()
    agents: dict[str, PersonaAgent] = {}

    # First pass: build live agents (real session per persona).
    live_clients: list[PersonaTelegramClient] = []
    for pid, persona in personas.items():
        if persona.library_only:
            continue
        tg = PersonaTelegramClient(persona.resolved_session_path())
        agents[pid] = PersonaAgent(persona, llm, tg)
        live_clients.append(tg)

    if not live_clients:
        raise PersonaLoadError(
            "no live persona sessions available; cannot route library_only "
            "personas without at least one carrier session."
        )

    # Second pass: library personas borrow a carrier's client round-robin.
    carrier_idx = 0
    for pid, persona in personas.items():
        if not persona.library_only:
            continue
        carrier = live_clients[carrier_idx % len(live_clients)]
        carrier_idx += 1
        agents[pid] = PersonaAgent(persona, llm, carrier)
        log.info(
            "library persona %s carried by session %s",
            pid, carrier.session_path.name,
        )

    storage = Storage()
    return Orchestrator(
        agents,
        storage,
        auto_approve_sandbox=auto_approve_sandbox,
    )


async def _main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Mendacity campaign orchestrator daemon.")
    parser.add_argument(
        "--auto-approve-sandbox",
        action="store_true",
        help="Auto-approve non-seed posts on channels in the sandbox allowlist.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=os.getenv("MENDACITY_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    orch = build_orchestrator(
        require_sessions=True,
        auto_approve_sandbox=args.auto_approve_sandbox,
    )
    await orch.storage.init()
    await orch.run_forever()


if __name__ == "__main__":
    asyncio.run(_main())
