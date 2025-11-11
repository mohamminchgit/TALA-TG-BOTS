from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from typing import Any, Dict, Optional

from telethon import Button, TelegramClient, events

from src.common.redis import RedisManager, StreamMessage
from src.engine.core.trade_policy import PolicySnapshot

logger = logging.getLogger(__name__)


class AdminControlBot:
    """Telegram inline keyboard controller for runtime engine operations."""

    def __init__(
        self,
        *,
        redis_manager: RedisManager,
        api_id: int,
        api_hash: str,
        bot_token: str,
        chat_id: int,
        policy_snapshot: PolicySnapshot,
        initial_auto_delay: int,
        status_refresh_seconds: int,
        source_alias: str,
        destination_alias: str,
        engine_config: Dict[str, Any],
        initial_monitor_only: bool,
    ) -> None:
        self._redis = redis_manager
        self._api_id = api_id
        self._api_hash = api_hash
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._status_refresh_seconds = max(5, status_refresh_seconds)
        self._client = TelegramClient("admin_control_bot", api_id, api_hash)
        self._dashboard_message_id: Optional[int] = None
        self._status_message_id: Optional[int] = None
        self._report_task: Optional[asyncio.Task] = None
        self._dashboard_lock = asyncio.Lock()
        self._state: Dict[str, Any] = {
            "fixed_spread_delta": policy_snapshot.fixed_spread_delta,
            "base_carry_limit": policy_snapshot.base_carry_limit,
            "opportunity_carry_limit": policy_snapshot.opportunity_carry_limit,
            "auto_n_delay_seconds": max(0, initial_auto_delay),
            "predictive_price_delta": engine_config.get("predictive_price_delta"),
            "predictive_suffix_digits": engine_config.get("predictive_suffix_digits"),
            "speculative_trade_timeout_seconds": engine_config.get("speculative_trade_timeout_seconds"),
            "source_order_expiry_seconds": engine_config.get("source_order_expiry_seconds"),
            "exit_break_even_timeout_seconds": engine_config.get("exit_break_even_timeout_seconds"),
            "exit_stop_loss_timeout_seconds": engine_config.get("exit_stop_loss_timeout_seconds"),
            "stop_loss_price_offset": engine_config.get("stop_loss_price_offset"),
            "circuit_breaker_pause_seconds": engine_config.get("circuit_breaker_pause_seconds"),
            "monitor_only": initial_monitor_only,
        }
        self._aliases = {
            "source": source_alias,
            "destination": destination_alias,
        }
        self._report_group = "admin_reports"
        self._report_consumer = f"admin-bot-{uuid.uuid4().hex}"

    async def run(self) -> None:
        await self._client.start(bot_token=self._bot_token)
        self._client.add_event_handler(self._on_start, events.NewMessage(pattern=r"/start"))
        self._client.add_event_handler(self._on_callback, events.CallbackQuery())
        await self._send_dashboard(initial=True)
        self._report_task = asyncio.create_task(self._consume_reports(), name="admin-bot-reports")
        try:
            await self._client.run_until_disconnected()
        finally:
            if self._report_task and not self._report_task.done():
                self._report_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._report_task

    async def stop(self) -> None:
        if self._report_task and not self._report_task.done():
            self._report_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._report_task
        await self._client.disconnect()

    async def _on_start(self, event: events.NewMessage.Event) -> None:
        if event.chat_id != self._chat_id:
            return
        await self._send_dashboard()

    async def _on_callback(self, event: events.CallbackQuery.Event) -> None:
        if event.chat_id != self._chat_id:
            await event.answer("Not authorised", alert=True)
            return

        data = (event.data or b"").decode("utf-8")
        logger.debug("Admin control callback received: %s", data)
        if data.startswith("carry:"):
            value = int(data.split(":", 1)[1])
            await self._publish_update({"base_carry_limit": value})
            await event.answer(f"Base carry set to {value}")
        elif data.startswith("opportunity:"):
            raw = data.split(":", 1)[1]
            if raw == "unlimited":
                value = 0
                label = "∞"
            else:
                value = int(raw)
                label = raw
            await self._publish_update({"opportunity_carry_limit": value})
            await event.answer(f"Opportunity limit set to {label}")
        elif data.startswith("delay:"):
            value = int(data.split(":", 1)[1])
            await self._publish_update({"auto_n_delay_seconds": value})
            await event.answer(f"Auto ن delay set to {value}s")
        elif data.startswith("predictive_delta:"):
            value = int(data.split(":", 1)[1])
            await self._publish_update({"predictive_price_delta": value})
            await event.answer(f"Predictive delta set to {value}")
        elif data.startswith("suffix:"):
            value = int(data.split(":", 1)[1])
            await self._publish_update({"predictive_suffix_digits": value})
            await event.answer(f"Predictive suffix digits set to {value}")
        elif data.startswith("spec_timeout:"):
            value = int(data.split(":", 1)[1])
            await self._publish_update({"speculative_trade_timeout_seconds": value})
            await event.answer(f"Speculative timeout set to {value}s")
        elif data.startswith("source_expiry:"):
            value = int(data.split(":", 1)[1])
            await self._publish_update({"source_order_expiry_seconds": value})
            await event.answer(f"Source expiry set to {value}s")
        elif data.startswith("break_even:"):
            value = int(data.split(":", 1)[1])
            await self._publish_update({"exit_break_even_timeout_seconds": value})
            await event.answer(f"Break-even wait set to {value}s")
        elif data.startswith("stop_loss_wait:"):
            value = int(data.split(":", 1)[1])
            await self._publish_update({"exit_stop_loss_timeout_seconds": value})
            await event.answer(f"Stop-loss wait set to {value}s")
        elif data.startswith("stop_loss_offset:"):
            value = int(data.split(":", 1)[1])
            await self._publish_update({"stop_loss_price_offset": value})
            await event.answer(f"Stop-loss offset set to {value}")
        elif data.startswith("circuit:"):
            value = int(data.split(":", 1)[1])
            await self._publish_update({"circuit_breaker_pause_seconds": value})
            await event.answer(f"Circuit breaker set to {value // 60}m")
        elif data.startswith("monitor:"):
            enabled = data.split(":", 1)[1] == "1"
            await self._publish_update({"monitor_only": enabled})
            await event.answer("Monitor-only enabled" if enabled else "Monitor-only disabled")
        elif data == "command:pause":
            await self._publish_command({"command": "safe_pause"})
            await event.answer("Pause requested")
        elif data == "command:resume":
            await self._publish_command({"command": "resume"})
            await event.answer("Resume requested")
        elif data == "command:status":
            await self._publish_command({"command": "status"})
            await event.answer("Status requested")
        elif data == "command:stop":
            await self._publish_command({"command": "shutdown"})
            await event.answer("Shutdown requested")
        elif data == "command:start":
            await self._publish_command({"command": "resume"})
            await event.answer("Start requested")
        else:
            await event.answer("Unknown action", alert=True)
            return

        await self._refresh_dashboard()

    async def _publish_update(self, updates: Dict[str, Any]) -> None:
        self._state.update({key: updates.get(key, self._state.get(key)) for key in self._state.keys() if key in updates})
        payload = {
            "command": "update_config",
            "updates": updates,
        }
        await self._redis.publish_json(self._redis.channels.admin_commands, payload)

    async def _publish_command(self, payload: Dict[str, Any]) -> None:
        await self._redis.publish_json(self._redis.channels.admin_commands, payload)

    async def _send_dashboard(self, *, initial: bool = False) -> None:
        async with self._dashboard_lock:
            text = self._render_dashboard_text()
            keyboard = self._build_keyboard()
            if initial or not self._dashboard_message_id:
                message = await self._client.send_message(
                    self._chat_id,
                    text,
                    buttons=keyboard,
                )
                self._dashboard_message_id = message.id
            else:
                try:
                    await self._client.edit_message(self._chat_id, self._dashboard_message_id, text, buttons=keyboard)
                except Exception as exc:  # pragma: no cover - defensive logging
                    logger.warning("Failed to refresh admin dashboard: %s", exc)
                    self._dashboard_message_id = None
                    await self._client.send_message(self._chat_id, text, buttons=keyboard)

    async def _refresh_dashboard(self) -> None:
        if not self._dashboard_message_id:
            return
        await self._send_dashboard()

    async def _consume_reports(self) -> None:
        try:
            async for message in self._redis.consume_stream(
                self._redis.channels.admin_reports,
                self._report_group,
                self._report_consumer,
                count=100,
            ):
                await self._handle_report_message(message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception("Admin report listener failed: %s", exc)

    async def _handle_report_message(self, message: StreamMessage) -> None:
        payload_raw = message.payload
        if isinstance(payload_raw, dict):
            payload = payload_raw
        else:
            try:
                payload = json.loads(payload_raw)
            except Exception:
                logger.warning("Admin bot received invalid report payload: %s", payload_raw)
                await message.ack()
                return
        await self._handle_report(payload)
        await message.ack()

    async def _handle_report(self, payload: Dict[str, Any]) -> None:
        event = (payload.get("event") or "").lower()
        data = payload.get("data") or {}
        logger.debug("Admin report event=%s data=%s", event, data)

        if event == "config_updated":
            applied = data.get("applied") or {}
            tracked_keys = {
                "fixed_spread_delta",
                "base_carry_limit",
                "opportunity_carry_limit",
                "auto_n_delay_seconds",
                "predictive_price_delta",
                "predictive_suffix_digits",
                "speculative_trade_timeout_seconds",
                "source_order_expiry_seconds",
                "exit_break_even_timeout_seconds",
                "exit_stop_loss_timeout_seconds",
                "stop_loss_price_offset",
                "circuit_breaker_pause_seconds",
                "monitor_only",
            }
            for key, value in applied.items():
                if key in tracked_keys:
                    self._state[key] = value
            await self._refresh_dashboard()
            await self._notify(f"✅ Config updated: {json.dumps(applied, ensure_ascii=False)}")
        elif event == "config_noop":
            await self._notify("⚠️ Config update ignored: no supported keys")
        elif event == "status":
            await self._render_status(data)
        elif event == "monitor_update":
            if "monitor_only" in data:
                self._state["monitor_only"] = bool(data["monitor_only"])
                await self._refresh_dashboard()
            await self._notify(f"ℹ️ Monitor-only mode {'enabled' if data.get('monitor_only') else 'disabled'}")
        elif event == "deployment":
            status = data.get("status", "unknown").upper()
            commit = data.get("commit", "unknown")
            summary = data.get("summary", "")
            author = data.get("author", "")
            details = data.get("details", "")
            lines = [f"🚀 Deployment {status} — {commit}"]
            if summary:
                lines.append(summary)
            if author:
                lines.append(f"by {author}")
            if details:
                lines.append(details)
            await self._notify("\n".join(lines))
        elif event in {"safe_pause_pending", "safe_pause_ready", "panic", "resume", "shutdown", "admin_unknown"}:
            await self._notify(f"ℹ️ {event.replace('_', ' ').title()}: {json.dumps(data, ensure_ascii=False)}")

    async def _render_status(self, data: Dict[str, Any]) -> None:
        lines = [
            "📊 Engine Status",
            f"Source: {self._aliases['source']}",
            f"Destination: {self._aliases['destination']}",
            f"Trading Allowed: {'Yes' if data.get('trading_allowed') else 'No'}",
            f"Monitor Only: {'Yes' if data.get('monitor_only') else 'No'}",
        ]
        order_book = data.get("order_book") or {}
        for group in ("source", "destination"):
            stats = order_book.get(group) or {}
            lines.append(
                f"{group.title()}: {stats.get('orders', 0)} orders (buy {stats.get('buy_orders', 0)}, sell {stats.get('sell_orders', 0)})"
            )
        advertisements = order_book.get("advertisements") or {}
        lines.append(
            f"Auto Ads: {advertisements.get('total', 0)} (buy {advertisements.get('by_side', {}).get('buy', 0)}, "
            f"sell {advertisements.get('by_side', {}).get('sell', 0)})"
        )
        trade_history = data.get("trade_history") or {}
        lines.append(
            f"Trades: {trade_history.get('total_trades', 0)} | P&L: {trade_history.get('total_profit', 0):.2f}"
        )
        policy = data.get("policy") or {}
        lines.append(
            f"Policy Δ={policy.get('fixed_spread_delta')} carry={policy.get('base_carry_limit')} opp={self._format_opportunity(policy.get('opportunity_carry_limit'))}"
        )

        text = "\n".join(lines)
        if self._status_message_id:
            try:
                await self._client.edit_message(self._chat_id, self._status_message_id, text)
                return
            except Exception:
                self._status_message_id = None
        message = await self._client.send_message(self._chat_id, text)
        self._status_message_id = message.id

    async def _notify(self, text: str) -> None:
        try:
            await self._client.send_message(self._chat_id, text)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Failed to send admin notification: %s", exc)

    def _render_dashboard_text(self) -> str:
        opportunity_label = self._format_opportunity(self._state.get("opportunity_carry_limit"))
        circuit_minutes = int(int(self._state.get("circuit_breaker_pause_seconds", 0) or 0) / 60)
        monitor_flag = "Yes" if self._state.get("monitor_only") else "No"
        return (
            "⚙️ Engine Controls\n"
            f"Spread Δ: {self._state['fixed_spread_delta']}\n"
            f"Base Carry Limit: {self._state['base_carry_limit']}\n"
            f"Opportunity Limit: {opportunity_label}\n"
            f"Auto ن Delay: {self._state['auto_n_delay_seconds']}s\n"
            f"Spec Timeout: {self._state.get('speculative_trade_timeout_seconds', 0)}s | Source Expiry: {self._state.get('source_order_expiry_seconds', 0)}s\n"
            f"Break-even Wait: {self._state.get('exit_break_even_timeout_seconds', 0)}s | Stop-loss Wait: {self._state.get('exit_stop_loss_timeout_seconds', 0)}s\n"
            f"Stop-loss Offset: {self._state.get('stop_loss_price_offset', 0)} | Circuit Breaker: {circuit_minutes}m\n"
            f"Monitor Only: {monitor_flag}"
        )

    def _build_keyboard(self) -> list[list[Button]]:
        base_limit = int(self._state.get("base_carry_limit", 1))
        opportunity = self._state.get("opportunity_carry_limit", 0)
        delay = int(self._state.get("auto_n_delay_seconds", 3))
        predictive_delta = str(self._state.get("predictive_price_delta", 0))
        suffix_digits = str(self._state.get("predictive_suffix_digits", 4))
        spec_timeout = str(self._state.get("speculative_trade_timeout_seconds", 0))
        source_expiry = str(self._state.get("source_order_expiry_seconds", 0))
        break_even = str(self._state.get("exit_break_even_timeout_seconds", 0))
        stop_loss_wait = str(self._state.get("exit_stop_loss_timeout_seconds", 0))
        stop_loss_offset = str(self._state.get("stop_loss_price_offset", 0))
        circuit_seconds = str(self._state.get("circuit_breaker_pause_seconds", 0))
        monitor_current = "1" if self._state.get("monitor_only") else "0"

        rows: list[list[Button]] = []
        carry_row = [
            self._option_button("carry", str(value), str(base_limit))
            for value in (1, 2, 3, 4)
        ]
        rows.append(carry_row)

        opportunity_row = [
            self._option_button("opportunity", "1", str(opportunity)),
            self._option_button("opportunity", "2", str(opportunity)),
            self._option_button("opportunity", "3", str(opportunity)),
            self._option_button("opportunity", "unlimited", "0" if opportunity == 0 else str(opportunity)),
        ]
        rows.append(opportunity_row)

        delay_row = [
            self._option_button("delay", str(value), str(delay))
            for value in (0, 3, 10, 30)
        ]
        rows.append(delay_row)

        predictive_row = [
            self._option_button("predictive_delta", str(value), predictive_delta)
            for value in (5, 10, 15)
        ]
        rows.append(predictive_row)

        suffix_row = [
            self._option_button("suffix", str(value), suffix_digits)
            for value in (3, 4, 5)
        ]
        rows.append(suffix_row)

        spec_row = [
            self._option_button("spec_timeout", str(value), spec_timeout, label=f"{value}s")
            for value in (30, 60, 120)
        ]
        rows.append(spec_row)

        expiry_row = [
            self._option_button("source_expiry", str(value), source_expiry, label=f"{value}s")
            for value in (30, 60, 90)
        ]
        rows.append(expiry_row)

        break_even_row = [
            self._option_button("break_even", str(value), break_even, label=f"{value}s")
            for value in (2, 5, 10)
        ]
        rows.append(break_even_row)

        stop_loss_row = [
            self._option_button("stop_loss_wait", str(value), stop_loss_wait, label=f"{value}s")
            for value in (4, 8, 15)
        ]
        rows.append(stop_loss_row)

        stop_offset_row = [
            self._option_button("stop_loss_offset", str(value), stop_loss_offset)
            for value in (5, 10, 20)
        ]
        rows.append(stop_offset_row)

        circuit_row = [
            self._option_button("circuit", str(value), circuit_seconds, label=f"{value // 60}m")
            for value in (300, 600, 1800)
        ]
        rows.append(circuit_row)

        monitor_row = [
            self._option_button("monitor", "1", monitor_current, label="👁 Monitor On"),
            self._option_button("monitor", "0", monitor_current, label="👁 Monitor Off"),
        ]
        rows.append(monitor_row)

        rows.append(
            [
                Button.inline("⏸ Pause", b"command:pause"),
                Button.inline("▶️ Resume", b"command:resume"),
                Button.inline("📊 Status", b"command:status"),
            ]
        )
        rows.append(
            [
                Button.inline("🔴 Stop Engine", b"command:stop"),
                Button.inline("🟢 Start Engine", b"command:start"),
            ]
        )

        return rows

    @staticmethod
    def _option_button(prefix: str, value: str, current: str, label: Optional[str] = None) -> Button:
        display = label or value
        comparison_value = value
        if value == "unlimited":
            display = "∞"
            comparison_value = "0"
        if comparison_value == current:
            display = f"✅ {display}"
        return Button.inline(display, f"{prefix}:{value}".encode("utf-8"))

    @staticmethod
    def _format_opportunity(value: Any) -> str:
        try:
            numeric = int(value)
        except (TypeError, ValueError):
            return str(value)
        return "∞" if numeric == 0 else str(numeric)