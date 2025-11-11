"""Helper script to generate a Telethon session string for manual usage."""
from __future__ import annotations

import getpass
import sys
from pathlib import Path

from telethon import TelegramClient
from telethon.sessions import StringSession

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config.settings import get_settings  # noqa: E402


def main() -> None:
    settings = get_settings(env_path=PROJECT_ROOT / ".env")
    api_id = settings.telegram.api_id
    api_hash = settings.telegram.api_hash

    default_phone = settings.source_bot.phone_number or settings.destination_bot.phone_number or ""
    prompt = f"Enter phone number (international format){f' [{default_phone}]' if default_phone else ''}: "
    phone = input(prompt).strip() or default_phone
    if not phone:
        raise SystemExit("Phone number is required to generate a session.")

    password = getpass.getpass("2FA password (leave empty if not enabled): ") or None

    with TelegramClient(StringSession(), api_id, api_hash) as client:
        client.start(phone=phone, password=password)
        session_string = client.session.save()
        print("\nCopy the session string, store it securely, and keep it outside of version control.\n")
        print(session_string)


if __name__ == "__main__":
    main()
