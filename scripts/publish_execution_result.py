#!/usr/bin/env python3
"""Publish a raw execution result payload for testing risk flows."""
from __future__ import annotations

import asyncio
import json
import sys
from typing import Any, Dict

from src.common.redis import RedisChannels, RedisManager
from src.config.settings import get_settings


async def main(payload: Dict[str, Any]) -> None:
    settings = get_settings()
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
    print("📤 Publishing execution result:")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    await redis_manager.publish_json(redis_manager.channels.execution_results, payload)
    print("✅ Payload sent")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/publish_execution_result.py '<json>'", file=sys.stderr)
        sys.exit(1)
    try:
        payload = json.loads(sys.argv[1])
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON payload: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        asyncio.run(main(payload))
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        sys.exit(1)
