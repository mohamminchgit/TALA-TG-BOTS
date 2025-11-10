from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from src.common.redis import RedisManager
from src.engine.core.engine_state import EngineState
from src.engine.core.order_book import OrderBook
from src.engine.core.trade_tracker import TradeContext

logger = logging.getLogger(__name__)


@dataclass
class ExitPlan:
    trade_id: str
    direction: str  # "long" -> need to sell, "short" -> need to buy
    quantity: int
    entry_price: int
    target_bot: str
    stage: str = "pending"
    order_message_id: Optional[int] = None
    timer: Optional[asyncio.Task] = None
    forced_emergency: bool = False
    flood_wait_delay: float = 0.0
    created_at: float = field(default_factory=time.time)


class RiskManager:
    """Coordinates layered exit strategies and crisis protocols."""

    def __init__(
        self,
        redis_manager: RedisManager,
        order_book: OrderBook,
        engine_state: EngineState,
        execution_commands_channel: str,
        admin_reports_channel: str,
        break_even_timeout_seconds: int,
        stop_loss_timeout_seconds: int,
        stop_loss_price_offset: int,
        circuit_breaker_seconds: int,
        source_alias: str,
        destination_alias: str,
    ) -> None:
        self._redis = redis_manager
        self._order_book = order_book
        self._engine_state = engine_state
        self._commands_channel = execution_commands_channel
        self._admin_channel = admin_reports_channel
        self._break_even_timeout = max(1, break_even_timeout_seconds)
        self._stop_loss_timeout = max(1, stop_loss_timeout_seconds)
        self._stop_loss_offset = max(1, stop_loss_price_offset)
        self._circuit_breaker_seconds = max(1, circuit_breaker_seconds)
        self._source_alias = source_alias
        self._destination_alias = destination_alias

        self._exit_plans: Dict[str, ExitPlan] = {}
        self._flood_wait_pending: Dict[str, float] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def trading_paused(self) -> bool:
        return not self._engine_state.can_trade()

    async def handle_execution_result(self, payload: Dict[str, Any]) -> None:
        trade_id = payload.get("trade_id")
        status = payload.get("status")
        if not trade_id or not status:
            return

        if status == "flood_wait":
            wait_seconds = max(0.0, float(payload.get("details", {}).get("wait_seconds", 0)))
            async with self._lock:
                self._flood_wait_pending[trade_id] = wait_seconds
            await self._publish_admin_report(
                event="flood_wait",
                message=f"Trade {trade_id} encountered FloodWait; scheduling emergency exit in {wait_seconds:.1f}s",
                data={"trade_id": trade_id, "wait_seconds": wait_seconds},
            )
            return

        async with self._lock:
            plan = self._exit_plans.get(trade_id)

        if not plan:
            return

        action = (payload.get("command") or {}).get("action") or payload.get("action")
        agent = payload.get("agent")

        if status == "success" and action == "post_new_order":
            message_id = payload.get("details", {}).get("sent_message_id")
            if message_id is None:
                message_id = payload.get("details", {}).get("message_id")
            if message_id is not None:
                plan.order_message_id = int(message_id)
                logger.info("Exit plan %s posted order %s", trade_id, plan.order_message_id)
            return

        if status == "success" and action == "cancel_own_order":
            plan.order_message_id = None
            return

        if status == "confirmation_detected":
            await self._complete_exit(plan, reason="confirmation")
            return

        if status == "confirmation_timeout":
            if plan.stage == "break_even":
                await self._advance_stage(plan.trade_id, "stop_loss")
            elif plan.stage == "stop_loss":
                await self._advance_stage(plan.trade_id, "emergency")
            return

        if status == "success" and action == "reply" and agent in {"source", "destination"}:
            await self._complete_exit(plan, reason="reply_success")
            return

    async def handle_trade_final(self, context: TradeContext, final_status: str) -> None:
        if not context.failed:
            async with self._lock:
                self._flood_wait_pending.pop(context.trade_id, None)
            return

        if context.quantity <= 0:
            return

        source_status = context.agent_status.get("source")
        destination_status = context.agent_status.get("destination")
        source_success = source_status in {"success", "confirmation_detected"}
        destination_success = destination_status in {"success", "confirmation_detected"}

        direction: Optional[str] = None
        target_bot: Optional[str] = None
        entry_price: int = 0

        if source_success and not destination_success:
            direction = "long"
            target_bot = "destination"
            entry_price = context.source_price or context.destination_price
        elif destination_success and not source_success:
            direction = "short"
            target_bot = "source"
            entry_price = context.destination_price or context.source_price

        if direction is None or target_bot is None:
            logger.info(
                "Trade %s failed but no open position detected (statuses: source=%s destination=%s)",
                context.trade_id,
                source_status,
                destination_status,
            )
            async with self._lock:
                self._flood_wait_pending.pop(context.trade_id, None)
            return

        forced_emergency = False
        flood_delay = 0.0
        async with self._lock:
            if context.trade_id in self._exit_plans:
                return
            if context.trade_id in self._flood_wait_pending:
                forced_emergency = True
                flood_delay = self._flood_wait_pending.pop(context.trade_id)

        plan = ExitPlan(
            trade_id=context.trade_id,
            direction=direction,
            quantity=max(1, context.quantity),
            entry_price=max(0, entry_price),
            target_bot=target_bot,
            forced_emergency=forced_emergency,
            flood_wait_delay=flood_delay,
            stage="pending",
        )

        async with self._lock:
            self._exit_plans[plan.trade_id] = plan

        if forced_emergency and flood_delay > 0:
            await self._publish_admin_report(
                event="exit_forced",
                message=f"Trade {plan.trade_id} entering emergency exit after FloodWait",
                data={"trade_id": plan.trade_id, "delay_seconds": flood_delay},
            )
            plan.timer = asyncio.create_task(
                self._schedule_stage(plan, "emergency", flood_delay),
                name=f"exit-flood-{plan.trade_id}",
            )
        elif forced_emergency:
            await self._publish_admin_report(
                event="exit_forced",
                message=f"Trade {plan.trade_id} triggering immediate emergency exit",
                data={"trade_id": plan.trade_id},
            )
            await self._advance_stage(plan.trade_id, "emergency")
        else:
            await self._publish_admin_report(
                event="exit_started",
                message=f"Trade {plan.trade_id} starting layered exit ({plan.direction})",
                data={
                    "trade_id": plan.trade_id,
                    "direction": plan.direction,
                    "quantity": plan.quantity,
                },
            )
            await self._advance_stage(plan.trade_id, "break_even")

    def update_parameters(
        self,
        break_even_timeout_seconds: Optional[int] = None,
        stop_loss_timeout_seconds: Optional[int] = None,
        stop_loss_price_offset: Optional[int] = None,
        circuit_breaker_seconds: Optional[int] = None,
    ) -> None:
        if break_even_timeout_seconds is not None:
            self._break_even_timeout = max(1, break_even_timeout_seconds)
        if stop_loss_timeout_seconds is not None:
            self._stop_loss_timeout = max(1, stop_loss_timeout_seconds)
        if stop_loss_price_offset is not None:
            self._stop_loss_offset = max(1, stop_loss_price_offset)
        if circuit_breaker_seconds is not None:
            self._circuit_breaker_seconds = max(1, circuit_breaker_seconds)

    def resume_trading(self) -> None:
        self._engine_state.resume()

    def pause_trading(self, duration_seconds: float) -> None:
        self._engine_state.pause_for(duration_seconds)

    def get_default_pause_seconds(self) -> int:
        return self._circuit_breaker_seconds

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _advance_stage(self, trade_id: str, stage: str) -> None:
        async with self._lock:
            plan = self._exit_plans.get(trade_id)
        if not plan:
            return

        if plan.timer:
            plan.timer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await plan.timer
            plan.timer = None

        if stage == "break_even":
            plan.stage = "break_even"
            await self._issue_break_even(plan)
            plan.timer = asyncio.create_task(
                self._schedule_stage(plan, "stop_loss", self._break_even_timeout),
                name=f"exit-be-{plan.trade_id}",
            )
            return

        if stage == "stop_loss":
            if plan.forced_emergency:
                await self._advance_stage(trade_id, "emergency")
                return
            plan.stage = "stop_loss"
            await self._issue_stop_loss(plan)
            plan.timer = asyncio.create_task(
                self._schedule_stage(plan, "emergency", self._stop_loss_timeout),
                name=f"exit-sl-{plan.trade_id}",
            )
            return

        if stage == "emergency":
            plan.stage = "emergency"
            await self._issue_emergency(plan)
            await self._complete_exit(plan, reason="emergency")

    async def _schedule_stage(self, plan: ExitPlan, stage: str, delay: float) -> None:
        try:
            await asyncio.sleep(max(0.0, delay))
        except asyncio.CancelledError:  # pragma: no cover - cancelled when stage completed sooner
            raise
        await self._advance_stage(plan.trade_id, stage)

    async def _issue_break_even(self, plan: ExitPlan) -> None:
        price = plan.entry_price
        if plan.direction == "long":
            text = self._format_order_text("sell", plan.quantity, price, self._destination_alias)
        else:
            text = self._format_order_text("buy", plan.quantity, price, self._source_alias)
        await self._publish_command(plan.target_bot, "post_new_order", text=text, trade_id=plan.trade_id, stage="break_even")

    async def _issue_stop_loss(self, plan: ExitPlan) -> None:
        if plan.order_message_id:
            await self._publish_command(
                plan.target_bot,
                "cancel_own_order",
                message_id=plan.order_message_id,
                trade_id=plan.trade_id,
                stage="stop_loss_cancel",
            )
            plan.order_message_id = None

        if plan.direction == "long":
            best = self._order_book.best_entry("destination", "buy")
            base_price = best.price if best and best.price is not None else plan.entry_price
            price = max(0, base_price - self._stop_loss_offset)
            text = self._format_order_text("sell", plan.quantity, price, self._destination_alias)
        else:
            best = self._order_book.best_entry("source", "sell")
            base_price = best.price if best and best.price is not None else plan.entry_price
            price = max(0, base_price + self._stop_loss_offset)
            text = self._format_order_text("buy", plan.quantity, price, self._source_alias)

        await self._publish_command(plan.target_bot, "post_new_order", text=text, trade_id=plan.trade_id, stage="stop_loss")

    async def _issue_emergency(self, plan: ExitPlan) -> None:
        if plan.order_message_id:
            await self._publish_command(
                plan.target_bot,
                "cancel_own_order",
                message_id=plan.order_message_id,
                trade_id=plan.trade_id,
                stage="emergency_cancel",
            )
            plan.order_message_id = None

        if plan.direction == "long":
            target_entry = self._order_book.best_entry("destination", "buy")
            if target_entry:
                await self._publish_command(
                    "destination",
                    "reply",
                    message_id=target_entry.message_id,
                    trade_id=plan.trade_id,
                    quantity=plan.quantity,
                    stage="emergency_reply",
                )
            else:
                fallback_price = max(0, plan.entry_price - self._stop_loss_offset * 2)
                text = self._format_order_text("sell", plan.quantity, fallback_price, self._destination_alias)
                await self._publish_command("destination", "post_new_order", text=text, trade_id=plan.trade_id, stage="emergency_post")
        else:
            target_entry = self._order_book.best_entry("source", "sell")
            if target_entry:
                await self._publish_command(
                    "source",
                    "reply",
                    message_id=target_entry.message_id,
                    trade_id=plan.trade_id,
                    quantity=plan.quantity,
                    stage="emergency_reply",
                )
            else:
                fallback_price = plan.entry_price + self._stop_loss_offset * 2
                text = self._format_order_text("buy", plan.quantity, fallback_price, self._source_alias)
                await self._publish_command("source", "post_new_order", text=text, trade_id=plan.trade_id, stage="emergency_post")

        self._engine_state.pause_for(self._circuit_breaker_seconds)
        await self._publish_admin_report(
            event="circuit_breaker",
            message=(
                f"Emergency exit executed for trade {plan.trade_id}; trading paused for {self._circuit_breaker_seconds}s"
            ),
            data={"trade_id": plan.trade_id, "pause_seconds": self._circuit_breaker_seconds},
        )

    async def _complete_exit(self, plan: ExitPlan, reason: str) -> None:
        async with self._lock:
            existing = self._exit_plans.pop(plan.trade_id, None)
        if existing and existing.timer:
            existing.timer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await existing.timer
        await self._publish_admin_report(
            event="exit_complete",
            message=f"Exit flow completed for trade {plan.trade_id} ({reason})",
            data={"trade_id": plan.trade_id, "reason": reason},
        )

    async def _publish_command(
        self,
        target_bot: str,
        action: str,
        *,
        text: Optional[str] = None,
        message_id: Optional[int] = None,
        quantity: Optional[int] = None,
        trade_id: str,
        stage: str,
    ) -> None:
        payload: Dict[str, Any] = {
            "target_bot": target_bot,
            "action": action,
            "trade_id": trade_id,
            "metadata": {"stage": stage, "strategy": "risk_management"},
        }
        if text is not None:
            payload["text"] = text
        if message_id is not None:
            payload["message_id"] = message_id
            if action == "cancel_own_order":
                payload.setdefault("metadata", {})["reply_to_message_id"] = message_id
        if quantity is not None:
            payload["quantity"] = quantity

        await self._redis.publish_json(self._commands_channel, payload)
        logger.info("RiskManager issued %s command for trade %s (stage=%s)", action, trade_id, stage)

    async def _publish_admin_report(self, event: str, message: str, data: Optional[Dict[str, Any]] = None) -> None:
        payload = {
            "timestamp": time.time(),
            "event": event,
            "message": message,
        }
        if data is not None:
            payload["data"] = data
        await self._redis.publish_json(self._admin_channel, payload)

    @staticmethod
    def _format_order_text(side: str, quantity: int, price: int, alias: str) -> str:
        quantity = max(1, quantity)
        price = max(0, price)
        alias = alias.strip() or "ربات"
        if side == "sell":
            return f"🔴 {alias} {quantity} ف {price}"
        return f"🔵 {alias} {quantity} خ {price}"