#!/usr/bin/env python3
"""
Publish a structured admin notification over Redis.

Usage:
    python scripts/admin_notify.py deployment --status success --commit abc1234 --summary "Update" --author me
"""
from __future__ import annotations

import argparse
import asyncio
from typing import Any, Dict

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.common.redis import RedisChannels, RedisManager
from src.config.settings import get_settings


def _build_payload(args: argparse.Namespace) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "status": args.status,
    }
    if args.commit:
        data["commit"] = args.commit
    if args.author:
        data["author"] = args.author
    if args.summary:
        data["summary"] = args.summary
    if args.details:
        data["details"] = args.details

    payload: Dict[str, Any] = {
        "event": args.event,
        "message": args.message or args.summary or args.status,
        "data": data,
    }
    return payload


async def _publish(payload: Dict[str, Any]) -> None:
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
    await redis_manager.publish_json(redis_manager.channels.admin_reports, payload)


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a notification to admin_reports channel.")
    parser.add_argument("event", nargs="?", default="deployment", help="Event name (default: deployment)")
    parser.add_argument("--status", default="info", help="Status string to include in payload")
    parser.add_argument("--commit", default="", help="Short commit hash")
    parser.add_argument("--summary", default="", help="Short human-readable summary")
    parser.add_argument("--author", default="", help="Commit or deployment author")
    parser.add_argument("--details", default="", help="Additional details")
    parser.add_argument("--message", default="", help="Override message field (falls back to summary/status)")

    args = parser.parse_args()
    payload = _build_payload(args)
    asyncio.run(_publish(payload))


if __name__ == "__main__":
    main()

