from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Awaitable, Callable, Dict, List, Optional

from src.common.db import DatabaseManager
from src.common.redis import RedisManager, StreamMessage
from src.engine.core.trade_tracker import TradeContext, TradeTracker

logger = logging.getLogger(__name__)


class ExecutionResultProcessor:
    """Consumes execution results, persists trade records, and updates caches."""

    def __init__(
        self,
        redis_manager: RedisManager,
        channel: str,
        tracker: TradeTracker,
        database: DatabaseManager,
        executed_cache_key: str,
        executed_cache_ttl: int,
        listeners: Optional[List[Callable[[Dict[str, Any]], Awaitable[None] | None]]] = None,
        trade_observer: Optional[Callable[[TradeContext, str], Awaitable[None] | None]] = None,
    ) -> None:
        self._redis = redis_manager
        self._channel = channel
        self._tracker = tracker
        self._database = database
        self._executed_cache_key = executed_cache_key
        self._executed_cache_ttl = executed_cache_ttl
        self._stop_event = asyncio.Event()
        self._listeners = listeners or []
        self._trade_observer = trade_observer
        self._group_name = "execution_results"
        self._consumer_name = f"exec-results-{uuid.uuid4().hex}"

    def stop(self) -> None:
        self._stop_event.set()

    async def run(self) -> None:
        logger.info("Reading stream %s for execution results", self._channel)
        try:
            async for message in self._redis.consume_stream(
                self._channel,
                self._group_name,
                self._consumer_name,
                count=200,
            ):
                if self._stop_event.is_set():
                    break
                await self._handle_stream_message(message)
        except asyncio.CancelledError:
            logger.debug("Execution result processor cancelled")
            raise

    async def _handle_stream_message(self, message: StreamMessage) -> None:
        payload = message.payload
        await self._handle_result(payload)
        await message.ack()

    async def _handle_result(self, payload: Dict[str, Any]) -> None:
        for listener in self._listeners:
            try:
                maybe_coro = listener(payload)
                if asyncio.iscoroutine(maybe_coro):
                    await maybe_coro
            except Exception:  # pragma: no cover - defensive logging
                logger.exception("Execution result listener failed for payload: %s", payload)

        trade_id = payload.get("trade_id")
        status = payload.get("status")
        agent = payload.get("agent")
        if not trade_id or not status:
            logger.debug("Ignoring execution result missing trade_id/status: %s", payload)
            return

        command = payload.get("command") or {}
        metadata = command.get("metadata") or {}
        details = payload.get("details") or {}
        action = command.get("action") or payload.get("action")

        context = self._tracker.record_result(
            trade_id,
            agent,
            status,
            details=details,
            action=action,
            metadata=metadata,
        )
        if context is None:
            if self._tracker.get(trade_id) is None:
                logger.debug("Received result for unknown trade %s; payload=%s", trade_id, payload)
            else:
                logger.debug("Trade %s awaiting additional results", trade_id)
            return

        context = self._tracker.pop(trade_id) or context
        final_status = context.failure_status or status

        if self._trade_observer is not None:
            try:
                maybe_coro = self._trade_observer(context, final_status)
                if asyncio.iscoroutine(maybe_coro):
                    await maybe_coro
            except Exception:  # pragma: no cover - defensive logging
                logger.exception("Trade observer failed for trade %s", context.trade_id)

        if not context.failed and context.completed_agents >= context.expected_agents:
            await self._mark_as_executed(context)

        await self._persist_trade(context, final_status)
        logger.info("Recorded trade %s with status %s", trade_id, final_status)

    async def _mark_as_executed(self, context: TradeContext) -> None:
        message_ids: set[int] = set()
        if context.source_message_id is not None:
            message_ids.add(context.source_message_id)
        if context.destination_message_id is not None:
            message_ids.add(context.destination_message_id)
        message_ids.update(context.destination_message_ids.values())

        for message_id in message_ids:
            await self._redis.add_to_set(
                self._executed_cache_key,
                str(message_id),
                ttl_seconds=self._executed_cache_ttl,
            )
            logger.debug("Cached executed message %s for trade %s", message_id, context.trade_id)

    async def _persist_trade(self, context: TradeContext, status: str) -> None:
        source_price = context.source_price or 0
        total_profit = 0
        if context.destination_leg_prices:
            total_quantity = 0
            total_notional = 0
            for agent_key, price in context.destination_leg_prices.items():
                quantity = context.destination_leg_quantities.get(agent_key, 0)
                if quantity <= 0:
                    continue
                total_quantity += quantity
                total_notional += price * quantity
                total_profit += (price - source_price) * quantity
            if total_quantity > 0:
                context.destination_price = int(round(total_notional / total_quantity))
                context.quantity = total_quantity
        else:
            profit_per_unit = (context.destination_price or 0) - source_price
            total_profit = profit_per_unit * context.quantity
        await asyncio.to_thread(
            self._write_trade_record,
            context,
            status,
            float(total_profit),
        )

    def _write_trade_record(self, context: TradeContext, status: str, total_profit: float) -> None:
        payload = (
            context.trade_id,
            "predictive" if context.strategy == "predictive" else "immediate_arbitrage",
            context.source_message_id,
            context.destination_message_id,
            context.quantity,
            float(context.source_price or 0),
            float(context.destination_price or 0),
            total_profit,
            status,
        )

        with self._database.connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO trade_history (
                        trade_id,
                        strategy,
                        source_message_id,
                        destination_message_id,
                        quantity,
                        source_price,
                        destination_price,
                        profit,
                        status
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (trade_id) DO UPDATE SET
                        quantity = EXCLUDED.quantity,
                        source_price = EXCLUDED.source_price,
                        destination_price = EXCLUDED.destination_price,
                        profit = EXCLUDED.profit,
                        status = EXCLUDED.status,
                        executed_at = CURRENT_TIMESTAMP
                    """,
                    payload,
                )
                conn.commit()
