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

另有 **per-VID 写锁**（``vid_write_locks``，2026-10-18 实体列保留修复引入）：
锁的是「FETCH 旧值 → 合并 → INSERT」读改写窗口，按 (graph_space, label, vid)
加键，无名记录/异名同 VID 同样互斥。与同名锁分野：同名锁保消歧活性
（fail-open），VID 锁保数据正确性（**fail-closed**——拿不到/续期失败宁可
让活动重试，不冒丢列风险；代价是 Redis 成为实体写路径的硬依赖）。开关：

- ``ENTITY_WRITE_VID_LOCK_ENABLED``：默认开，``"0"`` 关（仅排障/语句形状单测）。
- ``ENTITY_WRITE_VID_LOCK_WAIT_SECONDS``：获取等待上限，默认 30s（超时抛错重试）。
- ``ENTITY_WRITE_VID_LOCK_HEARTBEAT_SECONDS``：续期心跳间隔，默认 TTL/3。

同步写路径（人工审核 T_LINK 裁决写图）用 ``vid_write_lock_sync``：与异步版
同键/同开关/同 fail-closed 语义（详见其 docstring），人工裁决与工作流写图
并发写同一 VID 时在同一把锁上互斥。
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
import uuid
from collections.abc import Iterator
from contextlib import asynccontextmanager, contextmanager
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


# ---------------------------------------------------------------------------
# per-VID 写锁（fail-closed）：包住实体写图的「FETCH 旧值 → 合并 → INSERT」
# 读改写窗口。多来源 asyncio.gather 并行 / 来源内多 worker 下，同名锁只按
# 显示名加键——无名记录不进锁、异名同 VID 不互斥；而 INSERT VERTEX 是整标签
# 覆盖，并发子集写会互相清列。VID 锁补上这个互斥面，且**不降级**：
# 获取失败/等待超时/续期失败 → 抛错让活动层整批重试（幂等），绝无锁写入。
# ---------------------------------------------------------------------------

_RENEW_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('pexpire', KEYS[1], ARGV[2])
end
return 0
"""


def vid_lock_enabled() -> bool:
    """per-VID 写锁开关，默认开，``"0"`` 关（仅排障/语句形状单测）。"""
    return os.getenv("ENTITY_WRITE_VID_LOCK_ENABLED", "1") != "0"


def _vid_lock_wait_seconds() -> float:
    try:
        return max(0.0, float(os.getenv("ENTITY_WRITE_VID_LOCK_WAIT_SECONDS", "30")))
    except ValueError:
        return 30.0


def _vid_heartbeat_interval(ttl_seconds: float) -> float:
    """续期间隔：默认 TTL/3；允许显式覆盖（单测提速用）。"""
    raw = os.getenv("ENTITY_WRITE_VID_LOCK_HEARTBEAT_SECONDS")
    if raw:
        try:
            return max(0.05, float(raw))
        except ValueError:
            pass
    return max(0.2, ttl_seconds / 3)


def vid_lock_keys(space: str | None, label: str, vids) -> list[str]:
    """per-VID 锁键（排序去重——批内多 vid 按固定序获取，防交叉死锁）。

    键按 vid 而非显示名：无名记录、异名同 VID 都落在同一把锁上。vid 进
    md5 与同名锁同理（键长可控、避开特殊字符）。
    """
    keys: set[str] = set()
    for raw in vids:
        vid = str(raw or "").strip()
        if vid:
            keys.add(f"kg:entity:vid:{space or ''}:{label}:{hashlib.md5(vid.encode()).hexdigest()}")
    return sorted(keys)


async def _renew_pass(keys: list[str], token: str, ttl_ms: int) -> bool:
    """pipeline 续期全部键（Lua 校验 token 才 PEXPIRE）；任一未续上返回 False。"""
    pipe = _redis_client().pipeline(transaction=False)
    for key in keys:
        pipe.eval(_RENEW_LUA, 1, key, token, ttl_ms)
    results = await pipe.execute()
    return all(bool(ok) for ok in results)


async def _vid_lock_heartbeat(keys: list[str], token: str, ttl_ms: int, lost: dict) -> None:
    """持锁心跳：TTL/3 续期一次；续期失败即标记丢失（写入方据此中止/整体重试）。"""
    interval = _vid_heartbeat_interval(ttl_ms / 1000)
    try:
        while True:
            await asyncio.sleep(interval)
            if not await _renew_pass(keys, token, ttl_ms):
                lost["lost"] = True
                logger.error("VID 写锁续期失败，标记丢失（keys=%d）——本批写入需整体重试", len(keys))
                return
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        lost["lost"] = True
        logger.error("VID 写锁心跳异常，标记丢失: %s", exc)


@asynccontextmanager
async def vid_write_locks(space: str | None, label: str, vids, *, lost: dict | None = None):
    """per-VID fail-closed 微锁（详见模块 docstring）。

    ``lost`` 是调用方持有的共享标记：心跳续期失败时置 ``lost["lost"]=True``，
    写入方在 chunk 间检查并中止；即便最后一 chunk 已写完，退出临界区时仍会
    抛错让活动层重试（写图幂等，重试安全）。
    """
    keys = vid_lock_keys(space, label, vids)
    if lost is None:
        lost = {}
    if not keys:
        yield lost
        return
    token = f"wr-{uuid.uuid4().hex}"
    ttl_ms = _lock_ttl_seconds() * 1000
    acquired: list[str] = []
    # fail-closed：与同名锁不同，这里任何失败都上抛（获取途中失败也先归还
    # 已拿到的键），绝不降级无锁——无锁并发子集写 = 确定性丢列
    deadline = asyncio.get_running_loop().time() + _vid_lock_wait_seconds()
    remaining = keys
    try:
        while remaining:
            got = await _acquire_pass(remaining, token, ttl_ms)
            acquired.extend(got)
            remaining = [key for key in remaining if key not in set(got)]
            if not remaining:
                break
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError(
                    f"VID 写锁等待超时（{len(remaining)}/{len(keys)} 个 vid 被占用）"
                )
            await asyncio.sleep(0.05)
    except BaseException:
        await _release_quiet(acquired, token)
        raise
    heartbeat = asyncio.create_task(_vid_lock_heartbeat(acquired, token, ttl_ms, lost))
    body_failed = False
    try:
        yield lost
    except BaseException:
        body_failed = True
        raise
    finally:
        heartbeat.cancel()
        try:
            await heartbeat
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001
            logger.exception("VID 写锁心跳任务收尾异常")
        await _release_quiet(acquired, token)
    if not body_failed and lost.get("lost"):
        raise RuntimeError("VID 写锁租期丢失，本批写入不可信——活动层将整批重试（写图幂等）")


# ---------------------------------------------------------------------------
# 同步版 per-VID 写锁（人工审核裁决等同步写路径）：与 ``vid_write_locks``
# 同键（``vid_lock_keys``）、同开关（ENTITY_WRITE_VID_LOCK_ENABLED）、同
# TTL/等待上限、同 token 比删——人工裁决与工作流写图并发写同一 VID 时落在
# 同一把锁上互斥（INSERT VERTEX 整标签覆盖，跨路径无互斥 = 确定性丢列）。
# ---------------------------------------------------------------------------

_sync_client: Any = None


def _redis_client_sync() -> Any:
    """惰性同步 Redis 客户端（与 async 客户端同一 ``REDIS_URL``）。

    ``redis.Redis`` 连接池线程安全；提交裁决的同步处理器跑在线程池里，
    进程内单例复用即可。不可用由调用方 fail-closed（上抛，不降级无锁）。
    """
    global _sync_client
    if _sync_client is None:
        import redis

        _sync_client = redis.Redis.from_url(
            os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=True
        )
    return _sync_client


def _acquire_sync(key: str, token: str, ttl_ms: int) -> bool:
    """单键 ``SET key token NX PX ttl``（测试经本函数注入假客户端）。"""
    return bool(_redis_client_sync().set(key, token, nx=True, px=ttl_ms))


def _release_sync_quiet(key: str, token: str) -> None:
    """token 比删单键（Lua 同异步版共用）；失败仅告警，TTL 兜底自愈。"""
    try:
        _redis_client_sync().eval(_RELEASE_LUA, 1, key, token)
    except Exception:  # noqa: BLE001
        logger.warning(
            "VID 写锁（同步）释放失败（TTL %ss 内自动过期）: key=%s", _lock_ttl_seconds(), key
        )


@contextmanager
def vid_write_lock_sync(space: str | None, label: str, vid) -> Iterator[None]:
    """同步 per-VID fail-closed 微锁（人工审核 T_LINK 裁决写图路径专用）。

    语义与 ``vid_write_locks`` 完全一致，仅缺心跳续期：人工裁决临界区是
    单点「FETCH 旧值 → 合并 → INSERT」（秒级），TTL（默认 120s）远盖得住
    且兜底崩溃自愈；批量长窗口写图仍走异步版（带 TTL/3 心跳）。

    **fail-closed**：获取失败（Redis 不可用）/ 等待超时直接抛错，绝不无锁
    进入——无锁并发子集写在整标签覆盖语义下 = 确定性丢列；调用方（裁决
    submit）事务回滚后重新提交即重试（合并后 INSERT 幂等）。
    """
    keys = vid_lock_keys(space, label, [vid])
    if not keys or not vid_lock_enabled():
        yield
        return
    key = keys[0]
    token = f"wr-{uuid.uuid4().hex}"
    ttl_ms = _lock_ttl_seconds() * 1000
    deadline = time.monotonic() + _vid_lock_wait_seconds()
    while not _acquire_sync(key, token, ttl_ms):
        if time.monotonic() >= deadline:
            raise TimeoutError(f"VID 写锁等待超时（{label} 的同 VID 写入正在进行，稍后重试）")
        time.sleep(0.05)
    try:
        yield
    finally:
        _release_sync_quiet(key, token)
