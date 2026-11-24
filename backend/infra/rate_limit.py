"""按调用身份的固定窗口频控（用户 id / 机器 client id）。

多 worker 部署经 Redis 计数（与 auth 会话共用实例，键前缀 ``ratelimit:`` 隔离）；
AUTH_SESSION_BACKEND=memory（本地/测试）或 Redis 不可用时退回进程内计数——
退化为单 worker 口径，但不放行无上限请求。

额度用环境变量覆盖：``RATE_LIMIT_<BUCKET>``，取值 ``<次数>/<秒>``，如
``RATE_LIMIT_GRAPH_CONSOLE=60/60``；``0`` 关闭该桶。
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass

from fastapi import HTTPException

logger = logging.getLogger(__name__)

_KEY_PREFIX = "ratelimit:"


@dataclass(frozen=True)
class RateLimit:
    limit: int
    window_seconds: int


def configured_limit(bucket: str, default: RateLimit) -> RateLimit | None:
    raw = os.getenv(f"RATE_LIMIT_{bucket.upper().replace('-', '_')}", "").strip()
    if not raw:
        return default
    if raw == "0":
        return None
    try:
        count, _, window = raw.partition("/")
        parsed = RateLimit(int(count), int(window or default.window_seconds))
    except ValueError:
        logger.warning("频控配置无效，沿用默认值 bucket=%s value=%s", bucket, raw)
        return default
    return parsed if parsed.limit > 0 and parsed.window_seconds > 0 else default


class _MemoryCounter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._windows: dict[str, tuple[float, int]] = {}

    def add(self, key: str, cost: int, window: int) -> tuple[int, int]:
        now = time.monotonic()
        with self._lock:
            if len(self._windows) > 10_000:
                for stale in [k for k, (end, _) in self._windows.items() if end <= now]:
                    del self._windows[stale]
            end, used = self._windows.get(key, (0.0, 0))
            if end <= now:
                end, used = now + window, 0
            used += cost
            self._windows[key] = (end, used)
            return used, max(1, int(end - now))


_memory = _MemoryCounter()
_redis_client = None
_redis_lock = threading.Lock()


def _redis():
    global _redis_client
    if os.getenv("AUTH_SESSION_BACKEND", "redis").lower() == "memory":
        return None
    with _redis_lock:
        if _redis_client is None:
            from redis.asyncio import Redis

            from config.auth import AuthSettings

            _redis_client = Redis.from_url(
                AuthSettings.from_env().redis_url,
                decode_responses=True,
                socket_timeout=0.5,
                socket_connect_timeout=0.5,
            )
        return _redis_client


async def _add(key: str, cost: int, window: int) -> tuple[int, int]:
    client = _redis()
    if client is not None:
        try:
            async with client.pipeline(transaction=True) as pipe:
                pipe.set(key, 0, ex=window, nx=True)
                pipe.incrby(key, cost)
                pipe.ttl(key)
                _, used, ttl = await pipe.execute()
            return int(used), max(1, int(ttl))
        except Exception:  # noqa: BLE001 — 频控存储故障不应拖垮业务，退回进程内计数
            logger.warning("频控 Redis 不可用，退回进程内计数", exc_info=True)
    return _memory.add(key, cost, window)


async def enforce_rate_limit(
    bucket: str, identity: str, default: RateLimit, *, cost: int = 1
) -> None:
    """超额抛 429（带 Retry-After）；identity 为空时按匿名单桶计。"""
    limit = configured_limit(bucket, default)
    if limit is None:
        return
    used, retry_after = await _add(
        f"{_KEY_PREFIX}{bucket}:{identity or 'anonymous'}", max(1, cost), limit.window_seconds
    )
    if used > limit.limit:
        raise HTTPException(
            status_code=429,
            detail=f"请求过于频繁，请 {retry_after} 秒后重试",
            headers={"Retry-After": str(retry_after)},
        )


def reset_memory_counters() -> None:
    """测试用：清空进程内计数。"""
    global _memory
    _memory = _MemoryCounter()
