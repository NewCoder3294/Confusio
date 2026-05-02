"""PersonaAgent — binds one persona to its LLM + Telethon client."""

from __future__ import annotations

import logging

from social.llm import LLMClient
from social.personas import Persona, Role
from social.prompts import PreviousPost, build_prompt
from social.storage import Campaign, GeneratedPost
from social.telegram_client import (
    PersonaTelegramClient,
    PostResult,
    send_with_backoff,
)

log = logging.getLogger(__name__)


class PersonaAgent:
    def __init__(
        self,
        persona: Persona,
        llm: LLMClient,
        tg: PersonaTelegramClient,
    ) -> None:
        self.persona = persona
        self._llm = llm
        self._tg = tg

    @property
    def id(self) -> str:
        return self.persona.id

    async def start(self) -> None:
        """Connect Telethon. Idempotent."""
        await self._tg.start()

    async def stop(self) -> None:
        await self._tg.stop()

    async def join(self, channel: str) -> None:
        await self._tg.join_channel(channel)

    async def generate(
        self,
        campaign: Campaign,
        role: Role,
        previous_posts: list[PreviousPost],
    ) -> GeneratedPost:
        """Build role prompt, call LLM, return GeneratedPost(pending_approval)."""
        prompt = build_prompt(
            self.persona, role, intent=campaign.intent, previous_posts=previous_posts
        )
        log.info(
            "generate: campaign=%s persona=%s role=%s prev=%d",
            campaign.id, self.persona.id, role, len(previous_posts),
        )
        content = await self._llm.generate(prompt)
        return GeneratedPost.new(
            campaign_id=campaign.id,
            persona_id=self.persona.id,
            role=role,
            generated_content=content,
        )

    async def post(self, content: str, channel: str) -> PostResult:
        """Send via Telethon with FloodWait backoff. Operator-approved content only."""
        return await send_with_backoff(self._tg, channel, content)
