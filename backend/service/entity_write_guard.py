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
并发写同一 VID 时在同一把锁上互斥。临界区内起**心跳线程**（daemon）按
TTL/3 间隔续租（与异步心跳同间隔口径、共用 ``_RENEW_LUA``）——在途图请求
阻塞写线程期间租约仍持续有效（Redis 健康、只是请求慢时，第二写者结构性
拿不到锁，互斥保持）；续租失败置共享 lost 标记并自停。写路径各边界（长耗
时步骤后 / 写派发前 / 写返回后）校验租约，丢失抛 ``VidWriteLeaseLostError``
禁写/熔断（防按过期快照整标签覆盖清掉已接管写者的列——单次 SET NX PX 后
临界区耗时超过 TTL 即出现该窗口）。
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import threading
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
# 租约生命周期与异步版对齐：临界区内起**心跳线程**按 TTL/3 续租（在途写
# 期间租约持续有效），叠加边界续租（长耗时步骤后 / 写派发前 / 写返回后由
# 调用方经租约句柄校验），丢失一律 fail-closed 抛错禁写。
# ---------------------------------------------------------------------------

_SYNC_HEARTBEAT_JOIN_SECONDS = 5.0
"""心跳线程收尾 join 上限。

正常收尾是瞬时的（stop 事件即时唤醒等待中的心跳）；上限只兜「续租调用
本身卡死」的病态场景——超时告警后**放弃等待**（绝不因心跳卡死而挂起请求
线程；daemon 线程也不阻塞进程退出）。被放弃的心跳若之后自行恢复，迟到的
续租/释放经 token 比对自然 no-op，不会误伤接管者的锁。"""

_sync_client: Any = None


def _monotonic() -> float:
    """单调时钟接缝：生产恒等于 ``time.monotonic``，测试可替换成可拨动的
    固定时钟，确定性复现「临界区跨过 TTL → 租约过期被接管」。"""
    return time.monotonic()


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
    """单键 ``SET key token NX PX ttl``（测试经假同步客户端注入）。"""
    return bool(_redis_client_sync().set(key, token, nx=True, px=ttl_ms))


def _renew_sync(key: str, token: str, ttl_ms: int) -> bool:
    """单键续租：token 校验通过才 PEXPIRE。

    与异步版 ``_renew_pass`` **共用同一段 ``_RENEW_LUA``**（不另造一套语义
    不同的脚本）；任何异常（Redis 不可用等）按续租失败处理——无法证明仍
    持有就当作丢失（fail-closed，宁中止不冒险）。
    """
    try:
        return bool(_redis_client_sync().eval(_RENEW_LUA, 1, key, token, ttl_ms))
    except Exception:  # noqa: BLE001
        logger.warning("VID 写锁（同步）续租异常，按租约丢失处理: key=%s", key, exc_info=True)
        return False


def _release_sync_quiet(key: str, token: str) -> None:
    """token 比删单键（Lua 同异步版共用）；失败仅告警，TTL 兜底自愈。"""
    try:
        _redis_client_sync().eval(_RELEASE_LUA, 1, key, token)
    except Exception:  # noqa: BLE001
        logger.warning(
            "VID 写锁（同步）释放失败（TTL %ss 内自动过期）: key=%s", _lock_ttl_seconds(), key
        )


class VidWriteLeaseLostError(RuntimeError):
    """同步 VID 写锁租约丢失（临界区跨过 TTL 被他人接管 / 续租失败）。

    语义类似 LeaseLost：收到本错误的写入方**禁止再派发任何新的写语句**——
    按过期快照继续整标签 INSERT 会静默清掉已接管写者落下的列且全程不抛错
    （Codex 探针 2026-10-19 复现）；上层事务回滚后整体重试（写图幂等）。
    写已派发后才丢失（在途窗口）时图写可能已落地——抛错只阻止后续写并让
    事务回滚，**不假装能回滚图库**（与 #526 异步版在途窗口同级）。
    """


class _SyncVidLease:
    """``vid_write_lock_sync`` 临界区内的租约句柄（边界校验 + 心跳兜底）。

    临界区内的心跳线程按 TTL/3 持续续租（见 :class:`_SyncLeaseHeartbeat`），
    失败置共享 ``lost`` 标记；句柄方法在写路径各边界校验租约：

    - ``refresh_if_aged()``：距上次续租超过阈值（默认 TTL/3，与异步心跳
      同间隔口径）时续租——慢 FETCH 等长耗时步骤后拉长后续写窗口；
    - ``ensure_lease()``：**派发新写语句前必须调用**——无条件续租并校验
      持有权，失败抛 :class:`VidWriteLeaseLostError` 禁止继续写；
    - ``raise_if_lost()``：**写语句返回后必须调用**——在途期间心跳判丢
      （Redis 故障窗口）则抛错熔断后续写（图写可能已落地，见类 docstring）。

    锁关闭/无键时 contextmanager yield 的空租约三个方法均为 no-op，调用方
    无需分支判断。
    """

    __slots__ = ("key", "token", "ttl_ms", "_threshold", "_renewed_at", "_lost")

    def __init__(
        self, key: str | None, token: str = "", ttl_ms: int = 0, lost: dict | None = None
    ) -> None:
        self.key = key
        self.token = token
        self.ttl_ms = ttl_ms
        self._threshold = _vid_heartbeat_interval(ttl_ms / 1000) if ttl_ms else 0.0
        self._renewed_at = _monotonic()
        # 心跳线程与请求线程共享的丢失标记（空租约不共享：恒为未丢失）
        self._lost = lost if lost is not None else {}

    def _renew(self) -> bool:
        ok = _renew_sync(self.key or "", self.token, self.ttl_ms)
        if ok:
            self._renewed_at = _monotonic()
        return ok

    def raise_if_lost(self) -> None:
        """写返回后校验：心跳已判丢 → 抛错熔断（图写可能已落地，不假装能回滚）。"""
        if self.key is not None and self._lost.get("lost"):
            raise VidWriteLeaseLostError(
                f"VID 写锁（同步）在途写期间租约丢失（key={self.key}）——已派发"
                "的图写可能已落地且不可取消：submit 回滚使案件不前移，重提重新"
                "FETCH 合并即可收敛；后续写全部熔断"
            )

    def refresh_if_aged(self) -> None:
        """距上次续租超过 TTL/3 → 续租；心跳已判丢/续不上按租约丢失熔断。"""
        if self.key is None:
            return
        self.raise_if_lost()
        if _monotonic() - self._renewed_at < self._threshold:
            return
        if not self._renew():
            raise VidWriteLeaseLostError(
                f"VID 写锁（同步）临界区耗时过长且续租失败（key={self.key}）"
                "——中止写入，防按过期快照整标签覆盖"
            )

    def ensure_lease(self) -> None:
        """写派发前必须续租并校验持有权；失败抛错，禁止新的 INSERT。"""
        if self.key is None:
            return
        self.raise_if_lost()
        if not self._renew():
            raise VidWriteLeaseLostError(
                f"VID 写锁（同步）租约丢失（key={self.key}）——禁止按过期快照继续写，整体重试"
            )


class _SyncLeaseHeartbeat:
    """同步租约心跳线程：TTL/3 续租，续租失败置 lost 并自停。

    独立于（可能阻塞在图请求上的）写线程运行——这是在途写期间租约持续
    有效的关键：Redis 健康、只是图请求慢时，心跳把 TTL 不断拉满，第二写
    者结构性拿不到锁，互斥保持。``time.sleep`` 换 ``Event.wait`` 使 stop
    可即时打断；daemon=True 使进程退出不被卡死的心跳拖住。
    """

    def __init__(self, key: str, token: str, ttl_ms: int, lost: dict) -> None:
        self._key = key
        self._token = token
        self._ttl_ms = ttl_ms
        self._lost = lost
        self._interval = _vid_heartbeat_interval(ttl_ms / 1000)
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name=f"vid-lease-hb-{key.rsplit(':', 1)[-1][:12]}",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    @property
    def _ever_started(self) -> bool:
        # 未启动的线程 join 会 RuntimeError；ident 非空即至少启动过一次
        return self._thread.ident is not None

    def _run(self) -> None:
        try:
            while not self._stop.wait(self._interval):
                if not _renew_sync(self._key, self._token, self._ttl_ms):
                    self._lost["lost"] = True
                    logger.error(
                        "VID 写锁（同步）心跳续租失败，标记租约丢失（key=%s）——"
                        "在途/后续写将被熔断，本批需整体重试",
                        self._key,
                    )
                    return
        except BaseException:  # noqa: BLE001 — 心跳线程任何异常都按租约丢失处理
            self._lost["lost"] = True
            logger.exception("VID 写锁（同步）心跳线程异常退出，标记租约丢失（key=%s）", self._key)

    def stop(self, join_timeout: float) -> None:
        """通知心跳退出并等待收尾；超时告警后**放弃等待**，不挂起请求线程。"""
        self._stop.set()
        if not self._ever_started:
            return  # start() 未成功（创建失败已在进入临界区前释放锁上抛）
        self._thread.join(join_timeout)
        if self._thread.is_alive():
            logger.warning(
                "VID 写锁（同步）心跳线程 %.1fs 内未收尾（续租调用卡住？key=%s）——"
                "放弃等待（daemon 线程不阻塞请求/进程退出）；迟到的续租经 token "
                "比对自然 no-op，不误伤接管者的锁",
                join_timeout,
                self._key,
            )


@contextmanager
def vid_write_lock_sync(space: str | None, label: str, vid) -> Iterator[_SyncVidLease]:
    """同步 per-VID fail-closed 微锁（人工审核 T_LINK 裁决写图路径专用）。

    与异步版同键/同开关/同 TTL/同 token 比删，**fail-closed**：获取失败
    （Redis 不可用）/ 等待超时直接抛错，绝不无锁进入——无锁并发子集写在
    整标签覆盖语义下 = 确定性丢列；调用方（裁决 submit）事务回滚后重新
    提交即重试（合并后 INSERT 幂等）。

    租约生命周期与异步版对齐：**临界区内起心跳线程**（``_SyncLeaseHeartbeat``，
    daemon）按 TTL/3 续租——在途 INSERT 阻塞写线程期间租约持续有效，Redis
    健康只是请求慢时第二写者结构性拿不到锁（Codex 第三轮探针的丢列形状在
    该语义下不可发生）。调用方仍需边界校验（防御纵深）：长耗时步骤后
    ``refresh_if_aged()``、**每次派发新写语句前** ``ensure_lease()``、写语句
    返回后 ``raise_if_lost()``——丢失抛 :class:`VidWriteLeaseLostError` 禁止
    新的/后续的写。不加保护的缺陷形状（Codex 探针 2026-10-19 复现）：单次
    ``SET key token NX PX ttl`` 后，临界区耗时超过 TTL（慢图请求、两次
    FETCH、线程暂停、网络阻塞、可配置的短 TTL）租约即过期，另一写者可获同
    键锁写入；原写者按旧快照 INSERT 在整标签覆盖语义下清掉对方列，全程不
    抛错——token 比删只防误删后来者锁，不防原写者过期后继续覆盖。

    **收尾语义**：with 退出时先 stop+join 心跳（上限
    ``_SYNC_HEARTBEAT_JOIN_SECONDS``，正常收尾瞬时完成；续租调用卡死时超时
    告警放弃等待，绝不因心跳挂起请求线程），再 token 比删释放；租约已丢失
    时比删自然 no-op（不误删接管者的锁）。临界区正常走完但租约曾丢失（body
    未自行抛错）时，退出时同样抛 :class:`VidWriteLeaseLostError`（与异步版
    口径一致——lost 即不可信，整体重试）。

    **在途边界（诚实声明）**：派发后的 INSERT 无法取消、事后抛错不能回滚
    图库。心跳把残余窗口压到「Redis 故障窗口内（续租连不上）且在途请求
    停滞超过剩余 TTL」——与 #526 异步版心跳续期通过后、下一次心跳前 Redis
    故障的在途窗口同级，不可消除；届时图写可能已落地，本锁的处置是抛错让
    submit 回滚（案件不前移、零后续写），重提重新 FETCH 合并收敛（合并语义
    保留接管者落下的列），不假装能回滚图库。

    不以调大 TTL 替代正确性修复（TTL 只是持锁方崩溃的自愈兜底）。
    """
    keys = vid_lock_keys(space, label, [vid])
    if not keys or not vid_lock_enabled():
        yield _SyncVidLease(None)
        return
    key = keys[0]
    token = f"wr-{uuid.uuid4().hex}"
    ttl_ms = _lock_ttl_seconds() * 1000
    deadline = _monotonic() + _vid_lock_wait_seconds()
    while not _acquire_sync(key, token, ttl_ms):
        if _monotonic() >= deadline:
            raise TimeoutError(f"VID 写锁等待超时（{label} 的同 VID 写入正在进行，稍后重试）")
        time.sleep(0.05)
    lost: dict[str, Any] = {}
    lease = _SyncVidLease(key, token, ttl_ms, lost)
    heartbeat = _SyncLeaseHeartbeat(key, token, ttl_ms, lost)
    try:
        heartbeat.start()
    except BaseException:  # 线程创建失败（资源耗尽）：先释放刚拿到的锁再上抛
        _release_sync_quiet(key, token)
        raise
    body_failed = False
    try:
        yield lease
    except BaseException:
        body_failed = True
        raise
    finally:
        # 先收心跳再释放：正常瞬时完成；心跳卡死时超时放弃，不挂起请求线程
        heartbeat.stop(_SYNC_HEARTBEAT_JOIN_SECONDS)
        _release_sync_quiet(key, token)
    if not body_failed and lost.get("lost"):
        raise VidWriteLeaseLostError(
            f"VID 写锁（同步）租约在临界区内丢失（key={key}）——本批写入不可信，"
            "整体重试（写图幂等，重提重新 FETCH 合并收敛）"
        )
