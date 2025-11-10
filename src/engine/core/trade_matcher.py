from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from src.common.redis import RedisManager
from src.engine.core.engine_state import EngineState
from src.engine.core.order_book import OrderBook, OrderEntry
from src.engine.core.trade_policy import TradeDirection, TradePolicy
from src.engine.core.trade_tracker import TradeContext, TradeTracker

logger = logging.getLogger(__name__)


class ImmediateArbitrageMatcher:
    """Detects profitable spreads and publishes paired execution commands."""

    def __init__(
        self,
        order_book: OrderBook,
        redis_manager: RedisManager,
        execution_commands_channel: str,
        policy: TradePolicy,
        trade_tracker: TradeTracker,
        engine_state: Optional[EngineState] = None,
    ) -> None:
        self._order_book = order_book
        self._redis = redis_manager
        self._commands_channel = execution_commands_channel
        self._policy = policy
        self._lock = asyncio.Lock()
        self._tracker = trade_tracker
        self._engine_state = engine_state

    async def process_event(self, event: Dict[str, Any]) -> None:
        if event.get("category") not in {
            "buy_order",
            "sell_order",
            "partial_match",
            "cancel_all",
            "trade_confirmation",
            "auto_advertisement",
        }:
            return

        async with self._lock:
            await self._attempt_matches()

    async def _attempt_matches(self) -> None:
        if self._engine_state and not self._engine_state.can_trade():
            return
        while True:
            executed = False
            executed |= await self._process_direction("source_sell", opportunistic=False)
            executed |= await self._process_direction("source_buy", opportunistic=False)
            executed |= await self._process_advertisements()
            if not executed:
                break

    async def _process_direction(self, direction: TradeDirection, *, opportunistic: bool) -> bool:
        source_side = "sell" if direction == "source_sell" else "buy"
        source_entry = self._order_book.best_entry("source", source_side)
        if not source_entry or source_entry.price is None:
            return False

        plan = self._build_destination_plan(direction, source_entry, opportunistic=opportunistic)
        if not plan:
            return False

        await self._finalize_trade(
            direction,
            source_entry,
            plan,
            opportunistic=opportunistic,
            is_advertisement=False,
        )
        return True

    async def _process_advertisements(self) -> bool:
        advertisements = sorted(
            self._order_book.advertisements(),
            key=lambda entry: entry.created_at_monotonic,
        )
        for advert in advertisements:
            if advert.price is None:
                continue
            direction: TradeDirection = "source_sell" if advert.side == "sell" else "source_buy"
            plan = self._build_destination_plan(direction, advert, opportunistic=True)
            if not plan:
                continue
            await self._finalize_trade(
                direction,
                advert,
                plan,
                opportunistic=True,
                is_advertisement=True,
            )
            return True
        return False

    def _build_destination_plan(
        self,
        direction: TradeDirection,
        source_order: OrderEntry,
        *,
        opportunistic: bool,
    ) -> List[tuple[OrderEntry, int]]:
        destination_side = "buy" if direction == "source_sell" else "sell"
        candidates = self._order_book.side_entries("destination", destination_side)
        if not candidates:
            return []

        allowed_quantity = self._policy.allowed_quantity(source_order.remaining_quantity, opportunistic=opportunistic)
        remaining = min(source_order.remaining_quantity, allowed_quantity)
        if remaining <= 0:
            return []

        plan: List[tuple[OrderEntry, int]] = []
        for candidate in candidates:
            if candidate.price is None:
                continue
            if not self._policy.is_profitable(
                direction,
                source_price=source_order.price or 0,
                counter_price=candidate.price or 0,
            ):
                continue
            fill_quantity = min(candidate.remaining_quantity, remaining)
            if fill_quantity <= 0:
                continue
            plan.append((candidate, fill_quantity))
            remaining -= fill_quantity
            if remaining <= 0:
                break
        return plan

    async def _finalize_trade(
        self,
        direction: TradeDirection,
        source_order: OrderEntry,
        plan: List[tuple[OrderEntry, int]],
        *,
        opportunistic: bool,
        is_advertisement: bool,
    ) -> None:
        total_quantity = sum(quantity for _, quantity in plan)
        if total_quantity <= 0:
            return

        spreads = [
            self._compute_spread(direction, source_order.price or 0, entry.price or 0)
            for entry, _ in plan
        ]
        if not spreads:
            return
        min_spread = min(spreads)
        weighted_notional = sum((entry.price or 0) * quantity for entry, quantity in plan)
        destination_price = int(round(weighted_notional / total_quantity)) if total_quantity else 0

        trade_id = self._generate_trade_id()
        strategy = "advertisement" if is_advertisement else ("opportunistic" if opportunistic else "immediate")

        destination_primary = plan[0][0] if plan else None
        context = TradeContext(
            trade_id=trade_id,
            source_message_id=source_order.message_id,
            destination_message_id=destination_primary.message_id if destination_primary else 0,
            quantity=total_quantity,
            source_price=source_order.price or 0,
            destination_price=destination_price,
            spread=min_spread,
            strategy=strategy,
        )
        self._tracker.register(context)
        for index, (destination_entry, quantity) in enumerate(plan):
            agent_key = f"destination_leg_{index}"
            leg_price = destination_entry.price or 0
            self._tracker.register_destination_leg(
                trade_id,
                agent_key,
                destination_entry.message_id,
                quantity=quantity,
                price=leg_price,
            )

        await self._publish_plan(
            trade_id,
            direction,
            source_order,
            plan,
            min_spread=min_spread,
            opportunistic=opportunistic,
            is_advertisement=is_advertisement,
        )

        if not is_advertisement:
            self._order_book.reserve_quantity("source", source_order.message_id, total_quantity)
        else:
            source_order.apply_fill(total_quantity)
            if source_order.remaining_quantity <= 0:
                self._order_book.pop_advertisement(source_order.message_id)

        for destination_entry, quantity in plan:
            self._order_book.reserve_quantity("destination", destination_entry.message_id, quantity)

    async def _publish_plan(
        self,
        trade_id: str,
        direction: TradeDirection,
        source_order: OrderEntry,
        plan: List[tuple[OrderEntry, int]],
        *,
        min_spread: int,
        opportunistic: bool,
        is_advertisement: bool,
    ) -> None:
        destination_payloads = []
        total_quantity = sum(quantity for _, quantity in plan)
        for index, (destination_order, quantity) in enumerate(plan):
            leg_spread = self._compute_spread(direction, source_order.price or 0, destination_order.price or 0)
            metadata = {
                "matched_with": source_order.message_id,
                "spread": leg_spread,
                "leg_index": index,
                "leg_count": len(plan),
                "leg_quantity": quantity,
                "leg_price": destination_order.price or 0,
                "leg_message_id": destination_order.message_id,
                "agent_key": f"destination_leg_{index}",
                "direction": direction,
                "opportunistic": opportunistic,
                "advertisement": is_advertisement,
            }
            destination_payloads.append(
                {
                    "target_bot": "destination",
                    "action": "reply",
                    "message_id": destination_order.message_id,
                    "quantity": quantity,
                    "trade_id": trade_id,
                    "metadata": metadata,
                }
            )

        for payload in destination_payloads:
            await self._redis.publish_json(self._commands_channel, payload)

        source_metadata = {
            "matched_with": [entry.message_id for entry, _ in plan],
            "spread": min_spread,
            "legs": [
                {
                    "message_id": entry.message_id,
                    "quantity": quantity,
                    "price": entry.price,
                }
                for entry, quantity in plan
            ],
            "agent_key": "source",
            "direction": direction,
            "opportunistic": opportunistic,
            "advertisement": is_advertisement,
        }

        source_payload = {
            "target_bot": "source",
            "action": "reply",
            "message_id": source_order.message_id,
            "quantity": total_quantity,
            "trade_id": trade_id,
            "metadata": source_metadata,
        }

        await self._redis.publish_json(self._commands_channel, source_payload)

        logger.info(
            "Published commands for trade %s (direction=%s source_msg=%s legs=%s total_quantity=%s)",
            trade_id,
            direction,
            source_order.message_id,
            len(plan),
            total_quantity,
        )

    @staticmethod
    def _compute_spread(direction: TradeDirection, source_price: int, counter_price: int) -> int:
        if direction == "source_sell":
            return counter_price - source_price
        return source_price - counter_price

    @staticmethod
    def _generate_trade_id() -> str:
        timestamp = int(time.time())
        unique = uuid.uuid4().hex[:8]
        return f"imm-{timestamp}-{unique}"

    def update_minimum_spread(self, value: int) -> None:
        snapshot = self._policy.update(fixed_spread_delta=value)
        logger.info("Updated fixed spread delta via legacy API: %s", snapshot.fixed_spread_delta)
