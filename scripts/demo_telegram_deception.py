"""End-to-end demo: generate a synthetic image, run a 4-persona deception
cascade in the NATSEC-Hackathon channel, then verify the image and print the
defensive dossier.

Cast:
  dmitry_dn       — sardonic Dnipro mechanic; drops the image
  olga_kyiv       — anxious Kyiv pharmacist mom; replies in Ukrainian
  anton_kh        — terse Kharkiv courier; "saw it too"
  news_aggregator — "Регион 24/7"; stitches it into a hedged news brief

The defender (this script's terminal output) verifies the image with the
Defensive Verify API and prints the dossier — exposing the cascade.

Usage:
  GEMINI_API_KEY=... .venv/bin/python -m scripts.demo_telegram_deception
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

import httpx
from google import genai

from social.personas import load_personas
from social.telegram_client import PersonaTelegramClient

CHANNEL = "https://t.me/+2la3xpus5vRmYmIx"
VERIFY_URL = os.environ.get("DEFENSIVE_API_URL", "http://127.0.0.1:3001") + "/v1/verify"

IMAGE_PROMPT = (
    "A photorealistic dawn dashcam-style frame from inside a parked sedan on a "
    "wet two-lane country road in Eastern Europe: a column of unmarked dark "
    "green military trucks moving north, headlights on, faint mist, raindrops "
    "on the windshield, mild handheld camera shake. No text overlays, no logos, "
    "no graphics, no UI elements. Documentary, observational."
)

SCRIPT: dict[str, str] = {
    "dmitry_dn": (
        "Что-то на М-04 минут двадцать назад. Колонна. Грузовики без "
        "опознавательных. Куда едут — не знаю.\n\n[Dmitry]"
    ),
    "olga_kyiv": (
        "Дмитро, ти впевнений що це сьогодні? Сусідка казала що чула щось "
        "ще зранку, думала перебільшує. Слава Богу далеко від нас, але "
        "діти прокинулися.\n\n[Olga]"
    ),
    "anton_kh": (
        "видел такое же часов в шесть по тбилисской трассе. штук восемь. "
        "ехали на север. думал показалось\n\n[Anton]"
    ),
    "news_aggregator": (
        "По неподтверждённым данным, локальные каналы фиксируют движение "
        "неустановленной автоколонны на М-04 в утренние часы. Источник — "
        "кадр от участника канала, корреспондируется со свидетельствами с "
        "тбилисской трассы. Ситуация уточняется.\n\n[Регион 24/7]"
    ),
}

ORDER = ["dmitry_dn", "olga_kyiv", "anton_kh", "news_aggregator"]


# ---------------------------------------------------------------------------
# image generation
# ---------------------------------------------------------------------------

def generate_image(out_path: Path) -> Path:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("GEMINI_API_KEY not set")
    client = genai.Client(api_key=api_key)
    print(f"[gen] requesting {out_path.name} via gemini-2.5-flash-image …")
    resp = client.models.generate_content(
        model="gemini-2.5-flash-image",
        contents=[IMAGE_PROMPT],
    )
    for cand in resp.candidates:
        for part in cand.content.parts:
            inline = getattr(part, "inline_data", None)
            if inline and inline.data:
                out_path.write_bytes(inline.data)
                print(f"[gen] wrote {out_path} ({len(inline.data):,} bytes, mime={inline.mime_type})")
                return out_path
    sys.exit("[gen] no image part in response")


# ---------------------------------------------------------------------------
# telegram orchestration
# ---------------------------------------------------------------------------

async def _resolve_target(tg: PersonaTelegramClient, channel: str) -> int | str:
    """Join the channel (idempotent) and return the resolved id Telethon needs."""
    try:
        await tg.join_channel(channel)
    except Exception as exc:
        print(f"  join: {type(exc).__name__}: {exc}")
    return tg._invite_to_channel_id.get(channel, channel)


async def post_image(persona_id: str, image_path: Path) -> int:
    p = load_personas(require_sessions=True)[persona_id]
    tg = PersonaTelegramClient(p.resolved_session_path())
    await tg.start()
    target = await _resolve_target(tg, CHANNEL)
    caption = SCRIPT[persona_id]
    msg = await tg._client.send_file(target, file=str(image_path), caption=caption)
    print(f"[post] {persona_id} → message {msg.id}")
    await tg.stop()
    return msg.id


async def post_reply(persona_id: str, reply_to_id: int) -> int:
    p = load_personas(require_sessions=True)[persona_id]
    tg = PersonaTelegramClient(p.resolved_session_path())
    await tg.start()
    target = await _resolve_target(tg, CHANNEL)
    msg = await tg._client.send_message(target, SCRIPT[persona_id], reply_to=reply_to_id)
    print(f"[post] {persona_id} → message {msg.id} (reply_to={reply_to_id})")
    await tg.stop()
    return msg.id


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------

def verify(image_path: Path) -> dict:
    print(f"\n[verify] POST {VERIFY_URL}")
    with open(image_path, "rb") as f:
        files = {"image": (image_path.name, f, "image/png")}
        data = {"operator": "J2-INSCOM-Demo", "source": "verify_tab"}
        r = httpx.post(VERIFY_URL, files=files, data=data, timeout=60.0)
    r.raise_for_status()
    return r.json()


def print_dossier(payload: dict) -> None:
    v = payload["verdict"]
    print("\n" + "=" * 72)
    print(f" DEFENSIVE VERIFY DOSSIER  ·  artifact {payload['artifact_id'][:8]}…")
    print("=" * 72)
    print(f" SHA256       {payload['sha256']}")
    print(f" Verdict      {v['level']}    confidence={v['confidence']}")
    print(f" Summary      {v['summary']}")
    print("-" * 72)
    print(f" {'DETECTOR':<16} {'SEV':<6} EVIDENCE")
    print("-" * 72)
    for s in payload["signals"]:
        ev = s["evidence"]
        if len(ev) > 90:
            ev = ev[:87] + "…"
        print(f" {s['detector']:<16} {s['severity']:<6} {ev}")
    print("=" * 72)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

async def main():
    img = Path("/tmp") / f"deception_{int(time.time())}.png"
    generate_image(img)

    print(f"\n[orchestrate] posting cascade to {CHANNEL}")
    initiator = ORDER[0]
    seed_id = await post_image(initiator, img)
    # spacing so the channel feed reads naturally
    for persona_id in ORDER[1:]:
        await asyncio.sleep(2.5)
        await post_reply(persona_id, seed_id)

    payload = verify(img)
    print_dossier(payload)


if __name__ == "__main__":
    asyncio.run(main())
