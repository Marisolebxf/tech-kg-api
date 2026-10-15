"""消歧写前守卫——同名微锁（根治并行批次同名双写竞态）。

竞态形状（gkx_verify_1 2026-10-10 两个「汪小红」节点实锤）：多来源
``asyncio.gather`` 并行 + 来源内多 worker 时，批次 A 的消歧召回跑在批次 B 的
INSERT 落地之前，双方都判「无同名候选」→ 同名实体双双按新节点写图。批内同名
去重与 Milvus 批内增量入索引只覆盖同批；跨批的窗口由本模块关死：把「写前
二次确认 + INSERT」整段包进按 (graph_space, label, normalize(name)) 加键的
Redis 微锁——同名写入方跨批/跨来源/跨 job 串行，异名完全并行，吞吐无感。

锁语义：

- ``SET key token NX PX ttl``（token 释放走 Lua 比删，防误删他人锁）；批内
  多名字排序获取防 ABBA 死锁；TTL 兜底持锁方崩溃自愈。
- 键不含 run/任务——同栈并发写同图空间的任何 job 都互斥。
- fail-open：Redis 不可用 / 获取超时 → 降级为无锁进入（只剩终判查询与
  INSERT 之间的毫秒级窗口，行为不劣于守卫上线前），绝不为锁拦写入。

开关（默认全开）：

- ``ENTITY_DISAMBIGUATION_PREWRITE_RECHECK``：写前二次确认（权威终判）。
- ``ENTITY_DISAMBIGUATION_NAME_LOCK``：同名互斥锁（关后只剩毫秒级窗口，
  仅排障用）。
- ``ENTITY_DISAMBIGUATION_NAME_LOCK_TTL_SECONDS``：持锁上限，默认 120s
  （覆盖写图步调歇速 + 水位退避重试的批级耗时）。
- ``ENTITY_DISAMBIGUATION_NAME_LOCK_WAIT_SECONDS``：获取等待上限，默认 30s
  （超时降级无锁，只告警不阻塞流水）。
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any

from service.entity_disambiguation import normalize_display_name

logger = logging.getLogger(__name__)

# token 比删：只释放自己持有的锁，防把后来者的锁误删
_RELEASE_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


def prewrite_recheck_enabled() -> bool:
    """写前二次确认（权威终判）开关，默认开，``"0"`` 关。"""
    return os.getenv("ENTITY_DISAMBIGUATION_PREWRITE_RECHECK", "1") != "0"


def name_lock_enabled() -> bool:
    """同名互斥锁开关，默认开，``"0"`` 关。"""
    return os.getenv("ENTITY_DISAMBIGUATION_NAME_LOCK", "1") != "0"


def _lock_ttl_seconds() -> int:
    try:
        return max(5, int(os.getenv("ENTITY_DISAMBIGUATION_NAME_LOCK_TTL_SECONDS", "120")))
    except ValueError:
        return 120


def _lock_wait_seconds() -> float:
    try:
        return max(0.0, float(os.getenv("ENTITY_DISAMBIGUATION_NAME_LOCK_WAIT_SECONDS", "30")))
    except ValueError:
        return 30.0


def name_lock_keys(space: str | None, label: str, names: list[str] | set[str]) -> list[str]:
    """同名锁键（排序去重——批内多名按固定序获取，防交叉死锁）。

    name 折叠与消歧同名召回同一套 ``normalize_display_name``，保证「召回判
    同名」与「锁互斥」的口径一致；名字进 md5，避免中文/超长名直接当键。
    """
    keys: set[str] = set()
    for raw in names:
        folded = normalize_display_name(str(raw))
        if not folded:
            continue
        keys.add(f"kg:entity:name:{space or ''}:{label}:{hashlib.md5(folded.encode()).hexdigest()}")
    return sorted(keys)


_client: Any = None


def _redis_client() -> Any:
    """惰性 Redis 客户端（REDIS_URL，与 auth 会话同源；不可用由调用方 fail-open）。"""
    global _client
    if _client is None:
        from redis.asyncio import Redis

        _client = Redis.from_url(
            os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True
        )
    return _client


async def close_name_lock_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def _acquire_pass(keys: list[str], token: str, ttl_ms: int) -> list[str]:
    """一轮 pipeline 批量 SET NX，返回本轮拿到的键（拿不到的留给上层轮询）。"""
    pipe = _redis_client().pipeline(transaction=False)
    for key in keys:
        pipe.set(key, token, nx=True, px=ttl_ms)
    results = await pipe.execute()
    return [key for key, ok in zip(keys, results, strict=True) if ok]


async def _release_quiet(keys: list[str], token: str) -> None:
    if not keys:
        return
    try:
        client = _redis_client()
        pipe = client.pipeline(transaction=False)
        for key in keys:
            pipe.eval(_RELEASE_LUA, 1, key, token)
        await pipe.execute()
    except Exception:  # noqa: BLE001
        logger.warning(
            "同名写锁释放失败（TTL %ss 内自动过期）: keys=%d", _lock_ttl_seconds(), len(keys)
        )


@asynccontextmanager
async def name_write_locks(space: str | None, label: str, names: list[str] | set[str]):
    """同名微锁：包住「写前终判 + INSERT」临界区（详见模块 docstring）。"""
    keys = name_lock_keys(space, label, names)
    if not keys:
        yield
        return
    token = f"wr-{uuid.uuid4().hex}"
    ttl_ms = _lock_ttl_seconds() * 1000
    acquired: list[str] = []
    try:
        deadline = asyncio.get_running_loop().time() + _lock_wait_seconds()
        remaining = keys
        while remaining:
            got = await _acquire_pass(remaining, token, ttl_ms)
            acquired.extend(got)
            remaining = [key for key in remaining if key not in set(got)]
            if not remaining:
                break
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError(f"同名写锁等待超时（{len(remaining)} 个名字被占用）")
            await asyncio.sleep(0.05)
    except Exception as exc:  # noqa: BLE001
        # fail-open：拿到的先还，无锁进入（毫秒级窗口仍在，行为不劣于守卫前）
        logger.warning(
            "同名写锁获取降级为无锁（space=%s label=%s names=%d）: %s",
            space,
            label,
            len(keys),
            exc,
        )
        await _release_quiet(acquired, token)
        acquired = []
    try:
        yield
    finally:
        await _release_quiet(acquired, token)
