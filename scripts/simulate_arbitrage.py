#!/usr/bin/env python3
"""Simulate an arbitrage opportunity end-to-end without Telegram bots."""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import random
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.common.db import DatabaseManager
from src.common.redis import RedisChannels, RedisManager
from src.config.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass
class PublishedOrder:
    message_id: int
    group_label: str
    side: str
    price: int
    quantity: int


async def publish_order(redis_manager: RedisManager, order: PublishedOrder) -> None:
    payload: Dict[str, Any] = {
        "category": "sell_order" if order.side == "sell" else "buy_order",
        "group_label": order.group_label,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "message": {
            "id": order.message_id,
            "date": datetime.now(tz=timezone.utc).isoformat(),
        },
        "details": {
            "quantity": str(order.quantity),
            "price": str(order.price),
        },
        "sender": {
            "id": random.randint(1000, 9999),
            "display_name": f"Test Trader {order.message_id}",
        },
    }
    await redis_manager.publish_json(redis_manager.channels.group_events, payload)
    logger.info("Published %s order %s @ %s", order.group_label, order.message_id, order.price)


async def capture_execution_commands(
    redis_manager: RedisManager,
    trade_id_timeout: float = 5.0,
) -> List[Dict[str, Any]]:
    commands: List[Dict[str, Any]] = []

    async def _listener() -> None:
        async for message in redis_manager.subscribe(redis_manager.channels.execution_commands):
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                logger.warning("Ignoring malformed execution command: %s", message)
                continue
            commands.append(payload)
            logger.info(
                "Captured execution command: target=%s trade_id=%s action=%s",
                payload.get("target_bot"),
                payload.get("trade_id"),
                payload.get("action"),
            )
            if len(commands) >= 2:
                break

    listener_task = asyncio.create_task(_listener())
    try:
        await asyncio.wait_for(listener_task, timeout=trade_id_timeout)
    except asyncio.TimeoutError:
        logger.warning("Timed out waiting for execution commands")
    finally:
        listener_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await listener_task

    return commands


async def publish_execution_results(
    redis_manager: RedisManager,
    commands: List[Dict[str, Any]],
) -> None:
    for command in commands:
        trade_id = command.get("trade_id")
        target = command.get("target_bot")
        message_id = command.get("message_id")
        payload = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "agent": target,
            "alias": target,
            "group_id": f"fake-{target}",
            "status": "success",
            "trade_id": trade_id,
            "action": command.get("action"),
            "command": command,
            "details": {
                "message_id": message_id,
                "text": command.get("text"),
            },
        }
        await redis_manager.publish_json(redis_manager.channels.execution_results, payload)
        logger.info(
            "Published fake execution result for trade %s (agent=%s)",
            trade_id,
            target,
        )
        await asyncio.sleep(0.1)


async def simulate() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    settings = get_settings()
    DatabaseManager(settings.database.path).initialize_schema()

    redis_manager = RedisManager(
        settings.redis.url,
        RedisChannels(
            group_events=settings.redis.group_events_channel,
            execution_commands=settings.redis.execution_commands_channel,
            execution_results=settings.redis.execution_results_channel,
            admin_commands=settings.redis.admin_commands_channel,
            admin_reports=settings.redis.admin_reports_channel,
        ),
    )

    base_id = int(time.time())
    source_order = PublishedOrder(
        message_id=base_id,
        group_label="source",
        side="sell",
        price=100,
        quantity=1,
    )
    destination_order = PublishedOrder(
        message_id=base_id + 1,
        group_label="destination",
        side="buy",
        price=150,
        quantity=1,
    )

    await publish_order(redis_manager, source_order)
    await asyncio.sleep(0.2)
    await publish_order(redis_manager, destination_order)

    commands = await capture_execution_commands(redis_manager)
    if not commands:
        logger.error("No execution commands were produced; check engine logs")
        return

    await publish_execution_results(redis_manager, commands)
    logger.info("Simulation complete. Check trade_history for new entries.")


if __name__ == "__main__":
    try:
        asyncio.run(simulate())
    except KeyboardInterrupt:
        print("Interrupted")
