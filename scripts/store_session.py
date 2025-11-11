#!/usr/bin/env python3
"""Interactively log in to Telegram and persist the resulting session string."""
from __future__ import annotations

import asyncio
import getpass
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.common.db import DatabaseManager
from src.common.session_onboarding import OnboardingConfig, SessionOnboarding
from src.common.session_store import SessionStore
from src.config.settings import get_settings


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

    database = DatabaseManager(settings.database.url)
    database.initialize_schema()
    store = SessionStore(database)
    onboarding = SessionOnboarding(
        api_id=settings.telegram.api_id,
        api_hash=settings.telegram.api_hash,
        session_store=store,
    )

    config = OnboardingConfig(
        session_key=session_key,
        bot_role="source" if session_key.startswith("source") else "destination" if session_key.startswith("destination") else session_key,
        phone_number=phone_number,
        phone_password=phone_password,
    )
    print(f"🤖 شروع فرآیند ورود برای {config.bot_role} ({phone_number})")

    async def prompt_code(role: str, phone: str) -> str:
        code = input(f"کد ارسال‌شده برای {role} ({phone}) را وارد کن: ").strip().replace(" ", "")
        return code

    async def prompt_password(role: str) -> Optional[str]:
        password = getpass.getpass("گذرواژه دو مرحله‌ای (در صورت وجود) را وارد کن: ")
        return password or None

    async def notify_flood(role: str, seconds: int) -> None:
        if seconds <= 0:
            print("❌ کد اشتباه بود. دوباره تلاش کن.")
        else:
            minutes = seconds // 60
            remaining = seconds % 60
            print(f"⏳ FloodWait برای {role}: لطفاً {minutes} دقیقه و {remaining} ثانیه منتظر بمان و سپس دوباره تلاش کن.")

    await onboarding.ensure_session(
        config,
        prompt_code=prompt_code,
        prompt_password=prompt_password,
        notify_flood_wait=notify_flood,
    )
    print(f"🎉 جلسه با موفقیت برای کلید {session_key} ذخیره شد.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹️ فرآیند توسط کاربر متوقف شد.")
