from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from src.bot_agent.agent import BotAgent
    from src.bot_agent.services.command_executor import CommandContext
    from src.bot_agent.handlers.message_handler import ClassifiedMessage


logger = logging.getLogger(__name__)


@dataclass
class PendingConfirmation:
    context: "CommandContext"
    action: Optional[str]
    metadata: Dict[str, Any]
    started_at: float = field(default_factory=time.monotonic)
    timer: Optional[asyncio.Task] = None


class ConfirmationMonitor:
    """Tracks command executions and waits for trade confirmations or timeouts."""

    def __init__(self, agent: "BotAgent", timeout_seconds: int) -> None:
        self._agent = agent
        self._timeout = max(0, timeout_seconds)
        self._pending: "OrderedDict[str, PendingConfirmation]" = OrderedDict()
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return self._timeout > 0

    async def track(self, context: "CommandContext", metadata: Optional[Dict[str, Any]] = None) -> None:
        if not self.enabled:
            return
        if not context.trade_id:
            logger.debug("%s skipping confirmation tracking (no trade_id)", self._agent.alias)
            return

        async with self._lock:
            existing = self._pending.get(context.trade_id)
            if existing and existing.timer:
                existing.timer.cancel()

            pending = PendingConfirmation(context=context, action=context.action, metadata=metadata or {})
            pending.timer = asyncio.create_task(self._timeout_after(context.trade_id), name=f"{self._agent.name}-confirm-{context.trade_id}")
            self._pending[context.trade_id] = pending
            logger.info(
                "%s tracking confirmation for trade %s (timeout=%ss)",
                self._agent.alias,
                context.trade_id,
                self._timeout,
            )

    async def observe_classification(
        self,
        classification: "ClassifiedMessage",
        payload: Dict[str, Any],
    ) -> None:
        if classification.category != "trade_confirmation":
            return

        details = dict(classification.details or {})
        confirmation_message_id = (payload.get("message") or {}).get("id")
        if confirmation_message_id is not None:
            details["confirmation_message_id"] = confirmation_message_id
        details["raw_text"] = payload.get("text")

        trade_id_hint = details.get("trade_id") or payload.get("details", {}).get("trade_id")
        trade_id, pending = await self._pop_pending(trade_id_hint)
        if not pending:
            logger.info(
                "%s observed trade confirmation with no pending commands: %s",
                self._agent.alias,
                details,
            )
            return

        elapsed = time.monotonic() - pending.started_at
        merged_details = {
            **pending.metadata,
            **details,
            "elapsed_seconds": round(elapsed, 2),
            "confirmation_timeout_seconds": self._timeout,
        }

        await self._agent.emit_execution_result(
            status="confirmation_detected",
            context=pending.context,
            details=merged_details,
        )
        logger.info(
            "%s confirmation received for trade %s in %.2fs",
            self._agent.alias,
            trade_id,
            elapsed,
        )

    async def _timeout_after(self, trade_id: str) -> None:
        try:
            await asyncio.sleep(self._timeout)
        except asyncio.CancelledError:
            raise

        trade_id, pending = await self._pop_pending(trade_id)
        if not pending:
            return

        elapsed = time.monotonic() - pending.started_at
        details = {
            **pending.metadata,
            "elapsed_seconds": round(elapsed, 2),
            "confirmation_timeout_seconds": self._timeout,
        }
        await self._agent.emit_execution_result(
            status="confirmation_timeout",
            context=pending.context,
            details=details,
        )
        logger.warning(
            "%s confirmation timeout for trade %s after %.2fs",
            self._agent.alias,
            trade_id,
            elapsed,
        )

    async def _pop_pending(self, trade_id: Optional[str]) -> tuple[Optional[str], Optional[PendingConfirmation]]:
        async with self._lock:
            if trade_id and trade_id in self._pending:
                pending = self._pending.pop(trade_id)
                selected_id = trade_id
            elif self._pending:
                selected_id, pending = self._pending.popitem(last=False)
            else:
                return None, None

        if pending.timer:
            current_task = asyncio.current_task()
            if pending.timer is current_task:
                pending.timer = None
            else:
                pending.timer.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await pending.timer

        return selected_id, pending

    async def shutdown(self) -> None:
        async with self._lock:
            pending_items = list(self._pending.items())
            self._pending.clear()

        for trade_id, pending in pending_items:
            if pending.timer:
                current_task = asyncio.current_task()
                if pending.timer is not current_task:
                    pending.timer.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await pending.timer
            logger.debug("%s cancelling pending confirmation for trade %s", self._agent.alias, trade_id)