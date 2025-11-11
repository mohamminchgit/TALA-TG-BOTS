from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, Optional, Tuple

import redis.asyncio as redis


@dataclass
class RedisChannels:
    group_events: str
    execution_commands: str
    execution_results: str
    admin_commands: str
    admin_reports: str


@dataclass
class StreamMessage:
    stream: str
    group: str
    message_id: str
    payload: Dict[str, Any]
    manager: "RedisManager"
    delete_after_ack: bool

    async def ack(self) -> None:
        await self.manager.ack(self.stream, self.group, self.message_id, delete=self.delete_after_ack)


class RedisManager:
    """Async Redis helper backed by streams and consumer groups."""

    def __init__(self, url: str, channels: RedisChannels) -> None:
        self._url = url
        self._channels = channels
        self._pool: Optional[redis.Redis] = None
        self._lock = asyncio.Lock()
        self._group_cache: set[Tuple[str, str]] = set()

    async def _ensure_pool(self) -> redis.Redis:
        async with self._lock:
            if self._pool is None:
                self._pool = redis.from_url(self._url, encoding="utf-8", decode_responses=True)
            return self._pool

    async def publish_json(self, stream: str, payload: Dict[str, Any], *, maxlen: Optional[int] = None) -> str:
        pool = await self._ensure_pool()
        data = json.dumps(payload, ensure_ascii=False)
        kwargs: Dict[str, Any] = {"fields": {"payload": data}}
        if maxlen is not None and maxlen > 0:
            kwargs["maxlen"] = maxlen
            kwargs["approximate"] = True
        message_id = await pool.xadd(stream, **kwargs)
        return message_id

    async def consume_stream(
        self,
        stream: str,
        group: str,
        consumer: str,
        *,
        count: int = 100,
        block_ms: int = 5000,
        delete_on_ack: bool = True,
    ) -> AsyncIterator[StreamMessage]:
        pool = await self._ensure_pool()
        await self._ensure_group(pool, stream, group)
        while True:
            response = await pool.xreadgroup(group, consumer, streams={stream: ">"}, count=count, block=block_ms)
            if not response:
                continue
            for _, entries in response:
                for message_id, fields in entries:
                    payload = self._decode_fields(stream, message_id, fields)
                    if payload is None:
                        await pool.xack(stream, group, message_id)
                        if delete_on_ack:
                            await pool.xdel(stream, message_id)
                        continue
                    yield StreamMessage(stream, group, message_id, payload, self, delete_on_ack)

    async def ack(self, stream: str, group: str, message_id: str, *, delete: bool = True) -> None:
        pool = await self._ensure_pool()
        await pool.xack(stream, group, message_id)
        if delete:
            await pool.xdel(stream, message_id)

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

    async def _ensure_group(self, pool: redis.Redis, stream: str, group: str) -> None:
        key = (stream, group)
        if key in self._group_cache:
            return
        try:
            await pool.xgroup_create(stream, group, id="0", mkstream=True)
        except redis.ResponseError as exc:  # BUSYGROUP means the group already exists
            if "BUSYGROUP" not in str(exc):
                raise
        self._group_cache.add(key)

    @staticmethod
    def _decode_fields(stream: str, message_id: str, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        raw = fields.get("payload")
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"stream": stream, "message_id": message_id, "raw": raw}
