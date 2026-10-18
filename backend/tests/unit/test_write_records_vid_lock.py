"""per-VID fail-closed 写锁（P1）+ 损坏旧属性熔断（P2）的单测。

背景（2026-10-18 Codex 二轮评审两个缺口，本文件是其吸收后的正式用例）：

- P1：同名微锁按显示名加键，管不到「无名记录 / 异名同 VID」的并发子集写；
  而 INSERT VERTEX 是整标签覆盖，多来源 asyncio.gather 并行 + 来源内多
  worker 下并发写同 VID 会互相清列。修复 = ``vid_write_locks``（fail-closed）
  包住「FETCH 旧值 → 合并 → INSERT」整个读改写窗口。
- P2：FETCH 返回的旧属性无法解析（JSON 字符串坏）/ 形状异常时，旧实现置
  None 跳过 = 静默回到覆盖清列。修复 = 直接抛 ``GraphRequestError``，
  合并发生在任何 INSERT 之前 → 抛错时本批零写入。

并发断言口径（与 Codex 约定）：并发启动协调在临界区**外**；断言同 VID
读改写临界区最大并发数 = 1、后路 FETCH 读到前路 INSERT 提交后的属性、
终态两列齐全；锁获取失败/等待超时零写入；不同 VID 不被全局串行化。

Redis 桩：monkeypatch 掉 ``entity_write_guard._acquire_pass/_renew_pass/
_release_quiet``（dict 后备），不发真连接；图客户端桩按整标签覆盖语义
维护 vid → props 状态（与真 Nebula 行为一致），FETCH 处设并发探针。
"""

from __future__ import annotations

import asyncio
import re
import threading
import time
from types import SimpleNamespace
from typing import Any

import pytest

from service import entity_write_guard as guard
from service import temporal_workflows as workflows
from service.temporal_workflows import write_records


async def _wait_event(event: threading.Event, timeout_s: float = 5.0) -> None:
    for _ in range(int(timeout_s / 0.01)):
        if event.is_set():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("探针事件等待超时")


_AUDIT_COLS = {"id", "source_table", "create_time", "update_time"}

_INSERT_RE = re.compile(
    r"INSERT VERTEX `(?P<tag>\w+)`\((?P<cols>[^)]*)\) VALUES (?P<rows>.+)$", re.S
)
_ROW_RE = re.compile(r'"(?P<vid>(?:[^"\\]|\\.)*)":\((?P<vals>.*?)\)(?=,\s*"|$)', re.S)


def _split_sql_vals(raw: str) -> list[str]:
    out, buf, in_str, esc = [], [], False, False
    for ch in raw:
        if in_str:
            buf.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
            buf.append(ch)
        elif ch == ",":
            out.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    out.append("".join(buf).strip())
    return out


def _coerce(raw_val: str):
    if raw_val == "NULL":
        return None
    if raw_val in ("true", "false"):
        return raw_val == "true"
    if raw_val.startswith('"'):
        import json

        return json.loads(raw_val)
    try:
        return int(raw_val)
    except ValueError:
        return float(raw_val)


class LockProbeGraphClient:
    """整标签覆盖语义的假图库：INSERT 列集即新状态（未列列清空）。

    FETCH 处有并发探针：in_fetch/max_in_fetch 统计同 VID 读窗口并发数，
    fetch_sleep 拉宽窗口让旧实现（无 VID 锁）必然重叠；fetch_results 按序
    记录每次 FETCH 看到的属性（验证「后路读到前路提交后的状态」）；
    corrupt 非 None 时 FETCH 直接返回该值（P2 注入）。
    """

    state: dict[str, dict] = {}
    write_stmts: list[str] = []
    fetch_results: list[dict] = []
    in_fetch = 0
    max_in_fetch = 0
    fetch_sleep = 0.0
    write_sleep = 0.0
    corrupt: Any = None
    barrier: threading.Barrier | None = None
    _lock = threading.Lock()
    instances: list[LockProbeGraphClient] = []

    def __init__(self, settings=None):
        self.settings = settings
        type(self).instances.append(self)

    def connect(self):
        pass

    def close(self):
        pass

    def execute_read(self, query, *args, **kwargs):
        if query.startswith("DESCRIBE"):
            # 空列集：列类型未知 → 写前必 FETCH（合并路径全覆盖）
            return SimpleNamespace(records=[])
        if query.startswith("FETCH PROP ON"):
            vids = re.findall(r'"([^"]+)"', query)
            with type(self)._lock:
                type(self).in_fetch += 1
                type(self).max_in_fetch = max(type(self).max_in_fetch, type(self).in_fetch)
            try:
                rows = []
                for vid in vids:
                    if type(self).corrupt is not None:
                        props = type(self).corrupt
                    else:
                        props = dict(type(self).state.get(vid) or {})
                    rows.append({"vid": vid, "props": props})
                    type(self).fetch_results.append(
                        {vid: dict(props) if isinstance(props, dict) else props}
                    )
                barrier = type(self).barrier
                if barrier is not None:
                    # 并行探测器：若被全局串行化，先到者在超时后 BrokenBarrier
                    barrier.wait()
                if type(self).fetch_sleep:
                    time.sleep(type(self).fetch_sleep)
                return SimpleNamespace(records=rows)
            finally:
                with type(self)._lock:
                    type(self).in_fetch -= 1
        return SimpleNamespace(records=[])

    def execute_write(self, query, *args, **kwargs):
        if type(self).write_sleep:
            time.sleep(type(self).write_sleep)
        type(self).write_stmts.append(query)
        match = _INSERT_RE.search(query)
        assert match, query
        cols = [c.strip().strip("`") for c in match.group("cols").split(",")]
        for row in _ROW_RE.finditer(match.group("rows")):
            vals = [_coerce(v) for v in _split_sql_vals(row.group("vals"))]
            props = dict(zip(cols, vals, strict=True))
            vid = row.group("vid").replace('\\"', '"')
            # 整标签覆盖：未列出的列重置（与真 Nebula INSERT VERTEX 一致）
            type(self).state[vid] = props
        return SimpleNamespace()


class FakeVidLockRedis:
    """dict 后备的 per-VID 锁桩（替换 _acquire_pass/_renew_pass/_release_quiet）。"""

    store: dict[str, str] = {}
    fail = False  # 注入：Redis 不可用（获取即抛）
    renew_ok = True  # 注入：续期失败
    renew_calls = 0

    @classmethod
    def reset(cls):
        cls.store = {}
        cls.fail = False
        cls.renew_ok = True
        cls.renew_calls = 0


async def _fake_acquire(keys, token, ttl_ms):
    if FakeVidLockRedis.fail:
        raise ConnectionError("redis down")
    got = [k for k in keys if k not in FakeVidLockRedis.store]
    for k in got:
        FakeVidLockRedis.store[k] = token
    return got


async def _fake_renew(keys, token, ttl_ms):
    FakeVidLockRedis.renew_calls += 1
    if not FakeVidLockRedis.renew_ok:
        return False
    return all(FakeVidLockRedis.store.get(k) == token for k in keys)


async def _fake_release(keys, token):
    for k in keys:
        if FakeVidLockRedis.store.get(k) == token:
            del FakeVidLockRedis.store[k]


@pytest.fixture
def vid_lock_env(monkeypatch):
    """图客户端桩 + 锁 Redis 桩；同名锁/终判关掉（隔离 per-VID 锁行为）。"""
    monkeypatch.setattr("infra.graph_db.client.TRSGraphClient", LockProbeGraphClient)
    monkeypatch.setattr(guard, "_acquire_pass", _fake_acquire)
    monkeypatch.setattr(guard, "_renew_pass", _fake_renew)
    monkeypatch.setattr(guard, "_release_quiet", _fake_release)
    LockProbeGraphClient.instances = []
    LockProbeGraphClient.state = {}
    LockProbeGraphClient.write_stmts = []
    LockProbeGraphClient.fetch_results = []
    LockProbeGraphClient.in_fetch = 0
    LockProbeGraphClient.max_in_fetch = 0
    LockProbeGraphClient.fetch_sleep = 0.0
    LockProbeGraphClient.write_sleep = 0.0
    LockProbeGraphClient.corrupt = None
    LockProbeGraphClient.barrier = None
    FakeVidLockRedis.reset()
    monkeypatch.setenv("SCHEMA_EXTRACT_WRITE_PACE_EVERY", "0")
    monkeypatch.setenv("SCHEMA_EXTRACT_WRITE_BATCH_ROWS", "64")
    monkeypatch.setenv("ENTITY_DISAMBIGUATION_PREWRITE_RECHECK", "0")
    monkeypatch.setenv("ENTITY_DISAMBIGUATION_NAME_LOCK", "0")
    # ENTITY_WRITE_VID_LOCK_ENABLED 保持默认开——本文件就是测它
    return LockProbeGraphClient


def _request(records, name="Person"):
    return {
        "kind": "entity",
        "name": name,
        "activeProps": [
            "id",
            "name",
            "scholar_org",
            "h_index",
            "affiliation",
            "source_table",
            "create_time",
            "update_time",
        ],
        "records": records,
        "graph": {"space": "sp1"},
        "sourceTable": "dwd_t",
    }


class TestVidLockKeys:
    def test_keys_sorted_and_cover_nameless(self):
        keys = guard.vid_lock_keys("sp1", "Person", ["b", "a", "a", None, ""])
        assert len(keys) == 2
        assert keys == sorted(keys)
        assert keys[0].startswith("kg:entity:vid:sp1:Person:")
        # 图空间隔离：不同空间同 vid 不是同一把锁
        assert guard.vid_lock_keys("sp2", "Person", ["a"])[0] not in keys


class TestParallelSameVid:
    async def test_parallel_same_vid_without_name_keeps_both_updates(self, vid_lock_env):
        """Codex 探针改造版：无名记录、同 VID 并发两路各写一列。

        断言四件套（临界区外协调并发启动）：
        1) 同 VID 读改写窗口最大并发数 = 1（探针计数）；
        2) 后路 FETCH 读到前路 INSERT 提交后的属性；
        3) 终态两列齐全（不再互相清列）；
        4) 锁全部释放（桩 store 清空）。
        """
        LockProbeGraphClient.fetch_sleep = 0.08  # 拉宽窗口：无锁时必然重叠
        req_a = _request([{"id": "v1", "props": {"id": "v1", "scholar_org": "清华"}}])
        req_b = _request([{"id": "v1", "props": {"id": "v1", "h_index": "5"}}])
        # 并发启动协调在临界区外：gather 直接并发（锁获取在 FETCH 之前）
        await asyncio.gather(write_records(req_a), write_records(req_b))

        assert LockProbeGraphClient.max_in_fetch == 1
        # 两次 FETCH 各自看到的状态：先路见空、后路见先路已提交的列
        fetches = [next(iter(f.values())) for f in LockProbeGraphClient.fetch_results]
        assert len(fetches) == 2
        business = [{k: v for k, v in p.items() if k not in _AUDIT_COLS} for p in fetches]
        assert sorted(len(p) for p in business)[0] == 0  # 先路读到空图
        second = max(business, key=len)
        assert second.get("scholar_org") == "清华" or second.get("h_index") == "5"
        # 终态两列齐全
        final = LockProbeGraphClient.state["v1"]
        assert final["scholar_org"] == "清华" and final["h_index"] == "5"
        assert FakeVidLockRedis.store == {}

    async def test_parallel_diff_name_same_vid_keeps_both_updates(self, vid_lock_env):
        """异名但同 VID：同名锁管不到，VID 锁必须互斥。"""
        LockProbeGraphClient.fetch_sleep = 0.08
        req_a = _request([{"id": "v1", "props": {"id": "v1", "name": "甲", "affiliation": "清华"}}])
        req_b = _request(
            [{"id": "v1", "props": {"id": "v1", "name": "乙", "scholar_org": "计算机系"}}]
        )
        await asyncio.gather(write_records(req_a), write_records(req_b))

        assert LockProbeGraphClient.max_in_fetch == 1
        final = LockProbeGraphClient.state["v1"]
        assert final["affiliation"] == "清华" and final["scholar_org"] == "计算机系"
        assert FakeVidLockRedis.store == {}

    async def test_different_vids_run_concurrently(self, vid_lock_env):
        """不同 VID 不被全局串行化：两路 FETCH 同时在窗口内（Barrier 探测）。"""
        LockProbeGraphClient.barrier = threading.Barrier(2, timeout=6)
        req_a = _request([{"id": "va", "props": {"id": "va", "scholar_org": "清华"}}])
        req_b = _request([{"id": "vb", "props": {"id": "vb", "h_index": "5"}}])
        # 若锁被误做成全局，先到路的 Barrier.wait 会超时炸 BrokenBarrierError
        await asyncio.gather(write_records(req_a), write_records(req_b))

        assert LockProbeGraphClient.max_in_fetch == 2
        assert LockProbeGraphClient.state["va"]["scholar_org"] == "清华"
        assert LockProbeGraphClient.state["vb"]["h_index"] == "5"
        assert FakeVidLockRedis.store == {}


class TestFailClosed:
    async def test_acquire_connection_error_fails_closed_zero_writes(self, vid_lock_env):
        """Redis 不可用：fail-closed——抛错、零写入、不留半持锁。"""
        FakeVidLockRedis.fail = True
        req = _request([{"id": "v1", "props": {"id": "v1", "scholar_org": "清华"}}])
        with pytest.raises(ConnectionError):
            await write_records(req)
        assert LockProbeGraphClient.write_stmts == []
        assert FakeVidLockRedis.store == {}

    async def test_wait_timeout_zero_writes_keeps_others_lock(self, vid_lock_env, monkeypatch):
        """等待超时：抛 TimeoutError、零写入、不误删他人持有的锁。"""
        monkeypatch.setenv("ENTITY_WRITE_VID_LOCK_WAIT_SECONDS", "0.2")
        key = guard.vid_lock_keys("sp1", "Person", ["v1"])[0]
        FakeVidLockRedis.store[key] = "other-token"
        req = _request([{"id": "v1", "props": {"id": "v1", "scholar_org": "清华"}}])
        with pytest.raises(TimeoutError):
            await write_records(req)
        assert LockProbeGraphClient.write_stmts == []
        assert FakeVidLockRedis.store == {key: "other-token"}


class TestLeaseRenewal:
    async def test_renewal_lost_aborts_remaining_chunks(self, vid_lock_env, monkeypatch):
        """续期失败（租期丢失）：chunk 间熔断——后续 chunk 不再写，整批上抛重试。"""
        monkeypatch.setenv("ENTITY_WRITE_VID_LOCK_HEARTBEAT_SECONDS", "0.05")
        FakeVidLockRedis.renew_ok = False
        # 合并读快、chunk 写慢：租期在第一 chunk 写入期间丢失，第二 chunk 被熔断
        LockProbeGraphClient.write_sleep = 0.25
        # 两个不同列集组 = 两个 chunk
        records = [
            {"id": "va", "props": {"id": "va", "scholar_org": "清华"}},
            {"id": "vb", "props": {"id": "vb", "h_index": "5"}},
        ]
        with pytest.raises(RuntimeError, match="VID 写锁"):
            await write_records(_request(records))
        assert len(LockProbeGraphClient.write_stmts) == 1  # 第二 chunk 被中止
        assert FakeVidLockRedis.store == {}  # 失败路径同样释放

    async def test_renewal_lost_after_all_chunks_still_raises(self, vid_lock_env, monkeypatch):
        """单 chunk 已写完但租期丢失：退出临界区仍抛错（不可信写入，重试幂等）。"""
        monkeypatch.setenv("ENTITY_WRITE_VID_LOCK_HEARTBEAT_SECONDS", "0.05")
        FakeVidLockRedis.renew_ok = False
        # 合并读快、唯一 chunk 写慢：租期在写入期间丢失 → 退出临界区时仍抛错
        LockProbeGraphClient.write_sleep = 0.25
        req = _request([{"id": "v1", "props": {"id": "v1", "scholar_org": "清华"}}])
        with pytest.raises(RuntimeError, match="租期丢失"):
            await write_records(req)
        assert len(LockProbeGraphClient.write_stmts) == 1
        assert FakeVidLockRedis.store == {}

    async def test_lease_loss_must_stop_current_chunk_retry(self, vid_lock_env, monkeypatch):
        """失锁后当前 chunk 内的重试不得再派发（Codex 探针吸收，名字沿用）。

        首次 INSERT 抛高水位瞬态，退避睡醒前心跳已报租期丢失——重试必须在
        真正派发前被拦下：只有一次尝试、零成功写入、退出时报租期丢失。
        """
        from infra.graph_db.exceptions import GraphRequestError

        monkeypatch.setenv("ENTITY_WRITE_VID_LOCK_HEARTBEAT_SECONDS", "0.05")
        monkeypatch.setattr(workflows, "_WATERMARK_RETRY_SLEEP_SECONDS", 0.2)
        FakeVidLockRedis.renew_ok = False
        original_write = LockProbeGraphClient.execute_write
        attempts: list[str] = []

        def transient_first_write(self, query, *args, **kwargs):
            attempts.append(query)
            if len(attempts) == 1:
                raise GraphRequestError("high watermark", status_code=503)
            return original_write(self, query, *args, **kwargs)

        monkeypatch.setattr(LockProbeGraphClient, "execute_write", transient_first_write)
        with pytest.raises(RuntimeError, match="租期丢失"):
            await write_records(
                _request([{"id": "v1", "props": {"id": "v1", "scholar_org": "org-A"}}])
            )
        assert FakeVidLockRedis.renew_calls >= 1  # 丢失确实在重试睡醒前被观察到
        assert len(attempts) == 1, "失锁已被心跳观察到，INSERT 仍被再次派发"
        assert LockProbeGraphClient.write_stmts == []


class TestActivityCancellation:
    async def test_cancelled_activity_must_not_unlock_running_write_thread(
        self, vid_lock_env, monkeypatch
    ):
        """活动取消不得在写线程仍在跑时解锁（Codex 探针吸收，名字沿用）。

        旧实现：协程取消 → 上下文立即停心跳/释放锁，同步线程持旧快照继续
        INSERT，与后到写方并发清列。修复语义：取消 → 置停止派发标志 →
        **排空等待在途线程收尾**（期间锁仍被持有）→ 才释放 → 取消上抛。
        """
        fetched = threading.Event()
        resume = threading.Event()
        original_read = LockProbeGraphClient.execute_read
        first = True

        def delayed_read(self, query, *args, **kwargs):
            nonlocal first
            result = original_read(self, query, *args, **kwargs)
            if query.startswith("FETCH PROP ON") and first:
                first = False
                fetched.set()
                assert resume.wait(5), "探针未放行，写线程收尾卡死"
            return result

        monkeypatch.setattr(LockProbeGraphClient, "execute_read", delayed_read)
        task = asyncio.create_task(
            write_records(_request([{"id": "v1", "props": {"id": "v1", "scholar_org": "org-A"}}]))
        )
        try:
            await _wait_event(fetched)
            task.cancel()
            await asyncio.sleep(0.1)  # 取消已送达、排空中：线程仍暂停在 FETCH
            # 排空期间锁必须仍被持有——后到写方此刻无法插队获取
            assert FakeVidLockRedis.store, "取消排空期间 VID 写锁被提前释放"
            resume.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            # 排空完成才释放；被取消的写方未派发任何 INSERT（旧快照不再落图）
            assert FakeVidLockRedis.store == {}
            assert LockProbeGraphClient.write_stmts == []
            # 后到写方照常落列，不会被已取消的旧快照覆盖
            await write_records(_request([{"id": "v1", "props": {"id": "v1", "h_index": "5"}}]))
            assert LockProbeGraphClient.state["v1"]["h_index"] == "5"
        finally:
            resume.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)


class TestRepeatedCancellation:
    async def test_repeated_cancel_during_drain_keeps_loop_and_heartbeat_alive(
        self, vid_lock_env, monkeypatch
    ):
        """排空期间的重复取消：事件循环与心跳必须保持可调度（Codex 三轮 P1）。

        旧实现排空循环裸 await write_task：二次取消传染给工作任务后，循环反复
        await 已取消任务、立即抛错且不让出——同循环上一切协程（含锁心跳）饿
        死。修复语义：排空等待持续 shield，外层重复取消只被吸收、继续等线程
        收尾；期间锁仍持有、心跳仍在续期。
        """
        monkeypatch.setenv("ENTITY_WRITE_VID_LOCK_HEARTBEAT_SECONDS", "0.05")
        fetched = threading.Event()
        resume = threading.Event()
        original_read = LockProbeGraphClient.execute_read
        first = True

        def delayed_read(self, query, *args, **kwargs):
            nonlocal first
            result = original_read(self, query, *args, **kwargs)
            if query.startswith("FETCH PROP ON") and first:
                first = False
                fetched.set()
                assert resume.wait(5), "探针未放行，写线程收尾卡死"
            return result

        monkeypatch.setattr(LockProbeGraphClient, "execute_read", delayed_read)
        task = asyncio.create_task(
            write_records(_request([{"id": "v1", "props": {"id": "v1", "scholar_org": "org-A"}}]))
        )
        try:
            await _wait_event(fetched)
            task.cancel()  # 第一次取消：进入排空
            await asyncio.sleep(0.1)
            assert FakeVidLockRedis.store, "排空期间 VID 写锁被提前释放"
            renew_before = FakeVidLockRedis.renew_calls
            # 第二、三次取消：每次后事件循环必须仍能调度（旧实现在此忙等冻结）
            task.cancel()
            await asyncio.sleep(0.05)
            task.cancel()
            await asyncio.sleep(0.05)
            # 心跳在排空期间持续续期 = 同循环协程未被饿死
            assert FakeVidLockRedis.renew_calls > renew_before, "排空期间锁心跳被饿死"
            assert FakeVidLockRedis.store, "重复取消后 VID 写锁被提前释放"
            resume.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert FakeVidLockRedis.store == {}
            assert LockProbeGraphClient.write_stmts == []
        finally:
            resume.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    async def test_cancel_during_inflight_insert_no_further_dispatch(
        self, vid_lock_env, monkeypatch
    ):
        """在途 INSERT 阶段（而非 FETCH 阶段）取消：已派发的在途语句允许完成，
        取消之后不得再追加任何派发；排空期间持锁，结束后才释放。"""
        monkeypatch.setenv("ENTITY_WRITE_VID_LOCK_HEARTBEAT_SECONDS", "0.05")
        inflight = threading.Event()
        resume = threading.Event()
        original_write = LockProbeGraphClient.execute_write

        def paused_first_write(self, query, *args, **kwargs):
            if not LockProbeGraphClient.write_stmts:
                inflight.set()
                assert resume.wait(5), "探针未放行，在途 INSERT 卡死"
            return original_write(self, query, *args, **kwargs)

        monkeypatch.setattr(LockProbeGraphClient, "execute_write", paused_first_write)
        # 两个不同列集组 = 两个 chunk：第一 chunk 在途暂停，第二 chunk 待派发
        records = [
            {"id": "va", "props": {"id": "va", "scholar_org": "清华"}},
            {"id": "vb", "props": {"id": "vb", "h_index": "5"}},
        ]
        task = asyncio.create_task(write_records(_request(records)))
        try:
            await _wait_event(inflight)
            task.cancel()
            await asyncio.sleep(0.1)
            assert FakeVidLockRedis.store, "在途 INSERT 排空期间 VID 写锁被提前释放"
            renew_before = FakeVidLockRedis.renew_calls
            await asyncio.sleep(0.1)
            assert FakeVidLockRedis.renew_calls > renew_before, "排空期间锁心跳被饿死"
            resume.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            # 第一 chunk 取消前已派发、允许完成；第二 chunk 被熔断，零追加派发
            assert len(LockProbeGraphClient.write_stmts) == 1
            assert "va" in LockProbeGraphClient.state
            assert "vb" not in LockProbeGraphClient.state
            assert FakeVidLockRedis.store == {}
        finally:
            resume.set()
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)


class TestCorruptExistingProps:
    async def test_corrupt_existing_properties_must_not_allow_overwrite(self, vid_lock_env):
        """P2：图上旧属性是无法解析的字符串 → 抛错 + 零写入（Codex 探针名沿用）。"""
        from infra.graph_db.exceptions import GraphRequestError

        LockProbeGraphClient.corrupt = '{"scholar_org": "清华"'  # 坏 JSON
        LockProbeGraphClient.state["v1"] = {"id": "v1"}  # 已存在记录才走合并 FETCH
        req = _request([{"id": "v1", "props": {"id": "v1", "h_index": "5"}}])
        with pytest.raises(GraphRequestError, match="旧属性无法解析"):
            await write_records(req)
        # 合并先于一切 INSERT：抛错时本批零写入
        assert LockProbeGraphClient.write_stmts == []
        assert FakeVidLockRedis.store == {}

    async def test_non_dict_existing_properties_must_not_allow_overwrite(self, vid_lock_env):
        """P2：旧属性形状异常（非 dict）→ 同样抛错 + 零写入。"""
        from infra.graph_db.exceptions import GraphRequestError

        LockProbeGraphClient.corrupt = 12345
        LockProbeGraphClient.state["v1"] = {"id": "v1"}
        req = _request([{"id": "v1", "props": {"id": "v1", "h_index": "5"}}])
        with pytest.raises(GraphRequestError, match="形状异常"):
            await write_records(req)
        assert LockProbeGraphClient.write_stmts == []
        assert FakeVidLockRedis.store == {}
