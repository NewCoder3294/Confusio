"""Interactive one-time Telethon login for a persona.

Produces social/sessions/<persona_id>.session that the orchestrator daemon
will use thereafter.

Usage:
    python -m social.scripts.login_persona <persona_id>

Example:
    python -m social.scripts.login_persona anton_kh
"""

from __future__ import annotations

import os
import sys
from getpass import getpass
from pathlib import Path

from dotenv import load_dotenv
from telethon.sync import TelegramClient
from telethon.errors import (
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
)

from social.personas import load_personas

_ENV_PATH = Path(__file__).parent.parent / "config" / "api_credentials.env"
load_dotenv(_ENV_PATH)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m social.scripts.login_persona <persona_id>")
        return 2
    persona_id = argv[1]

    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    if not api_id or not api_hash:
        print("ERROR: TELEGRAM_API_ID / TELEGRAM_API_HASH not set in env file.")
        return 1

    personas = load_personas(require_sessions=False)
    if persona_id not in personas:
        print(f"ERROR: unknown persona '{persona_id}'. Known: {list(personas)}")
        return 1
    persona = personas[persona_id]
    session_path = persona.resolved_session_path()
    session_path.parent.mkdir(parents=True, exist_ok=True)
    stem = str(session_path.with_suffix(""))

    print(f"Logging in persona '{persona_id}' -> {session_path}")
    phone = input(
        f"Phone number for {persona.name} (e.g. +380501234567): "
    ).strip()

    client = TelegramClient(stem, int(api_id), api_hash)
    client.connect()

    if client.is_user_authorized():
        print(f"Already authorized. Session: {session_path}")
        client.disconnect()
        return 0

    try:
        client.send_code_request(phone)
    except Exception as exc:
        print(f"ERROR sending code: {exc}")
        client.disconnect()
        return 1

    while True:
        code = input("Enter the code Telegram sent: ").strip()
        try:
            client.sign_in(phone, code)
            break
        except SessionPasswordNeededError:
            password = getpass("2FA password: ")
            client.sign_in(password=password)
            break
        except PhoneCodeInvalidError:
            print("Invalid code. Try again.")
            continue
        except Exception as exc:
            print(f"ERROR: {exc}")
            client.disconnect()
            return 1

    me = client.get_me()
    print(
        f"OK. Logged in as @{me.username or me.first_name} (id={me.id}). "
        f"Session written: {session_path}"
    )
    client.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
