"""Redis JSON 缓存封装，供 OAuth state、会话和权限缓存复用。"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Protocol

from redis.asyncio import Redis

from config.auth import AuthSettings


class AsyncJsonStore(Protocol):
    async def get_json(self, key: str) -> dict[str, Any] | None: ...

    async def set_json(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None: ...

    async def pop_json(self, key: str) -> dict[str, Any] | None: ...

    async def delete(self, key: str) -> None: ...

    async def close(self) -> None: ...


class RedisClient:
    """惰性创建的异步 Redis 客户端。"""

    def __init__(self, url: str) -> None:
        self._url = url
        self._client: Redis | None = None

    @property
    def client(self) -> Redis:
        if self._client is None:
            self._client = Redis.from_url(self._url, decode_responses=True)
        return self._client

    async def get_json(self, key: str) -> dict[str, Any] | None:
        payload = await self.client.get(key)
        return json.loads(payload) if payload else None

    async def set_json(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        await self.client.set(key, json.dumps(value, ensure_ascii=False), ex=ttl_seconds)

    async def pop_json(self, key: str) -> dict[str, Any] | None:
        payload = await self.client.getdel(key)
        return json.loads(payload) if payload else None

    async def delete(self, key: str) -> None:
        await self.client.delete(key)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


class MemoryJsonStore:
    """本地开发和单元测试使用的带 TTL 内存实现。"""

    def __init__(self) -> None:
        self._values: dict[str, tuple[float, dict[str, Any]]] = {}
        self._lock = asyncio.Lock()

    def _now(self) -> float:
        return asyncio.get_running_loop().time()

    async def get_json(self, key: str) -> dict[str, Any] | None:
        async with self._lock:
            item = self._values.get(key)
            if item is None:
                return None
            expires_at, value = item
            if expires_at <= self._now():
                self._values.pop(key, None)
                return None
            return json.loads(json.dumps(value, ensure_ascii=False))

    async def set_json(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        async with self._lock:
            self._values[key] = (
                self._now() + ttl_seconds,
                json.loads(json.dumps(value, ensure_ascii=False)),
            )

    async def pop_json(self, key: str) -> dict[str, Any] | None:
        async with self._lock:
            item = self._values.pop(key, None)
            if item is None or item[0] <= self._now():
                return None
            return json.loads(json.dumps(item[1], ensure_ascii=False))

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._values.pop(key, None)

    async def close(self) -> None:
        async with self._lock:
            self._values.clear()


_store: AsyncJsonStore | None = None


def get_json_store(settings: AuthSettings | None = None) -> AsyncJsonStore:
    global _store
    if _store is None:
        resolved = settings or AuthSettings.from_env()
        _store = (
            MemoryJsonStore()
            if resolved.session_backend == "memory"
            else RedisClient(resolved.redis_url)
        )
    return _store


async def close_redis_client() -> None:
    global _store
    if _store is not None:
        await _store.close()
        _store = None
