from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Awaitable, Callable, Dict, List, Optional

from src.common.redis import RedisManager, StreamMessage
from src.engine.core.order_book import OrderBook

logger = logging.getLogger(__name__)


class OrderBookManager:
    """Coordinates order book updates from Redis and periodic reconciliation."""

    def __init__(
        self,
        redis_manager: RedisManager,
        order_book: OrderBook,
        group_events_channel: str,
        reconciliation_interval_seconds: int,
        stale_order_seconds: int,
        executed_trades_cache_key: str,
        event_listeners: Optional[List[Callable[[Dict[str, Any]], Awaitable[None] | None]]] = None,
    ) -> None:
        self._redis = redis_manager
        self._order_book = order_book
        self._channel = group_events_channel
        self._reconcile_interval = max(1, reconciliation_interval_seconds)
        self._stale_order_seconds = max(0, stale_order_seconds)
        self._stop_event = asyncio.Event()
        self._tasks: list[asyncio.Task] = []
        self._event_listeners: List[Callable[[Dict[str, Any]], Awaitable[None] | None]] = event_listeners or []
        self._executed_cache_key = executed_trades_cache_key
        self._group_name = "order_book"
        self._consumer_name = f"order-book-{uuid.uuid4().hex}"

    async def run(self) -> None:
        """Run the consumer and reconciliation loops until cancelled."""
        consumer = asyncio.create_task(self._consume_group_events(), name="order-book-consumer")
        reconciler = asyncio.create_task(self._reconciliation_loop(), name="order-book-reconciler")
        self._tasks = [consumer, reconciler]

        try:
            await asyncio.gather(*self._tasks)
        finally:
            await self.shutdown()

    def stop(self) -> None:
        """Signal background tasks to stop."""
        self._stop_event.set()

    async def shutdown(self) -> None:
        if not self._tasks:
            return

        for task in self._tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def _consume_group_events(self) -> None:
        logger.info("Reading stream %s for order book updates", self._channel)
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
            logger.debug("Order book consumer cancelled")
            raise

    async def _handle_stream_message(self, message: StreamMessage) -> None:
        payload = message.payload
        if await self._should_skip_event(payload):
            await message.ack()
            return
        self._order_book.apply_event(payload)
        await self._notify_listeners(payload)
        await message.ack()

    async def _reconciliation_loop(self) -> None:
        logger.info(
            "Starting reconciliation loop (interval=%ss, stale=%ss)",
            self._reconcile_interval,
            self._stale_order_seconds,
        )
        try:
            while not self._stop_event.is_set():
                await asyncio.sleep(self._reconcile_interval)
                if self._stop_event.is_set():
                    break
                removed = self._order_book.purge_stale(self._stale_order_seconds)
                summary = self._order_book.summary()
                logger.info(
                    "Order book summary: %s | stale removals=%s",
                    summary,
                    removed,
                )
        except asyncio.CancelledError:
            logger.debug("Reconciliation loop cancelled")
            raise

    def snapshot(self) -> Dict[str, Dict[int, Dict[str, Any]]]:
        """Return a copy of the current order book for inspection."""
        return self._order_book.snapshot()

    def summary(self) -> Dict[str, Any]:
        """Return lightweight counts for dashboards or logs."""
        return self._order_book.summary()

    async def _notify_listeners(self, event: Dict[str, Any]) -> None:
        for listener in self._event_listeners:
            try:
                result = listener(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.exception("Order book listener error: %s", exc)

    async def _should_skip_event(self, event: Dict[str, Any]) -> bool:
        message_meta = event.get("message") or {}
        message_id = message_meta.get("id")
        if message_id is None:
            return False

        try:
            member = str(message_id)
        except Exception:  # pragma: no cover - defensive conversion guard
            return False

        if await self._redis.is_member(self._executed_cache_key, member):
            logger.debug("Skipping message %s - already marked as executed", member)
            return True
        return False
