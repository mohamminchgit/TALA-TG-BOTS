from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Dict, Optional

from telethon.errors import FloodWaitError, MessageIdInvalidError, RPCError

logger = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover
    from src.bot_agent.agent import BotAgent


@dataclass
class CommandContext:
    trade_id: Optional[str]
    raw: Dict[str, Any]
    action: Optional[str]


class CommandExecutor:
    """Consumes execution commands from Redis and applies them via Telethon."""

    def __init__(
        self,
        agent: "BotAgent",
        redis_manager,
        channel: str,
        reconnect_delay: float = 1.0,
    ) -> None:
        self._agent = agent
        self._redis = redis_manager
        self._channel = channel
        self._reconnect_delay = reconnect_delay
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name=f"{self._agent.name}-command-consumer")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _run(self) -> None:
        logger.info("%s subscribing to %s", self._agent.alias, self._channel)
        while True:
            try:
                async for message in self._redis.subscribe(self._channel):
                    await self._handle_message(message)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - log & keep running
                logger.exception("Command executor error: %s", exc)
                await asyncio.sleep(self._reconnect_delay)

    async def _handle_message(self, message: str) -> None:
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            logger.warning("%s received invalid JSON: %s", self._agent.alias, message)
            return

        target = payload.get("target_bot")
        if target and target != self._agent.name:
            logger.debug("%s ignoring command for %s", self._agent.alias, target)
            return

        action = payload.get("action")
        context = CommandContext(trade_id=payload.get("trade_id"), raw=payload, action=action)
        
        logger.info("🎯 %s received command: action=%s, trade_id=%s", self._agent.alias, action, context.trade_id)

        handlers: Dict[str, Callable[[Dict[str, Any], CommandContext], Awaitable[None]]] = {
            "reply": self._handle_reply,
            "post_new_order": self._handle_post,
            "cancel_own_order": self._handle_cancel,
            "update_settings": self._handle_update_settings,
        }

        handler = handlers.get(action)
        if not handler:
            logger.warning("%s received unknown command action: %s", self._agent.alias, action)
            return

        try:
            await handler(payload, context)
        except FloodWaitError as exc:
            await self._agent.emit_execution_result(
                status="flood_wait",
                context=context,
                details={"wait_seconds": exc.seconds},
            )
        except RPCError as exc:
            await self._agent.emit_execution_result(
                status="rpc_error",
                context=context,
                details={"error": exc.__class__.__name__, "message": str(exc)},
            )
        except Exception as exc:  # pragma: no cover - catch-all logging
            logger.exception("%s command failed: %s", self._agent.alias, exc)
            await self._agent.emit_execution_result(
                status="error",
                context=context,
                details={"message": str(exc)},
            )

    async def _handle_reply(self, payload: Dict[str, Any], context: CommandContext) -> None:
        quantity = payload.get("quantity")
        message_id = payload.get("message_id")
        reply_text = payload.get("text")

        if quantity is not None and reply_text:
            reply_text = f"{reply_text} {quantity}".strip()
        elif quantity is not None:
            reply_text = str(quantity)
        elif reply_text is None:
            reply_text = "ب"

        await self._agent.client.send_message(
            entity=self._agent.group_entity,
            message=reply_text,
            reply_to=message_id,
        )

        await self._agent.emit_execution_result(
            status="success",
            context=context,
            details={"text": reply_text, "message_id": message_id},
        )
        await self._agent.confirmation_monitor.track(
            context,
            metadata={
                "action": context.action or "reply",
                "message_id": message_id,
                "reply_text": reply_text,
            },
        )

    async def _handle_post(self, payload: Dict[str, Any], context: CommandContext) -> None:
        message_text = payload.get("text")
        if not message_text:
            raise ValueError("post_new_order requires 'text'")

        sent = await self._agent.client.send_message(self._agent.group_entity, message_text)
        await self._agent.emit_execution_result(
            status="success",
            context=context,
            details={"sent_message_id": sent.id, "text": message_text},
        )
        await self._agent.confirmation_monitor.track(
            context,
            metadata={
                "action": context.action or "post_new_order",
                "sent_message_id": sent.id,
            },
        )

    async def _handle_cancel(self, payload: Dict[str, Any], context: CommandContext) -> None:
        message_id = payload.get("message_id")
        if not message_id:
            raise ValueError("cancel_own_order requires 'message_id'")

        metadata = payload.get("metadata") or {}
        reply_to_id = metadata.get("reply_to_message_id") or payload.get("reply_to_message_id") or message_id
        send_ack = metadata.get("send_cancellation_ack", True)

        ack_sent = False
        acknowledgement_error: Optional[str] = None
        if reply_to_id and send_ack:
            delay = max(0, self._agent.cancel_ack_delay_seconds)
            if delay:
                await asyncio.sleep(delay)
            try:
                await self._agent.client.send_message(
                    entity=self._agent.group_entity,
                    message="ن",
                    reply_to=reply_to_id,
                )
                ack_sent = True
            except Exception as exc:  # pragma: no cover - defensive logging
                acknowledgement_error = str(exc)
                logger.warning("%s failed to send cancellation ack for %s: %s", self._agent.alias, reply_to_id, exc)
        elif not reply_to_id:
            acknowledgement_error = "reply_target_missing"
            logger.warning("%s missing reply_to target for cancellation of %s", self._agent.alias, message_id)

        already_missing = False
        try:
            await self._agent.client.delete_messages(self._agent.group_entity, [message_id])
        except MessageIdInvalidError:
            already_missing = True
            logger.warning("%s attempted to delete missing message %s", self._agent.alias, message_id)

        await self._agent.emit_execution_result(
            status="success",
            context=context,
            details={
                "deleted_message_id": message_id,
                "already_deleted": already_missing,
                "reply_to_message_id": reply_to_id,
                "ack_sent": ack_sent,
                "ack_error": acknowledgement_error,
            },
        )

    async def _handle_update_settings(self, payload: Dict[str, Any], context: CommandContext) -> None:
        settings = payload.get("settings") or {}
        updated: Dict[str, Any] = {}

        if "cancel_ack_delay_seconds" in settings:
            try:
                delay = int(settings["cancel_ack_delay_seconds"])
            except (TypeError, ValueError):
                raise ValueError("cancel_ack_delay_seconds must be an integer")
            self._agent.update_cancel_ack_delay(delay)
            updated["cancel_ack_delay_seconds"] = self._agent.cancel_ack_delay_seconds

        await self._agent.emit_execution_result(
            status="success",
            context=context,
            details={"updated": updated, "settings": settings},
        )