from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional

from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession

from src.common.session_store import SessionStore

logger = logging.getLogger(__name__)


class TelegramService:
    """Wrapper around Telethon client with convenience helpers."""

    def __init__(self, session_store: SessionStore, session_key: str, api_id: int, api_hash: str) -> None:
        self._session_store = session_store
        self._session_key = session_key
        session_string = self._session_store.load(session_key)
        self._client = TelegramClient(StringSession(session_string), api_id, api_hash)

    @property
    def client(self) -> TelegramClient:
        return self._client

    async def connect(self, phone_number: Optional[str], phone_password: Optional[str]) -> None:
        await self._client.connect()
        if await self._client.is_user_authorized():
            await self._persist_session()
            logger.info("Telethon session %s loaded successfully", self._session_key)
            return

        if not phone_number:
            raise RuntimeError(
                "Session not authorized and no phone number provided. "
                "Set SOURCE_PHONE_NUMBER/DESTINATION_PHONE_NUMBER in the environment or "
                "generate a session string using scripts/generate_session.py."
            )

        logger.info("Authorizing Telegram session for %s", phone_number)
        try:
            await self._client.start(phone=phone_number, password=phone_password)
        except SessionPasswordNeededError:
            raise RuntimeError(
                "Two-factor authentication is enabled but SOURCE_PHONE_PASSWORD/DESTINATION_PHONE_PASSWORD "
                "is not configured. Provide the password or generate the session manually."
            ) from None
        await self._persist_session()

    async def run_until_disconnected(self) -> None:
        try:
            await self._client.run_until_disconnected()
        finally:
            await self._persist_session()

    async def _persist_session(self) -> None:
        session_data = self._client.session.save()
        if session_data:
            await asyncio.to_thread(self._session_store.save, self._session_key, session_data)

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
