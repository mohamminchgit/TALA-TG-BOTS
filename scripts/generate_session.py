"""Helper script to generate a Telethon session string for .env usage."""

import getpass

from telethon.sync import TelegramClient
from telethon.sessions import StringSession


def main() -> None:
    api_id = int(input("Enter TELEGRAM_API_ID: ").strip())
    api_hash = input("Enter TELEGRAM_API_HASH: ").strip()
    phone = input("Enter phone number (international format): ").strip()

    password = getpass.getpass("2FA password (leave empty if not enabled): ") or None

    with TelegramClient(StringSession(), api_id, api_hash) as client:
        client.start(phone=phone, password=password)
        session_string = client.session.save()
        print("\nCopy the session string and store it securely (e.g., in the .env file)\n")
        print(session_string)


if __name__ == "__main__":
    main()
