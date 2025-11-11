#!/usr/bin/env python3
"""Interactively log in to Telegram and persist the resulting session string."""
from __future__ import annotations

import asyncio
import getpass
import sys
from typing import Optional

from pathlib import Path

from telethon import TelegramClient
from telethon.errors import PhoneCodeInvalidError, PhoneCodeExpiredError, SessionPasswordNeededError
from telethon.sessions import StringSession

from src.common.db import DatabaseManager
from src.common.session_store import SessionStore
from src.config.settings import get_settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]


async def interactive_login(
    *,
    api_id: int,
    api_hash: str,
    phone_number: str,
    phone_password: Optional[str],
) -> str:
    """Drive a Telethon login flow and return the resulting session string."""
    print(f"🤖 در حال ورود برای شماره: {phone_number}")
    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.connect()

    try:
        if await client.is_user_authorized():
            print("ℹ️ جلسه قبلاً مجاز بود؛ نیازی به دریافت کد نیست.")
        else:
            send_code_result = await client.send_code_request(phone_number)
            print("📨 کد ورود برای ربات ارسال شد. لطفاً آن را وارد کنید.")
            if send_code_result.next_type is not None:
                print(f"⚠️ ارسال کد به صورت {send_code_result.next_type.__class__.__name__} است.")

            while True:
                code = input("کد ورود را وارد کن: ").strip().replace(" ", "")
                if not code:
                    print("کد نمی‌تواند خالی باشد. دوباره تلاش کن.")
                    continue
                try:
                    await client.sign_in(phone=phone_number, code=code)
                    break
                except PhoneCodeInvalidError:
                    print("❌ کد وارد شده اشتباه بود. دوباره ارسال کن.")
                except PhoneCodeExpiredError:
                    print("⌛ کد منقضی شده. دوباره تلاش می‌کنیم.")
                    send_code_result = await client.send_code_request(phone_number)
        if not await client.is_user_authorized():
            try:
                await client.start(phone=phone_number, password=phone_password)
            except SessionPasswordNeededError:
                if not phone_password:
                    password = getpass.getpass("گذرواژه دو مرحله‌ای تلگرام را وارد کن: ")
                else:
                    password = phone_password
                await client.start(phone=phone_number, password=password)
    finally:
        session_string = client.session.save()
        await client.disconnect()
    return session_string


def resolve_session_key(name_hint: str) -> str:
    mapping = {
        "source": "source_session",
        "destination": "destination_session",
        "admin": "admin_session",
    }
    normalized = name_hint.strip().lower()
    return mapping.get(normalized, normalized or "session")


async def main() -> None:
    settings = get_settings(env_path=PROJECT_ROOT / ".env")
    session_key_hint = input(
        "🔑 وارد کن که این جلسه برای کدام ربات است (مثلاً source یا destination): "
    )
    session_key = resolve_session_key(session_key_hint)
    print(f"✅ جلسه در ستون {session_key} ذخیره می‌شود.")

    target = None
    if session_key.startswith("source"):
        target = settings.source_bot
    elif session_key.startswith("destination"):
        target = settings.destination_bot

    if target is None:
        phone_number = input("شماره ربات را با فرمت بین‌المللی وارد کن: ").strip()
        phone_password = getpass.getpass("اگر گذرواژه دو مرحله‌ای داری وارد کن (خالی بگذار برای هیچ): ") or None
    else:
        phone_number = target.phone_number or input(
            "شماره در .env نبود؛ لطفاً شماره ربات را وارد کن: "
        ).strip()
        phone_password = target.phone_password or None

    if not phone_number:
        print("❌ شماره ربات لازم است. فرآیند متوقف شد.")
        sys.exit(1)

    session_string = await interactive_login(
        api_id=settings.telegram.api_id,
        api_hash=settings.telegram.api_hash,
        phone_number=phone_number,
        phone_password=phone_password,
    )

    database = DatabaseManager(settings.database.url)
    database.initialize_schema()
    SessionStore(database).save(session_key, session_string)
    print(f"🎉 جلسه با موفقیت برای کلید {session_key} ذخیره شد.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹️ فرآیند توسط کاربر متوقف شد.")
