from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from src.common.redis import RedisManager
from src.engine.core.order_book import OrderBook
from src.engine.core.engine_state import EngineState
from src.engine.core.trade_tracker import TradeContext, TradeTracker
from src.engine.core.trade_policy import TradeDirection, TradePolicy

logger = logging.getLogger(__name__)


@dataclass
class PendingPredictiveTrade:
    trade_id: str
    source_message_id: int
    source_price: int
    quantity: int
    destination_price: int
    direction: str
    expected_spread: int
    destination_message_id: Optional[int] = None
    destination_supervisor_message_id: Optional[int] = None
    source_supervisor_message_id: Optional[int] = None
    stage: str = "awaiting_post_ack"
    created_at: float = field(default_factory=time.time)
    timeout_task: Optional[asyncio.Task] = None
    context_registered: bool = False


class PredictiveMarketMaker:
    """Places speculative orders when immediate arbitrage is unavailable."""

    def __init__(
        self,
        order_book: OrderBook,
        redis_manager: RedisManager,
        trade_tracker: TradeTracker,
        engine_state: EngineState,
        execution_commands_channel: str,
        predictive_price_delta: int,
        predictive_suffix_digits: int,
        speculative_timeout_seconds: int,
        destination_alias: str,
        policy: TradePolicy,
    ) -> None:
        self._order_book = order_book
        self._redis = redis_manager
        self._tracker = trade_tracker
        self._engine_state = engine_state
        self._commands_channel = execution_commands_channel
        self._suffix_digits = max(1, predictive_suffix_digits)
        self._timeout_seconds = max(1, speculative_timeout_seconds)
        self._destination_alias = destination_alias.strip() or "ربات مقصد"
        self._policy = policy
        # Retain predictive_price_delta for backward compatibility with admin commands.
        self._price_delta_override = max(0, predictive_price_delta)
        self._pending: Dict[str, PendingPredictiveTrade] = {}
        self._source_index: Dict[int, str] = {}
        self._lock = asyncio.Lock()

    async def process_event(self, event: Dict[str, Any]) -> None:
        await self._check_source_orders()

        if event.get("group_label") != "source":
            return
        if event.get("category") not in {"sell_order", "buy_order"}:
            return

        if self._engine_state and not self._engine_state.can_trade():
            return

        message_meta = event.get("message") or {}
        message_id = message_meta.get("id")
        if message_id is None:
            return

        pending: Optional[PendingPredictiveTrade] = None
        command_payload: Optional[Dict[str, Any]] = None

        async with self._lock:
            if message_id in self._source_index:
                return

            entry = self._order_book.get_entry("source", message_id)
            if entry is None or entry.price is None or entry.remaining_quantity <= 0:
                return

            direction: TradeDirection = "source_sell" if entry.side == "sell" else "source_buy"
            target_price = self._policy.target_destination_price(direction, source_price=entry.price or 0)
            if target_price <= 0:
                return

            if not self._should_post_speculative(direction, entry.price or 0, target_price):
                logger.debug("Skipping predictive flow for message %s due to qualifying counter-order", message_id)
                return

            quantity_to_post = self._policy.allowed_quantity(entry.remaining_quantity, opportunistic=False)
            if quantity_to_post <= 0:
                return

            post_side = "sell" if direction == "source_sell" else "buy"
            text = self._format_order_text(post_side, quantity_to_post, target_price)
            expected_spread = (
                target_price - (entry.price or 0)
                if direction == "source_sell"
                else (entry.price or 0) - target_price
            )

            trade_id = self._generate_trade_id()
            pending = PendingPredictiveTrade(
                trade_id=trade_id,
                source_message_id=message_id,
                source_price=entry.price or 0,
                quantity=quantity_to_post,
                destination_price=target_price,
                direction=direction,
                expected_spread=expected_spread,
            )
            self._pending[trade_id] = pending
            self._source_index[message_id] = trade_id

            command_payload = {
                "target_bot": "destination",
                "action": "post_new_order",
                "text": text,
                "trade_id": trade_id,
                "metadata": {
                    "strategy": "predictive",
                    "source_message_id": message_id,
                    "direction": direction,
                    "destination_price": target_price,
                    "agent_key": "destination",
                    "policy_delta": self._policy.snapshot.fixed_spread_delta,
                },
            }

        if not pending or not command_payload:
            return

        await self._redis.publish_json(self._commands_channel, command_payload)
        logger.info(
            "Issued predictive trade %s for source message %s (direction=%s price=%s)",
            pending.trade_id,
            pending.source_message_id,
            pending.direction,
            pending.destination_price,
        )

        await self._save_state(pending)

    async def handle_execution_result(self, payload: Dict[str, Any]) -> None:
        trade_id = payload.get("trade_id")
        if not trade_id or not trade_id.startswith("pred-"):
            return

        async with self._lock:
            pending = self._pending.get(trade_id)
        if not pending:
            return

        status = payload.get("status")
        agent = payload.get("agent")
        details = payload.get("details") or {}
        action = (payload.get("command") or {}).get("action") or payload.get("action")

        if status == "success" and agent == "destination" and action == "post_new_order":
            message_id = details.get("sent_message_id") or details.get("message_id")
            if message_id:
                pending.destination_message_id = int(message_id)
                pending.stage = "awaiting_fill"
                self._tracker.update_destination_message(trade_id, int(message_id))
                await self._save_state(pending)
                await self._schedule_timeout(pending)
            return

        if status == "confirmation_detected" and agent == "destination":
            await self._advance_to_source_execution(pending, details)
            return

        if status in {"confirmation_timeout", "error", "rpc_error", "flood_wait"} and agent == "destination":
            await self._cancel_pending_trade(pending, reason=status)
            return

        if status == "success" and agent == "destination" and action == "cancel_own_order":
            await self._finalize_trade(pending)
            return

        if status == "success" and agent == "source":
            await self._finalize_trade(pending)
            return

    async def _advance_to_source_execution(self, pending: PendingPredictiveTrade, details: Dict[str, Any]) -> None:
        if pending.stage != "awaiting_fill":
            return

        if pending.timeout_task:
            pending.timeout_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pending.timeout_task
            pending.timeout_task = None

        confirmation_message_id = details.get("confirmation_message_id")
        if confirmation_message_id is not None:
            try:
                pending.destination_supervisor_message_id = int(confirmation_message_id)
            except (TypeError, ValueError):
                logger.debug("Unable to coerce confirmation message id %s", confirmation_message_id)

        if not pending.context_registered:
            context = TradeContext(
                trade_id=pending.trade_id,
                source_message_id=pending.source_message_id,
                destination_message_id=pending.destination_message_id or 0,
                quantity=pending.quantity,
                source_price=pending.source_price,
                destination_price=pending.destination_price,
                spread=pending.expected_spread,
                strategy="predictive",
            )
            self._tracker.register(context)
            pending.context_registered = True

        pending.stage = "awaiting_source_execution"
        await self._save_state(pending)

        command_payload = {
            "target_bot": "source",
            "action": "reply",
            "message_id": pending.source_message_id,
            "quantity": pending.quantity,
            "trade_id": pending.trade_id,
            "metadata": {
                "strategy": "predictive",
                "stage": "close_source_leg",
                "agent_key": "source",
                "policy_delta": self._policy.snapshot.fixed_spread_delta,
            },
        }
        await self._redis.publish_json(self._commands_channel, command_payload)
        logger.info(
            "Predictive trade %s filled in destination; closing source leg",
            pending.trade_id,
        )

    async def _cancel_pending_trade(self, pending: PendingPredictiveTrade, reason: str) -> None:
        if pending.stage == "cancelled":
            return

        pending.stage = "cancelled"
        if pending.timeout_task:
            pending.timeout_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pending.timeout_task
            pending.timeout_task = None

        if pending.destination_message_id:
            reply_target: Optional[int] = pending.destination_supervisor_message_id
            if reply_target is None:
                reply_target = self._tracker.get_supervisor_message_id(pending.trade_id, "destination")
            if reply_target is None and pending.destination_message_id is not None:
                reply_target = self._order_book.supervisor_message_id_for_original(
                    "destination",
                    int(pending.destination_message_id),
                )
            metadata = {
                "reason": reason,
                "strategy": "predictive",
                "reply_to_message_id": reply_target,
                "original_message_id": pending.destination_message_id,
                "send_cancellation_ack": reply_target is not None,
            }
            if reply_target is None:
                metadata["ack_fallback"] = "missing_supervisor_message"
            cancel_payload = {
                "target_bot": "destination",
                "action": "cancel_own_order",
                "message_id": pending.destination_message_id,
                "trade_id": pending.trade_id,
                "metadata": metadata,
            }
            await self._redis.publish_json(self._commands_channel, cancel_payload)
            logger.info(
                "Predictive trade %s cancelled (%s)",
                pending.trade_id,
                reason,
            )

        await self._save_state(pending)

    async def _finalize_trade(self, pending: PendingPredictiveTrade) -> None:
        await self._cleanup(pending.trade_id)

    async def _schedule_timeout(self, pending: PendingPredictiveTrade) -> None:
        if pending.timeout_task is not None:
            return

        async def _timeout() -> None:
            try:
                await asyncio.sleep(self._timeout_seconds)
            except asyncio.CancelledError:
                raise
            await self._cancel_pending_trade(pending, reason="timeout")

        pending.timeout_task = asyncio.create_task(_timeout(), name=f"pred-timeout-{pending.trade_id}")

    async def _save_state(self, pending: PendingPredictiveTrade) -> None:
        state = {
            "trade_id": pending.trade_id,
            "source_message_id": pending.source_message_id,
            "source_price": pending.source_price,
            "destination_price": pending.destination_price,
            "quantity": pending.quantity,
            "direction": pending.direction,
            "destination_message_id": pending.destination_message_id,
            "stage": pending.stage,
            "expected_spread": pending.expected_spread,
            "updated_at": time.time(),
        }
        await self._redis.set_json(self._state_key(pending.trade_id), state, ttl_seconds=self._timeout_seconds)
        await self._redis.set_json(
            self._source_index_key(pending.source_message_id),
            {"trade_id": pending.trade_id, "stage": pending.stage},
            ttl_seconds=self._timeout_seconds,
        )

    async def _cleanup(self, trade_id: str) -> None:
        async with self._lock:
            pending = self._pending.pop(trade_id, None)
            if pending:
                self._source_index.pop(pending.source_message_id, None)
        if pending and pending.timeout_task:
            pending.timeout_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pending.timeout_task
        await self._redis.delete(self._state_key(trade_id))
        if pending:
            await self._redis.delete(self._source_index_key(pending.source_message_id))

    async def _check_source_orders(self) -> None:
        async with self._lock:
            pending_trades = [trade for trade in self._pending.values()]

        for pending in pending_trades:
            if pending.stage not in {"awaiting_post_ack", "awaiting_fill"}:
                continue
            entry = self._order_book.get_entry("source", pending.source_message_id)
            if entry is None:
                await self._cancel_pending_trade(pending, reason="source_unavailable")

    def _should_post_speculative(self, direction: TradeDirection, source_price: int, target_price: int) -> bool:
        if direction == "source_sell":
            counterpart = self._order_book.best_entry("destination", "buy")
            if counterpart and counterpart.price is not None:
                if self._policy.is_profitable(direction, source_price=source_price, counter_price=counterpart.price):
                    return False
                if counterpart.price >= target_price:
                    return False
            return True

        counterpart = self._order_book.best_entry("destination", "sell")
        if counterpart and counterpart.price is not None:
            if self._policy.is_profitable(direction, source_price=source_price, counter_price=counterpart.price):
                return False
            if counterpart.price <= target_price:
                return False
        return True

    def _format_order_text(self, side: str, quantity: int, price: int) -> str:
        quantity_token = self._format_quantity(quantity)
        side_token = "خ" if side == "buy" else "ف"
        price_token = self._format_price_suffix(price)
        return f"{quantity_token}{side_token}{price_token}"

    @staticmethod
    def _format_quantity(quantity: int) -> str:
        safe_quantity = max(1, quantity)
        return str(safe_quantity)

    def _format_price_suffix(self, price: int) -> str:
        safe_price = max(0, price)
        modulus = 10 ** self._suffix_digits
        suffix = safe_price % modulus
        return str(suffix).zfill(self._suffix_digits)

    @staticmethod
    def _generate_trade_id() -> str:
        timestamp = int(time.time())
        unique = uuid.uuid4().hex[:8]
        return f"pred-{timestamp}-{unique}"

    @staticmethod
    def _state_key(trade_id: str) -> str:
        return f"predictive:trade:{trade_id}"

    @staticmethod
    def _source_index_key(message_id: int) -> str:
        return f"predictive:source:{message_id}"

    def update_predictive_price_delta(self, value: int) -> None:
        self._price_delta_override = max(0, value)
        snapshot = self._policy.update(fixed_spread_delta=self._price_delta_override)
        logger.info(
            "Updated predictive price delta to %s (fixed spread delta now %s)",
            self._price_delta_override,
            snapshot.fixed_spread_delta,
        )

    def update_predictive_suffix_digits(self, value: int) -> None:
        self._suffix_digits = max(1, value)
        logger.info("Updated predictive suffix digits to %s", self._suffix_digits)

    def update_predictive_spread(self, value: int) -> None:  # pragma: no cover - legacy admin command
        logger.warning("predictive_spread is deprecated; use predictive_price_delta instead")
        self.update_predictive_price_delta(value)

    def update_speculative_timeout(self, seconds: int) -> None:
        self._timeout_seconds = max(1, seconds)
        logger.info("Updated speculative trade timeout to %s", self._timeout_seconds)

    def update_minimum_profit_spread(self, value: int) -> None:
        snapshot = self._policy.update(fixed_spread_delta=value)
        logger.info("Updated fixed spread delta via legacy command to %s", snapshot.fixed_spread_delta)

    def pending_trade_count(self) -> int:
        return len(self._pending)