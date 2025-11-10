from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional

from src.common.db import DatabaseManager
from src.common.redis import RedisManager
from src.engine.core.engine_state import EngineState
from src.engine.core.order_book import OrderBook
from src.engine.core.trade_matcher import ImmediateArbitrageMatcher
from src.engine.core.predictive_market_maker import PredictiveMarketMaker
from src.engine.core.trade_policy import TradePolicy
from src.engine.services.risk_manager import RiskManager

logger = logging.getLogger(__name__)


class AdminCommandService:
    """Consumes admin commands and applies runtime configuration updates."""

    def __init__(
        self,
        redis_manager: RedisManager,
        command_channel: str,
        report_channel: str,
        order_book: OrderBook,
        engine_state: EngineState,
        matcher: ImmediateArbitrageMatcher,
        predictive: PredictiveMarketMaker,
        risk_manager: RiskManager,
        policy: TradePolicy,
        database: DatabaseManager,
    ) -> None:
        self._redis = redis_manager
        self._command_channel = command_channel
        self._report_channel = report_channel
        self._order_book = order_book
        self._engine_state = engine_state
        self._matcher = matcher
        self._predictive = predictive
        self._risk_manager = risk_manager
        self._stop_event = asyncio.Event()
        self._shutdown_callbacks: List[Callable[[], Awaitable[None] | None]] = []
        self._policy = policy
        self._safe_pause_task: Optional[asyncio.Task] = None
        self._database = database

    def register_shutdown_callback(self, callback: Callable[[], Awaitable[None] | None]) -> None:
        self._shutdown_callbacks.append(callback)

    def stop(self) -> None:
        self._stop_event.set()
        if self._safe_pause_task and not self._safe_pause_task.done():
            self._safe_pause_task.cancel()

    async def run(self) -> None:
        logger.info("Listening for admin commands on %s", self._command_channel)
        try:
            async for message in self._redis.subscribe(self._command_channel):
                if self._stop_event.is_set():
                    break
                payload = self._parse_payload(message)
                if payload is None:
                    continue
                await self._handle_command(payload)
        except asyncio.CancelledError:
            raise

    @staticmethod
    def _parse_payload(message: Any) -> Optional[Dict[str, Any]]:
        if isinstance(message, bytes):
            message = message.decode("utf-8", errors="ignore")
        if not isinstance(message, str):
            logger.warning("Unsupported admin command payload type: %s", type(message))
            return None
        try:
            return json.loads(message)
        except json.JSONDecodeError:
            logger.warning("Failed to decode admin command payload: %s", message)
            return None

    async def _handle_command(self, payload: Dict[str, Any]) -> None:
        command = (payload.get("command") or payload.get("type") or "").lower()
        if not command:
            await self._send_report("admin_error", "Command missing", {"payload": payload})
            return

        logger.info("Admin command received: %s", command)

        if command == "update_config":
            await self._handle_update_config(payload.get("updates") or {})
        elif command == "status":
            await self._handle_status_request()
        elif command in {"monitor_only", "monitor"}:
            await self._handle_monitor_only(bool(payload.get("enabled", True)))
        elif command in {"panic", "pause"}:
            duration = float(payload.get("duration_seconds", self._risk_manager.get_default_pause_seconds()))
            await self._handle_panic(duration)
        elif command == "safe_pause":
            await self._handle_safe_pause()
        elif command == "resume":
            await self._handle_resume()
        elif command == "safe_resume":
            await self._handle_resume()
        elif command == "shutdown":
            await self._handle_shutdown()
        else:
            await self._send_report("admin_unknown", f"Unknown command: {command}", {"payload": payload})

    async def _handle_update_config(self, updates: Dict[str, Any]) -> None:
        applied: Dict[str, Any] = {}
        snapshot = None

        if "minimum_profit_spread" in updates:
            value = int(updates["minimum_profit_spread"])
            snapshot = self._policy.update(fixed_spread_delta=value)
            applied["minimum_profit_spread"] = value
            applied["fixed_spread_delta"] = snapshot.fixed_spread_delta
            self._predictive.update_predictive_price_delta(snapshot.fixed_spread_delta)

        if "fixed_spread_delta" in updates:
            value = int(updates["fixed_spread_delta"])
            snapshot = self._policy.update(fixed_spread_delta=value)
            applied["fixed_spread_delta"] = snapshot.fixed_spread_delta
            self._predictive.update_predictive_price_delta(snapshot.fixed_spread_delta)

        if "base_carry_limit" in updates:
            base_value = self._coerce_carry_limit(updates["base_carry_limit"], allow_zero=False)
            snapshot = self._policy.update(base_carry_limit=base_value)
            applied["base_carry_limit"] = snapshot.base_carry_limit

        if "opportunity_carry_limit" in updates:
            opportunity_value = self._coerce_carry_limit(updates["opportunity_carry_limit"], allow_zero=True)
            snapshot = self._policy.update(opportunity_carry_limit=opportunity_value)
            applied["opportunity_carry_limit"] = snapshot.opportunity_carry_limit

        if "predictive_price_delta" in updates:
            value = int(updates["predictive_price_delta"])
            self._predictive.update_predictive_price_delta(value)
            applied["predictive_price_delta"] = value

        if "predictive_suffix_digits" in updates:
            value = int(updates["predictive_suffix_digits"])
            self._predictive.update_predictive_suffix_digits(value)
            applied["predictive_suffix_digits"] = value

        if "predictive_spread" in updates:
            value = int(updates["predictive_spread"])
            self._predictive.update_predictive_spread(value)
            applied.setdefault("predictive_price_delta", value)

        if "speculative_trade_timeout_seconds" in updates:
            value = int(updates["speculative_trade_timeout_seconds"])
            self._predictive.update_speculative_timeout(value)
            applied["speculative_trade_timeout_seconds"] = value

        if "source_order_expiry_seconds" in updates:
            value = int(updates["source_order_expiry_seconds"])
            self._predictive.update_source_expiry_seconds(value)
            applied["source_order_expiry_seconds"] = value

        risk_params: Dict[str, Any] = {}
        if "exit_break_even_timeout_seconds" in updates:
            value = int(updates["exit_break_even_timeout_seconds"])
            risk_params["break_even_timeout_seconds"] = value
            applied["exit_break_even_timeout_seconds"] = value
        if "exit_stop_loss_timeout_seconds" in updates:
            value = int(updates["exit_stop_loss_timeout_seconds"])
            risk_params["stop_loss_timeout_seconds"] = value
            applied["exit_stop_loss_timeout_seconds"] = value
        if "stop_loss_price_offset" in updates:
            value = int(updates["stop_loss_price_offset"])
            risk_params["stop_loss_price_offset"] = value
            applied["stop_loss_price_offset"] = value
        if "circuit_breaker_pause_seconds" in updates:
            value = int(updates["circuit_breaker_pause_seconds"])
            risk_params["circuit_breaker_seconds"] = value
            applied["circuit_breaker_pause_seconds"] = value
        if risk_params:
            self._risk_manager.update_parameters(**risk_params)

        if "auto_n_delay_seconds" in updates:
            delay = int(updates["auto_n_delay_seconds"])
            await self._broadcast_cancel_delay(delay)
            applied["auto_n_delay_seconds"] = delay

        if "monitor_only" in updates:
            await self._handle_monitor_only(bool(updates["monitor_only"]))
            applied["monitor_only"] = bool(updates["monitor_only"])

        if not applied:
            await self._send_report("config_noop", "No supported config keys provided", {"updates": updates})
            return

        self._persist_config_updates(applied)

        await self._send_report(
            "config_updated",
            "Configuration updated",
            {
                "applied": applied,
                "policy": {
                    "fixed_spread_delta": self._policy.snapshot.fixed_spread_delta,
                    "base_carry_limit": self._policy.snapshot.base_carry_limit,
                    "opportunity_carry_limit": self._policy.snapshot.opportunity_carry_limit,
                },
            },
        )

    async def _handle_status_request(self) -> None:
        await self._send_report("status", "Engine status", self._current_state_snapshot())

    async def _handle_monitor_only(self, enabled: bool) -> None:
        self._engine_state.set_monitor_only(enabled)
        await self._send_report(
            "monitor_update",
            "Monitor-only mode enabled" if enabled else "Monitor-only mode disabled",
            {"monitor_only": enabled},
        )

    async def _handle_panic(self, duration_seconds: float) -> None:
        self._risk_manager.pause_trading(duration_seconds)
        await self._send_report(
            "panic",
            f"Trading paused for {duration_seconds:.1f}s",
            {"duration_seconds": duration_seconds},
        )

    async def _handle_safe_pause(self) -> None:
        self._engine_state.set_monitor_only(True)
        snapshot = self._current_state_snapshot()
        snapshot["outstanding_orders"] = self._outstanding_order_count()
        snapshot["predictive_pending"] = self._predictive.pending_trade_count()
        await self._send_report(
            "safe_pause_pending",
            "Monitor-only mode enabled; awaiting open orders to clear",
            snapshot,
        )
        if self._safe_pause_task and not self._safe_pause_task.done():
            return
        self._safe_pause_task = asyncio.create_task(self._await_safe_pause(), name="admin-safe-pause")

    async def _handle_resume(self) -> None:
        if self._safe_pause_task and not self._safe_pause_task.done():
            self._safe_pause_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._safe_pause_task
            self._safe_pause_task = None
        self._engine_state.set_monitor_only(False)
        self._risk_manager.resume_trading()
        await self._send_report("resume", "Trading resumed", {})

    async def _handle_shutdown(self) -> None:
        self._engine_state.request_shutdown()
        for callback in self._shutdown_callbacks:
            try:
                result = callback()
                if asyncio.iscoroutine(result):
                    await result
            except Exception:  # pragma: no cover - defensive logging
                logger.exception("Shutdown callback failed")
        self.stop()
        await self._send_report("shutdown", "Engine shutdown requested", {})

    async def _send_report(self, event: str, message: str, data: Optional[Dict[str, Any]]) -> None:
        payload = {
            "event": event,
            "message": message,
            "data": data,
        }
        await self._redis.publish_json(self._report_channel, payload)

    def _persist_config_updates(self, applied: Dict[str, Any]) -> None:
        persist_keys = {
            "fixed_spread_delta",
            "minimum_profit_spread",
            "base_carry_limit",
            "opportunity_carry_limit",
            "predictive_price_delta",
            "predictive_suffix_digits",
            "speculative_trade_timeout_seconds",
            "source_order_expiry_seconds",
            "exit_break_even_timeout_seconds",
            "exit_stop_loss_timeout_seconds",
            "stop_loss_price_offset",
            "circuit_breaker_pause_seconds",
            "auto_n_delay_seconds",
        }
        entries = {key: applied[key] for key in applied if key in persist_keys}
        if not entries:
            return

        with self._database.connect() as conn:
            cursor = conn.cursor()
            for key, value in entries.items():
                cursor.execute(
                    """
                    INSERT INTO config (parameter_name, parameter_value, description, updated_at)
                    VALUES (?, ?, NULL, CURRENT_TIMESTAMP)
                    ON CONFLICT(parameter_name) DO UPDATE SET
                        parameter_value=excluded.parameter_value,
                        updated_at=CURRENT_TIMESTAMP
                    """,
                    (key, str(value)),
                )
            conn.commit()

    @staticmethod
    def _coerce_carry_limit(value: Any, *, allow_zero: bool) -> int:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"unlimited", "∞", "inf", "infinite", "no_limit", "none"}:
                if allow_zero:
                    return 0
                raise ValueError("base_carry_limit cannot be unlimited")
        limit = int(value)
        if limit < 0:
            return 0 if allow_zero else 1
        if not allow_zero and limit == 0:
            return 1
        return limit

    async def _broadcast_cancel_delay(self, seconds: int) -> None:
        command = {
            "action": "update_settings",
            "settings": {"cancel_ack_delay_seconds": max(0, seconds)},
        }
        for target in ("source", "destination"):
            payload = dict(command)
            payload["target_bot"] = target
            await self._redis.publish_json(self._redis.channels.execution_commands, payload)

    def _current_state_snapshot(self) -> Dict[str, Any]:
        summary = self._order_book.summary()
        policy_snapshot = self._policy.snapshot
        snapshot = {
            "trading_allowed": self._engine_state.can_trade(),
            "monitor_only": self._engine_state.monitor_only,
            "paused_until": self._engine_state.paused_until_epoch,
            "order_book": summary,
            "policy": {
                "fixed_spread_delta": policy_snapshot.fixed_spread_delta,
                "base_carry_limit": policy_snapshot.base_carry_limit,
                "opportunity_carry_limit": policy_snapshot.opportunity_carry_limit,
            },
            "predictive_pending": self._predictive.pending_trade_count(),
        }
        with self._database.connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) AS total_trades, COALESCE(SUM(profit), 0) AS total_profit FROM trade_history")
            row = cursor.fetchone()
            if row:
                snapshot["trade_history"] = {
                    "total_trades": row["total_trades"],
                    "total_profit": float(row["total_profit"] or 0.0),
                }
        return snapshot

    def _outstanding_order_count(self) -> int:
        summary = self._order_book.summary()
        total = 0
        for group in ("source", "destination"):
            stats = summary.get(group) or {}
            total += int(stats.get("orders", 0))
        advertisements = summary.get("advertisements") or {}
        total += int(advertisements.get("total", 0))
        return total

    async def _await_safe_pause(self) -> None:
        try:
            while True:
                outstanding = self._outstanding_order_count()
                pending = self._predictive.pending_trade_count()
                if outstanding == 0 and pending == 0:
                    await self._send_report(
                        "safe_pause_ready",
                        "All open orders cleared; engine can be safely paused",
                        self._current_state_snapshot(),
                    )
                    return
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            raise
        finally:
            self._safe_pause_task = None
