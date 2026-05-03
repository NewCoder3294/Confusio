"""Non-interactive Telethon login that waits on file signals.

Used when the agent driving setup can't pipe stdin into the login script
(e.g. running under a tool harness). The user supplies the phone via env
var; the SMS code (and optional 2FA password) arrive via files in /tmp.

Flow:
    PHONE=+15551234567 .venv/bin/python -m social.scripts.await_login anton_kh

Then write the SMS code to /tmp/mendacity_code (newline-terminated). If
2FA is enabled you'll see "WAITING FOR 2FA" — write the password to
/tmp/mendacity_2fa.

The script prints status lines prefixed with `[await]` so a watcher can
trigger on them.
"""

from __future__ import annotations

import os
import sys
import time
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

CODE_FILE = Path("/tmp/mendacity_code")
TFA_FILE = Path("/tmp/mendacity_2fa")
POLL_TIMEOUT_SECONDS = 600  # 10 min


def _wait_for_file(path: Path, label: str) -> str:
    print(f"[await] WAITING FOR {label} at {path}", flush=True)
    deadline = time.time() + POLL_TIMEOUT_SECONDS
    while time.time() < deadline:
        if path.exists():
            value = path.read_text(encoding="utf-8").strip()
            if value:
                path.unlink(missing_ok=True)
                return value
        time.sleep(0.5)
    print(f"[await] TIMEOUT waiting for {label}", flush=True)
    sys.exit(2)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: PHONE=+1... python -m social.scripts.await_login <persona_id>")
        return 2
    persona_id = argv[1]
    phone = os.environ.get("PHONE", "").strip()
    if not phone:
        print("[await] ERROR: PHONE env var not set")
        return 1

    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    if not api_id or not api_hash:
        print("[await] ERROR: TG creds missing in env file")
        return 1

    personas = load_personas(require_sessions=False)
    if persona_id not in personas:
        print(f"[await] ERROR: unknown persona {persona_id}. Known: {list(personas)}")
        return 1
    persona = personas[persona_id]
    session_path = persona.resolved_session_path()
    session_path.parent.mkdir(parents=True, exist_ok=True)
    # Wipe any stub session so we get a clean auth.
    if session_path.exists() and session_path.stat().st_size <= 32768:
        # Heuristic: stubs from import-time PersonaTelegramClient are tiny.
        try:
            session_path.unlink()
            print(f"[await] cleared stub session {session_path}")
        except OSError:
            pass
    stem = str(session_path.with_suffix(""))

    # Clear stale signal files.
    CODE_FILE.unlink(missing_ok=True)
    TFA_FILE.unlink(missing_ok=True)

    print(f"[await] persona={persona_id} phone={phone[:3]}***{phone[-2:]}")
    client = TelegramClient(stem, int(api_id), api_hash)
    client.connect()

    if client.is_user_authorized():
        me = client.get_me()
        print(
            f"[await] ALREADY AUTHORIZED as @{me.username or me.first_name} "
            f"(id={me.id}). Session: {session_path}"
        )
        client.disconnect()
        return 0

    try:
        client.send_code_request(phone)
        print(f"[await] code request sent to {phone}")
    except Exception as exc:
        print(f"[await] ERROR sending code: {exc}")
        client.disconnect()
        return 1

    while True:
        code = _wait_for_file(CODE_FILE, "CODE")
        try:
            client.sign_in(phone, code)
            break
        except SessionPasswordNeededError:
            password = _wait_for_file(TFA_FILE, "2FA")
            try:
                client.sign_in(password=password)
                break
            except Exception as exc:
                print(f"[await] 2FA failed: {exc}")
                client.disconnect()
                return 1
        except PhoneCodeInvalidError:
            print("[await] invalid code, write a new one to the same file")
            continue
        except Exception as exc:
            print(f"[await] sign_in error: {exc}")
            client.disconnect()
            return 1

    me = client.get_me()
    print(
        f"[await] OK. Logged in as @{me.username or me.first_name} (id={me.id}). "
        f"Session written: {session_path}"
    )
    client.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
