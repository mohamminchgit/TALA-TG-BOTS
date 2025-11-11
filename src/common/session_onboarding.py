from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Optional

from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PasswordHashInvalidError,
    SessionPasswordNeededError,
)
from telethon.sessions import StringSession

from src.common.session_store import SessionStore


CodePromptFn = Callable[[str, str], Awaitable[str]]
PasswordPromptFn = Callable[[str], Awaitable[Optional[str]]]
FloodWaitNotifyFn = Callable[[str, int], Awaitable[None]]


@dataclass
class OnboardingConfig:
    session_key: str
    bot_role: str
    phone_number: str
    phone_password: Optional[str]


class SessionOnboarding:
    """Reusable flow for acquiring Telethon sessions."""

    def __init__(self, *, api_id: int, api_hash: str, session_store: SessionStore) -> None:
        self._api_id = api_id
        self._api_hash = api_hash
        self._store = session_store

    async def ensure_session(
        self,
        config: OnboardingConfig,
        *,
        prompt_code: CodePromptFn,
        prompt_password: PasswordPromptFn,
        notify_flood_wait: FloodWaitNotifyFn,
    ) -> None:
        client = TelegramClient(StringSession(), self._api_id, self._api_hash)
        await client.connect()
        try:
            if await client.is_user_authorized():
                session_string = client.session.save()
                self._store.save(
                    config.session_key,
                    session_string,
                    phone_number=config.phone_number,
                    bot_role=config.bot_role,
                )
                return

            await self._send_code_with_retry(config, client, notify_flood_wait)

            while True:
                code = await prompt_code(config.bot_role, config.phone_number)
                if not code:
                    continue
                try:
                    await client.sign_in(phone=config.phone_number, code=code)
                    break
                except PhoneCodeInvalidError:
                    await notify_flood_wait(
                        config.bot_role,
                        0,
                    )
                except PhoneCodeExpiredError:
                    await self._send_code_with_retry(config, client, notify_flood_wait)

            session_password = config.phone_password
            if not await client.is_user_authorized():
                if session_password is None:
                    session_password = await prompt_password(config.bot_role)
                try:
                    await client.start(phone=config.phone_number, password=session_password)
                except SessionPasswordNeededError:
                    session_password = await prompt_password(config.bot_role)
                    await client.start(phone=config.phone_number, password=session_password)
                except PasswordHashInvalidError:
                    session_password = await prompt_password(config.bot_role)
                    await client.start(phone=config.phone_number, password=session_password)

            session_string = client.session.save()
            self._store.save(
                config.session_key,
                session_string,
                phone_number=config.phone_number,
                bot_role=config.bot_role,
            )
        finally:
            await client.disconnect()

    async def _send_code_with_retry(
        self,
        config: OnboardingConfig,
        client: TelegramClient,
        notify_flood_wait: FloodWaitNotifyFn,
    ) -> None:
        try:
            await client.send_code_request(config.phone_number)
        except FloodWaitError as exc:
            seconds = max(0, int(exc.seconds))
            await notify_flood_wait(config.bot_role, seconds)
            self._store.update_flood_wait(config.session_key, seconds, error="FloodWait during send_code_request")
            await asyncio.sleep(seconds)
            await client.send_code_request(config.phone_number)

