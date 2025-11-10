from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional

import redis.asyncio as redis


@dataclass
class RedisChannels:
    group_events: str
    execution_commands: str
    execution_results: str
    admin_commands: str
    admin_reports: str


class RedisManager:
    """Async Redis helper providing pub/sub and connection pooling."""

    def __init__(self, url: str, channels: RedisChannels) -> None:
        self._url = url
        self._channels = channels
        self._pool: Optional[redis.Redis] = None
        self._lock = asyncio.Lock()

    async def _ensure_pool(self) -> redis.Redis:
        async with self._lock:
            if self._pool is None:
                self._pool = redis.from_url(self._url, encoding="utf-8", decode_responses=True)
            return self._pool

    async def publish(self, channel: str, message: str) -> None:
        pool = await self._ensure_pool()
        await pool.publish(channel, message)

    async def publish_json(self, channel: str, payload: dict) -> None:
        await self.publish(channel, json.dumps(payload, ensure_ascii=False))

    async def subscribe(self, channel: str) -> AsyncIterator[str]:
        pool = await self._ensure_pool()
        pubsub = pool.pubsub()
        await pubsub.subscribe(channel)
        try:
            async for item in pubsub.listen():
                if item is None:
                    continue
                if item.get("type") != "message":
                    continue
                data = item.get("data")
                if data is not None:
                    yield data
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()

    async def add_to_set(self, key: str, member: str, ttl_seconds: Optional[int] = None) -> None:
        pool = await self._ensure_pool()
        await pool.sadd(key, member)
        if ttl_seconds is not None and ttl_seconds > 0:
            await pool.expire(key, ttl_seconds)

    async def is_member(self, key: str, member: str) -> bool:
        pool = await self._ensure_pool()
        return bool(await pool.sismember(key, member))

    async def remove_from_set(self, key: str, member: str) -> None:
        pool = await self._ensure_pool()
        await pool.srem(key, member)

    async def set_json(self, key: str, payload: dict, ttl_seconds: Optional[int] = None) -> None:
        pool = await self._ensure_pool()
        data = json.dumps(payload, ensure_ascii=False)
        if ttl_seconds is None or ttl_seconds <= 0:
            await pool.set(key, data)
        else:
            await pool.set(key, data, ex=ttl_seconds)

    async def get_json(self, key: str) -> Optional[dict[str, Any]]:
        pool = await self._ensure_pool()
        data = await pool.get(key)
        if data is None:
            return None
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return None

    async def delete(self, key: str) -> None:
        pool = await self._ensure_pool()
        await pool.delete(key)

    @property
    def channels(self) -> RedisChannels:
        return self._channels
