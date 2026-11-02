"""Bound authenticated datasource probes across API workers.

Call only after checking that the authenticated actor may manage the datasource.
Production requires the existing auth Redis; failures never fall back to a
process-local counter. Local/test memory sessions have a bounded offline backend.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import threading
import time
from functools import lru_cache

from fastapi import HTTPException
from redis import Redis

from config.auth import AuthSettings

logger = logging.getLogger(__name__)

_WINDOW_SECONDS = 60
_MAX_MEMORY_KEYS = 2048
_LOCAL_ENVIRONMENTS = frozenset({"dev", "development", "local", "test"})
_memory_counts: dict[str, tuple[float, int]] = {}
_memory_lock = threading.Lock()

# Both keys use the same Redis Cluster hash tag. Check both limits before
# incrementing either, so a denied request cannot consume someone else's quota.
_CONSUME_SCRIPT = """
local retry = 0
for i = 1, 2 do
    local count = tonumber(redis.call('GET', KEYS[i]) or '0')
    if count >= tonumber(ARGV[i]) then
        local ttl = redis.call('TTL', KEYS[i])
        if ttl < 1 then ttl = tonumber(ARGV[3]) end
        if ttl > retry then retry = ttl end
    end
end
if retry > 0 then return {0, retry} end
for i = 1, 2 do
    local count = redis.call('INCR', KEYS[i])
    if count == 1 or redis.call('TTL', KEYS[i]) < 0 then
        redis.call('EXPIRE', KEYS[i], ARGV[3])
    end
end
return {1, 0}
"""


def _unavailable() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail="连接测试暂不可用，请稍后重试",
        headers={"Retry-After": str(_WINDOW_SECONDS)},
    )


def _limit(name: str, default: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    raw = raw.strip()
    if not raw.isascii() or not raw.isdecimal() or len(raw) > 6:
        raise ValueError("Invalid probe limit")
    result = int(raw)
    if not 1 <= result <= maximum:
        raise ValueError("Invalid probe limit")
    return result


@lru_cache(maxsize=4)
def _redis_client(url: str) -> Redis:
    return Redis.from_url(
        url,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )


def _consume_memory(keys: tuple[str, str], limits: tuple[int, int]) -> tuple[int, int]:
    now = time.monotonic()
    with _memory_lock:
        for key in [key for key, (expiry, _) in _memory_counts.items() if expiry <= now]:
            del _memory_counts[key]

        retry = 0
        for key, limit in zip(keys, limits, strict=True):
            current = _memory_counts.get(key)
            if current is not None and current[1] >= limit:
                retry = max(retry, max(1, math.ceil(current[0] - now)))
        if retry:
            return 0, retry

        if len(_memory_counts) + sum(key not in _memory_counts for key in keys) > _MAX_MEMORY_KEYS:
            raise RuntimeError("Probe counter capacity exhausted")
        for key in keys:
            expiry, count = _memory_counts.get(key, (now + _WINDOW_SECONDS, 0))
            _memory_counts[key] = (expiry, count + 1)
        return 1, 0


def consume_mysql_datasource_probe(user_id: str) -> None:
    """Reserve one probe for a trusted actor, or raise generic HTTP 429/503.

    MYSQL_DATASOURCE_PROBE_USER_LIMIT defaults to 5 (maximum 60) and
    MYSQL_DATASOURCE_PROBE_GLOBAL_LIMIT to 30 (maximum 600), per 60 seconds.
    Zero/invalid limits cannot disable the guard. Never pass a caller-controlled
    X-User-Id header here; use the authenticated PlatformActor.user_id instead.
    """
    try:
        if not isinstance(user_id, str) or not user_id.strip() or len(user_id) > 512:
            raise ValueError("Missing authenticated actor")
        limits = (
            _limit("MYSQL_DATASOURCE_PROBE_USER_LIMIT", 5, 60),
            _limit("MYSQL_DATASOURCE_PROBE_GLOBAL_LIMIT", 30, 600),
        )
        user_digest = hashlib.sha256(user_id.encode()).hexdigest()
        keys = (
            "mysql-datasource-probes:{all}:user:" + user_digest,
            "mysql-datasource-probes:{all}:global",
        )
        local_memory = (
            os.getenv("APP_ENV", "prod").strip().lower() in _LOCAL_ENVIRONMENTS
            and os.getenv("AUTH_SESSION_BACKEND", "").strip().lower() == "memory"
        )
        if local_memory:
            result = _consume_memory(keys, limits)
        else:
            result = _redis_client(AuthSettings.from_env().redis_url).eval(
                _CONSUME_SCRIPT, 2, *keys, *limits, _WINDOW_SECONDS
            )
        if (
            not isinstance(result, (list, tuple))
            or len(result) != 2
            or type(result[0]) is not int
            or type(result[1]) is not int
            or result[0] not in {0, 1}
            or (result[0] == 1 and result[1] != 0)
            or (result[0] == 0 and not 1 <= result[1] <= _WINDOW_SECONDS)
        ):
            raise ValueError("Invalid probe counter result")
    except Exception:  # noqa: BLE001
        # Driver errors can contain the Redis URL/password. Do not log them or
        # expose them to the API, including errors from configuration parsing.
        logger.warning("MySQL datasource probe limiter unavailable")
        raise _unavailable() from None

    if result[0] == 0:
        raise HTTPException(
            status_code=429,
            detail="连接测试过于频繁，请稍后重试",
            headers={"Retry-After": str(result[1])},
        )
