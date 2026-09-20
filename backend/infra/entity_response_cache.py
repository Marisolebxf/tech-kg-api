"""Two-level response cache for entity browse/search pages.

The in-process level avoids a Redis round trip for hot requests. Redis is the
shared level so cache entries survive API worker restarts and are reusable by
all workers. Redis failures are deliberately best-effort: entity queries must
continue to work even when the cache backend is temporarily unavailable.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import time
from typing import Any

from infra.redis import get_json_store

logger = logging.getLogger(__name__)

_MAX_LOCAL_ENTRIES = 2048
_REDIS_RETRY_SECONDS = 30.0


def build_cache_key(kind: str, **params: Any) -> str:
    """Return a stable, opaque key without exposing search text in Redis keys."""
    canonical = json.dumps(params, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{kind}:{digest}"


class EntityResponseCache:
    """Small L1 cache backed by the application's shared Redis JSON store."""

    def __init__(self, *, namespace: str, ttl_seconds: float) -> None:
        self.namespace = namespace.rstrip(":") + ":"
        self.ttl_seconds = max(float(ttl_seconds), 0.0)
        self._local: dict[str, tuple[float, str]] = {}
        self._redis_retry_after = 0.0

    @property
    def enabled(self) -> bool:
        return self.ttl_seconds > 0

    def _redis_key(self, key: str) -> str:
        return f"{self.namespace}{key}"

    async def get(self, key: str) -> str | None:
        if not self.enabled:
            return None
        now = time.monotonic()
        local = self._local.get(key)
        if local is not None:
            if local[0] > now:
                return local[1]
            self._local.pop(key, None)

        if now < self._redis_retry_after:
            return None
        try:
            cached = await get_json_store().get_json(self._redis_key(key))
        except Exception:  # noqa: BLE001 - cache outage must not break entity queries
            self._redis_retry_after = now + _REDIS_RETRY_SECONDS
            logger.warning("实体响应 Redis 缓存读取失败，暂时降级为进程内缓存", exc_info=True)
            return None
        payload = cached.get("payload") if isinstance(cached, dict) else None
        if not isinstance(payload, str):
            return None
        expires_at = cached.get("expiresAt")
        if not isinstance(expires_at, (int, float)):
            return None
        remaining = float(expires_at) - time.time()
        if remaining <= 0:
            return None
        # Do not restart the full L1 TTL when an almost-expired Redis entry is read.
        self._put_local(key, payload, now=now, ttl_seconds=remaining)
        return payload

    async def put(self, key: str, payload: str) -> None:
        if not self.enabled:
            return
        now = time.monotonic()
        self._put_local(key, payload, now=now)
        if now < self._redis_retry_after:
            return
        try:
            await get_json_store().set_json(
                self._redis_key(key),
                {"payload": payload, "expiresAt": time.time() + self.ttl_seconds},
                max(1, math.ceil(self.ttl_seconds)),
            )
        except Exception:  # noqa: BLE001 - L1 cache remains available
            self._redis_retry_after = now + _REDIS_RETRY_SECONDS
            logger.warning("实体响应 Redis 缓存写入失败，已保留进程内缓存", exc_info=True)

    async def clear(self) -> None:
        self._local.clear()
        now = time.monotonic()
        if now < self._redis_retry_after:
            return
        try:
            await get_json_store().delete_prefix(self.namespace)
        except Exception:  # noqa: BLE001 - entries still expire by TTL
            self._redis_retry_after = now + _REDIS_RETRY_SECONDS
            logger.warning("实体响应 Redis 缓存清理失败，将等待 TTL 自动过期", exc_info=True)

    def clear_local(self) -> None:
        """Test/support hook; shared entries are intentionally left untouched."""
        self._local.clear()

    def _put_local(
        self,
        key: str,
        payload: str,
        *,
        now: float,
        ttl_seconds: float | None = None,
    ) -> None:
        if len(self._local) >= _MAX_LOCAL_ENTRIES:
            expired = [item_key for item_key, item in self._local.items() if item[0] <= now]
            for item_key in expired:
                self._local.pop(item_key, None)
            if len(self._local) >= _MAX_LOCAL_ENTRIES:
                # Dicts preserve insertion order; evict the oldest inserted entry.
                self._local.pop(next(iter(self._local)), None)
        self._local[key] = (now + min(ttl_seconds or self.ttl_seconds, self.ttl_seconds), payload)
