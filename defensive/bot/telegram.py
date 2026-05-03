"""Telegram verify bot — DMs photos, calls /v1/verify, replies with verdict.

Whitelisted Telegram user IDs only. Group/channel messages ignored.
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import time
from collections import defaultdict
from typing import Any

import httpx
from telethon import TelegramClient, events

from defensive.bot.whitelist import load as load_whitelist

LOG = logging.getLogger("defensive.bot")

API_URL = os.environ.get("DEFENSIVE_API_URL", "http://127.0.0.1:3001")
RATE_LIMIT_SECONDS = 60

# Per-sender last-rejection timestamp; suppresses log spam from non-whitelisted senders.
_recent_rejections: dict[int, float] = defaultdict(lambda: 0.0)


def _build_client() -> TelegramClient:
    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]
    session_name = os.environ.get("DEFENSIVE_BOT_SESSION", "defensive_verify_bot")
    return TelegramClient(session_name, api_id, api_hash)


async def _verify_image(image_bytes: bytes, mime: str, operator: str) -> dict[str, Any]:
    files = {"image": ("image.jpg", image_bytes, mime)}
    data = {"operator": operator, "source": "telegram_bot"}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{API_URL}/v1/verify", files=files, data=data)
        if r.status_code >= 400:
            return {"_error": True, "status": r.status_code, "body": r.json()}
        return r.json()


def _format_reply(body: dict[str, Any]) -> str:
    if body.get("_error"):
        detail = body["body"].get("detail", {})
        code = detail.get("code", "unknown") if isinstance(detail, dict) else "unknown"
        if code == "image_too_large":
            return "Image too large (10 MB max)."
        if code == "unsupported_mime":
            return "Unsupported format — JPEG, PNG, or WebP only."
        if code == "image_invalid":
            return "Image invalid or corrupt."
        return f"Verify service error ({code})."
    v = body["verdict"]
    return (
        f"VERDICT  {v['level']}  (confidence {v['confidence']:.2f})\n"
        f"{v['summary']}\n"
        f"Dossier · {API_URL}/v1/verify/{body['artifact_id']}\n"
        f"artifact_id: {body['artifact_id']} · sha256: {body['sha256'][:8]}…{body['sha256'][-4:]}"
    )


def _attach_handlers(client: TelegramClient, whitelist: dict[int, str]) -> None:
    @client.on(events.NewMessage(incoming=True))
    async def handle(event):
        if not event.is_private:
            return  # ignore group/channel
        sender_id = event.sender_id

        # /start, /help — capability description
        text = event.raw_text or ""
        if text.startswith("/start") or text.startswith("/help"):
            operator = whitelist.get(sender_id)
            if operator:
                await event.reply(
                    "Mendacity Verify bot.\n"
                    f"You are mapped to operator identity: {operator}\n"
                    "DM me a photo to get a verdict (composite of 7 detectors).\n"
                    "JPEG, PNG, or WebP. 10 MB max."
                )
            else:
                await event.reply("Mendacity Verify bot. You are not authorized.")
            return

        # Whitelist check
        if sender_id not in whitelist:
            now = time.monotonic()
            if now - _recent_rejections[sender_id] >= RATE_LIMIT_SECONDS:
                _recent_rejections[sender_id] = now
                await event.reply("Not authorized.")
            return  # silent suppression within the rate-limit window

        operator = whitelist[sender_id]

        # Photo or photo-as-document
        if not (event.photo or (event.document and (event.document.mime_type or "").startswith("image/"))):
            return  # ignore text-only messages from whitelisted users

        try:
            image_bytes = await event.download_media(file=bytes)
        except Exception as e:
            await event.reply(f"Could not read attachment: {type(e).__name__}.")
            return

        mime = "image/jpeg"
        if event.document and event.document.mime_type:
            mime = event.document.mime_type

        if len(image_bytes) > 10 * 1024 * 1024:
            await event.reply("Image too large (10 MB max).")
            return

        try:
            body = await _verify_image(image_bytes, mime, operator)
        except httpx.RequestError:
            await event.reply("Verify service unreachable. Try again shortly.")
            return

        await event.reply(_format_reply(body))


async def run() -> None:
    """Start the bot. Blocks forever."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    whitelist = load_whitelist()
    LOG.info("loaded whitelist: %d users", len(whitelist))
    client = _build_client()
    _attach_handlers(client, whitelist)
    await client.start(bot_token=bot_token)
    LOG.info("bot started")
    await client.run_until_disconnected()
