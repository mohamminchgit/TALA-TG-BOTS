from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Any, Dict, Optional

from telethon import Button, TelegramClient, events

from src.common.redis import RedisManager
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
        }
        self._aliases = {
            "source": source_alias,
            "destination": destination_alias,
        }

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
        elif data == "command:pause":
            await self._publish_command({"command": "safe_pause"})
            await event.answer("Pause requested")
        elif data == "command:resume":
            await self._publish_command({"command": "resume"})
            await event.answer("Resume requested")
        elif data == "command:status":
            await self._publish_command({"command": "status"})
            await event.answer("Status requested")
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
            async for message in self._redis.subscribe(self._redis.channels.admin_reports):
                try:
                    payload = json.loads(message)
                except json.JSONDecodeError:
                    logger.warning("Admin bot received invalid report payload: %s", message)
                    continue
                await self._handle_report(payload)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception("Admin report listener failed: %s", exc)

    async def _handle_report(self, payload: Dict[str, Any]) -> None:
        event = (payload.get("event") or "").lower()
        data = payload.get("data") or {}
        logger.debug("Admin report event=%s data=%s", event, data)

        if event == "config_updated":
            applied = data.get("applied") or {}
            for key in ("fixed_spread_delta", "base_carry_limit", "opportunity_carry_limit", "auto_n_delay_seconds"):
                if key in applied:
                    self._state[key] = applied[key]
            await self._refresh_dashboard()
            await self._notify(f"✅ Config updated: {json.dumps(applied, ensure_ascii=False)}")
        elif event == "config_noop":
            await self._notify("⚠️ Config update ignored: no supported keys")
        elif event == "status":
            await self._render_status(data)
        elif event in {"safe_pause_pending", "safe_pause_ready", "monitor_update", "panic", "resume", "shutdown", "admin_unknown"}:
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
        return (
            "⚙️ Engine Controls\n"
            f"Spread Δ: {self._state['fixed_spread_delta']}\n"
            f"Base Carry Limit: {self._state['base_carry_limit']}\n"
            f"Opportunity Limit: {opportunity_label}\n"
            f"Auto ن Delay: {self._state['auto_n_delay_seconds']}s"
        )

    def _build_keyboard(self) -> list[list[Button]]:
        base_limit = int(self._state.get("base_carry_limit", 1))
        opportunity = self._state.get("opportunity_carry_limit", 0)
        delay = int(self._state.get("auto_n_delay_seconds", 3))

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

        rows.append(
            [
                Button.inline("⏸ Pause", b"command:pause"),
                Button.inline("▶️ Resume", b"command:resume"),
                Button.inline("📊 Status", b"command:status"),
            ]
        )

        return rows

    @staticmethod
    def _option_button(prefix: str, value: str, current: str) -> Button:
        label = value
        comparison_value = value
        if value == "unlimited":
            label = "∞"
            comparison_value = "0"
        if comparison_value == current:
            label = f"✅ {label}"
        return Button.inline(label, f"{prefix}:{value}".encode("utf-8"))

    @staticmethod
    def _format_opportunity(value: Any) -> str:
        try:
            numeric = int(value)
        except (TypeError, ValueError):
            return str(value)
        return "∞" if numeric == 0 else str(numeric)