from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from telethon import events

from src.bot_agent.handlers.message_handler import ClassifiedMessage, handle_group_message
from src.bot_agent.services.telegram_service import TelegramService
from src.bot_agent.services.command_executor import CommandContext, CommandExecutor
from src.bot_agent.services.confirmation_monitor import ConfirmationMonitor
from src.config.settings import BotConfig, TelegramCredentials
from src.common.redis import RedisManager
from src.common.session_store import SessionStore
from src.common.utils import normalize_persian_numbers, utc_now

logger = logging.getLogger(__name__)


@dataclass
class AgentStatus:
    alias: str
    group: Any
    is_running: bool


class BotAgent:
    """Represents a userbot connected to a single Telegram trading group."""

    def __init__(
        self,
        name: str,
        config: BotConfig,
        credentials: TelegramCredentials,
        redis_manager: RedisManager,
        session_store: SessionStore,
    ) -> None:
        self.name = name
        self.config = config
        self.alias = config.alias
        self._credentials = credentials
        self._telegram = TelegramService(session_store, config.session_key, credentials.api_id, credentials.api_hash)
        self._group_filter = self._coerce_group_id(config.group_id)
        self._ready_event = asyncio.Event()
        self._redis = redis_manager
        self._command_executor: Optional[CommandExecutor] = None
        self._confirmation_monitor = ConfirmationMonitor(self, config.confirmation_timeout_seconds)
        self._cancel_ack_delay_seconds = max(0, config.cancel_ack_delay_seconds)
        self._alias_normalized = normalize_persian_numbers(self.alias).strip().lower()

    @staticmethod
    def _coerce_group_id(raw_value: str) -> Any:
        value = raw_value.strip()
        try:
            return int(value)
        except ValueError:
            return value

    async def start(self) -> None:
        logger.info("Starting %s (%s) for group %s", self.name, self.alias, self.config.group_id)
        await self._telegram.connect(self.config.phone_number, self.config.phone_password)

        async def _handler(event: events.NewMessage.Event) -> None:
            await handle_group_message(self, event)

        self._telegram.add_message_handler(_handler, chats=[self._group_filter])

        async def _deleted_handler(event: events.MessageDeleted.Event) -> None:
            await self._handle_deleted_messages(event)

        self._telegram.add_deleted_handler(_deleted_handler, chats=[self._group_filter])
        self._command_executor = CommandExecutor(
            agent=self,
            redis_manager=self._redis,
            channel=self._redis.channels.execution_commands,
        )
        await self._command_executor.start()
        self._ready_event.set()
        logger.info("%s connected and listening", self.alias)

    async def run(self) -> None:
        await self._ready_event.wait()
        await self._telegram.run_until_disconnected()

    async def wait_until_ready(self) -> None:
        await self._ready_event.wait()

    def status(self) -> AgentStatus:
        return AgentStatus(alias=self.alias, group=self.config.group_id, is_running=self._ready_event.is_set())

    @property
    def client(self):
        return self._telegram.client

    @property
    def group_entity(self) -> Any:
        return self._group_filter

    @property
    def confirmation_monitor(self) -> ConfirmationMonitor:
        return self._confirmation_monitor

    @property
    def cancel_ack_delay_seconds(self) -> int:
        return self._cancel_ack_delay_seconds

    def update_cancel_ack_delay(self, seconds: int) -> None:
        self._cancel_ack_delay_seconds = max(0, int(seconds))
        logger.info("%s updated cancel ack delay to %ss", self.alias, self._cancel_ack_delay_seconds)

    async def process_classified_message(
        self,
        event: events.NewMessage.Event,
        classification: ClassifiedMessage,
    ) -> None:
        message = event.message
        sender = await event.get_sender()
        first_name = getattr(sender, "first_name", None) or "" if sender else ""
        last_name = getattr(sender, "last_name", None) or "" if sender else ""
        display_name_raw = (f"{first_name} {last_name}" if first_name or last_name else "").strip()
        if not display_name_raw:
            display_name_raw = getattr(sender, "username", "") if sender else ""
        if not display_name_raw:
            display_name_raw = "Unknown"

        details_dict = dict(classification.details or {})
        payload = {
            "agent": self.name,
            "alias": self.alias,
            "group_id": self.config.group_id,
            "group_label": self.name,
            "category": classification.category,
            "text": classification.original_text,
            "normalized_text": classification.normalized_text,
            "details": details_dict,
            "message": {
                "id": getattr(message, "id", None),
                "chat_id": event.chat_id,
                "reply_to": getattr(message, "reply_to_msg_id", None),
                "date": getattr(message, "date", None).isoformat() if getattr(message, "date", None) else None,
            },
            "sender": {
                "id": getattr(sender, "id", None) if sender else None,
                "username": getattr(sender, "username", None) if sender else None,
                "display_name": normalize_persian_numbers(display_name_raw),
            },
        }

        classification.details = details_dict

        alias_value = details_dict.get("alias")
        if alias_value:
            alias_normalized = normalize_persian_numbers(alias_value).strip().lower()
            details_dict.setdefault("alias_normalized", alias_normalized)
            if alias_normalized == self._alias_normalized and classification.category in {"buy_order", "sell_order"}:
                details_dict["is_self_order_confirmation"] = True

        await self._redis.publish_json(self._redis.channels.group_events, payload)
        logger.info(
            "%s published %s event for message %s", self.alias, classification.category, payload["message"]["id"]
        )

        await self._confirmation_monitor.observe_classification(classification, payload)

    async def _handle_deleted_messages(self, event: events.MessageDeleted.Event) -> None:
        raw_ids = list(getattr(event, "deleted_ids", []))
        normalized_ids: list[int] = []
        for raw_id in raw_ids:
            try:
                normalized_ids.append(int(raw_id))
            except (TypeError, ValueError):
                logger.debug("%s ignored non-integer deleted id %s", self.alias, raw_id)
        if not normalized_ids:
            return

        payload = {
            "agent": self.name,
            "alias": self.alias,
            "group_id": self.config.group_id,
            "group_label": self.name,
            "category": "message_deleted",
            "details": {"message_ids": normalized_ids},
            "message": {
                "chat_id": event.chat_id,
            },
        }

        await self._redis.publish_json(self._redis.channels.group_events, payload)
        logger.info("%s observed deletion for messages %s", self.alias, normalized_ids)

    async def emit_execution_result(
        self,
        status: str,
        context: CommandContext,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        payload = {
            "timestamp": utc_now().isoformat(),
            "agent": self.name,
            "alias": self.alias,
            "group_id": self.config.group_id,
            "status": status,
            "trade_id": context.trade_id,
            "action": context.action,
            "command": context.raw,
            "details": details or {},
        }
        await self._redis.publish_json(self._redis.channels.execution_results, payload)
        logger.info("%s reported %s for trade %s", self.alias, status, context.trade_id)
