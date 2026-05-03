"""Telethon wrapper. One client per persona session file."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import (
    AuthKeyError,
    ChannelPrivateError,
    FloodWaitError,
    InviteHashEmptyError,
    InviteHashExpiredError,
    InviteHashInvalidError,
    SessionPasswordNeededError,
    UserAlreadyParticipantError,
    UserNotParticipantError,
)
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import (
    CheckChatInviteRequest,
    ImportChatInviteRequest,
)

_ENV_PATH = Path(__file__).parent / "config" / "api_credentials.env"
load_dotenv(_ENV_PATH)

log = logging.getLogger(__name__)


class TelegramError(RuntimeError):
    pass


class SessionExpiredError(TelegramError):
    pass


class RateLimitedError(TelegramError):
    def __init__(self, seconds: int) -> None:
        super().__init__(f"flood wait: {seconds}s")
        self.seconds = seconds


@dataclass(frozen=True)
class PostResult:
    telegram_message_id: int
    posted_at: str  # ISO-8601 UTC


@dataclass(frozen=True)
class RecentMessage:
    id: int
    date: str
    sender_id: int | None
    text: str


def _api_creds() -> tuple[int, str]:
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    if not api_id or not api_hash:
        raise TelegramError(
            "TELEGRAM_API_ID / TELEGRAM_API_HASH not set in api_credentials.env."
        )
    return int(api_id), api_hash


def _is_invite_link(channel: str) -> bool:
    return "/+" in channel or "/joinchat/" in channel


def _invite_hash(channel: str) -> str:
    """Extract the hash from a t.me/+xxxx or t.me/joinchat/xxxx invite link."""
    if "/joinchat/" in channel:
        return channel.split("/joinchat/", 1)[1].split("?")[0].rstrip("/")
    if "/+" in channel:
        return channel.split("/+", 1)[1].split("?")[0].rstrip("/")
    raise ValueError(f"not an invite link: {channel}")


class PersonaTelegramClient:
    """Owns one Telethon connection bound to a single persona's session file."""

    def __init__(self, session_path: str | Path) -> None:
        self.session_path = Path(session_path)
        api_id, api_hash = _api_creds()
        # Telethon appends .session itself; pass the stem.
        stem = str(self.session_path.with_suffix(""))
        self._client = TelegramClient(stem, api_id, api_hash)
        self._connected = False
        # Invite-link → resolved channel id, populated by join_channel().
        # send_message() uses this to target the channel after joining.
        self._invite_to_channel_id: dict[str, int] = {}

    async def start(self) -> None:
        """Idempotent connect. Raises SessionExpiredError if the session is invalid."""
        if self._connected:
            return
        try:
            await self._client.connect()
            if not await self._client.is_user_authorized():
                raise SessionExpiredError(
                    f"Session {self.session_path} not authorized. "
                    "Re-run scripts/login_persona.py for this persona."
                )
            self._connected = True
        except AuthKeyError as exc:
            raise SessionExpiredError(str(exc)) from exc

    async def stop(self) -> None:
        if self._connected:
            await self._client.disconnect()
            self._connected = False

    async def join_channel(self, channel: str) -> None:
        """Idempotent join. Accepts @username or t.me/+hash invite link."""
        await self.start()
        try:
            if _is_invite_link(channel):
                await self._join_via_invite(channel)
            else:
                entity = await self._client.get_entity(channel)
                await self._client(JoinChannelRequest(entity))
        except UserNotParticipantError:
            pass  # shouldn't reach here, but tolerate
        except ChannelPrivateError as exc:
            raise TelegramError(
                f"Channel {channel} is private or persona has no access: {exc}"
            ) from exc
        except FloodWaitError as exc:
            raise RateLimitedError(exc.seconds) from exc

    async def _join_via_invite(self, channel: str) -> None:
        invite_hash = _invite_hash(channel)
        try:
            result = await self._client(ImportChatInviteRequest(invite_hash))
            chat_id = self._extract_channel_id(result)
        except UserAlreadyParticipantError:
            # Already a member — peek the invite to recover the channel id.
            check = await self._client(CheckChatInviteRequest(invite_hash))
            chat_id = self._extract_channel_id(check)
        except (
            InviteHashEmptyError,
            InviteHashExpiredError,
            InviteHashInvalidError,
        ) as exc:
            raise TelegramError(f"invite link invalid/expired: {exc}") from exc
        if chat_id is not None:
            self._invite_to_channel_id[channel] = chat_id

    @staticmethod
    def _extract_channel_id(result) -> int | None:
        # ImportChatInviteRequest → Updates with .chats[0]
        # CheckChatInviteRequest → ChatInviteAlready with .chat
        if hasattr(result, "chats") and result.chats:
            return result.chats[0].id
        if hasattr(result, "chat") and result.chat is not None:
            return result.chat.id
        return None

    async def send_message(self, channel: str, text: str) -> PostResult:
        await self.start()
        target = self._invite_to_channel_id.get(channel, channel)
        try:
            msg = await self._client.send_message(target, text)
            return PostResult(
                telegram_message_id=msg.id,
                posted_at=datetime.now(timezone.utc).isoformat(),
            )
        except FloodWaitError as exc:
            raise RateLimitedError(exc.seconds) from exc
        except AuthKeyError as exc:
            raise SessionExpiredError(str(exc)) from exc

    async def send_image(
        self,
        channel: str,
        image_path: str | Path,
        caption: str = "",
    ) -> PostResult:
        """Post an image with optional text caption. Returns the same PostResult
        shape as send_message so callers can swap freely."""
        await self.start()
        target = self._invite_to_channel_id.get(channel, channel)
        try:
            msg = await self._client.send_file(target, file=str(image_path), caption=caption)
            return PostResult(
                telegram_message_id=msg.id,
                posted_at=datetime.now(timezone.utc).isoformat(),
            )
        except FloodWaitError as exc:
            raise RateLimitedError(exc.seconds) from exc
        except AuthKeyError as exc:
            raise SessionExpiredError(str(exc)) from exc

    async def read_recent(self, channel: str, limit: int = 20) -> list[RecentMessage]:
        await self.start()
        target = self._invite_to_channel_id.get(channel, channel)
        out: list[RecentMessage] = []
        async for msg in self._client.iter_messages(target, limit=limit):
            out.append(
                RecentMessage(
                    id=msg.id,
                    date=msg.date.isoformat() if msg.date else "",
                    sender_id=msg.sender_id,
                    text=msg.message or "",
                )
            )
        return out


async def send_with_backoff(
    client: PersonaTelegramClient,
    channel: str,
    text: str,
    *,
    max_attempts: int = 3,
) -> PostResult:
    """Wrap send_message with exponential backoff on FloodWait, per PRD §16."""
    delay = 0
    for attempt in range(1, max_attempts + 1):
        if delay:
            await asyncio.sleep(delay)
        try:
            return await client.send_message(channel, text)
        except RateLimitedError as exc:
            log.warning("rate limited (attempt %d): wait %ds", attempt, exc.seconds)
            if attempt == max_attempts:
                raise
            delay = max(exc.seconds, 2 ** attempt)
    raise TelegramError("send_with_backoff: exhausted attempts")
