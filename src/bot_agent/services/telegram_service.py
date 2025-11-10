from __future__ import annotations

import logging
from pathlib import Path
from typing import Awaitable, Callable, Optional

from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError

logger = logging.getLogger(__name__)


class TelegramService:
    """Wrapper around Telethon client with convenience helpers."""

    def __init__(self, session_path: Path, api_id: int, api_hash: str) -> None:
        self._client = TelegramClient(str(session_path), api_id, api_hash)

    @property
    def client(self) -> TelegramClient:
        return self._client

    async def connect(self, phone_number: Optional[str], phone_password: Optional[str]) -> None:
        await self._client.connect()
        if await self._client.is_user_authorized():
            logger.info("Telethon session %s loaded successfully", self._client.session.filename)
            return

        if not phone_number:
            raise RuntimeError(
                "Session not authorized and no phone number provided. "
                "Set SOURCE_PHONE_NUMBER/DESTINATION_PHONE_NUMBER in the environment or "
                "generate a session file using scripts/generate_session.py."
            )

        logger.info("Authorizing Telegram session for %s", phone_number)
        try:
            await self._client.start(phone=phone_number, password=phone_password)
        except SessionPasswordNeededError:
            raise RuntimeError(
                "Two-factor authentication is enabled but SOURCE_PHONE_PASSWORD/DESTINATION_PHONE_PASSWORD "
                "is not configured. Provide the password or generate the session manually."
            ) from None

    async def run_until_disconnected(self) -> None:
        await self._client.run_until_disconnected()

    def add_message_handler(
        self,
        handler: Callable[[events.NewMessage.Event], Awaitable[None]],
        chats: Optional[list[int | str]] = None,
    ) -> None:
        chats = chats or []

        @self._client.on(events.NewMessage(chats=chats or None))
        async def wrapped(event: events.NewMessage.Event) -> None:  # type: ignore[misc]
            await handler(event)

        logger.debug("Registered new message handler for chats: %s", chats if chats else "all")

    def add_deleted_handler(
        self,
        handler: Callable[[events.MessageDeleted.Event], Awaitable[None]],
        chats: Optional[list[int | str]] = None,
    ) -> None:
        chats = chats or []

        @self._client.on(events.MessageDeleted(chats=chats or None))
        async def wrapped(event: events.MessageDeleted.Event) -> None:  # type: ignore[misc]
            await handler(event)

        logger.debug("Registered message deleted handler for chats: %s", chats if chats else "all")
