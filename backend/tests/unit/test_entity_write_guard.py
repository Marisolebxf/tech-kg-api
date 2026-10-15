"""消歧写前守卫测试：同名微锁（获取/释放/互斥/fail-open）+ 写前终判三分支
+ 并发同名双写竞态根治（关锁确定性复现老 bug → 开锁后恰一节点）。

竞态背景（gkx_verify_1 2026-10-10 两个「汪小红」）：并行批次各自的召回跑在
对方 INSERT 落地之前 → 双判「无候选」→ 同名双写。守卫 = 写前权威终判 +
同名互斥锁包住「终判 + INSERT」。
"""

from __future__ import annotations

import asyncio
import json
import re
from types import SimpleNamespace
from typing import Any

import pytest

from service import entity_write_guard as guard
from service.temporal_workflows import write_records

# ---------------------------------------------------------------------------
# 假 Redis（async SET NX / pipeline / Lua eval 的最小实现）
# ---------------------------------------------------------------------------


class FakePipeline:
    def __init__(self, redis: FakeLockRedis) -> None:
        self._redis = redis
        self._set_ops: list[tuple[str, str, bool]] = []
        self._eval_ops: list[tuple[str, str]] = []

    def set(self, key: str, value: str, nx: bool = False, px: int | None = None) -> FakePipeline:
        self._set_ops.append((key, value, nx))
        return self

    def eval(self, script: str, numkeys: int, key: str, token: str) -> FakePipeline:
        self._eval_ops.append((key, token))
        return self

    async def execute(self) -> list[Any]:
        results = [await self._redis.set(key, value, nx=nx) for key, value, nx in self._set_ops]
        results.extend([await self._redis.eval("", 1, key, token) for key, token in self._eval_ops])
        return results


class FakeLockRedis:
    """单事件循环内的原子 SET NX 桩（协程内无 await 点，天然原子）。"""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.fail = False  # 注入：Redis 不可用

    async def set(self, key: str, value: str, nx: bool = False, px: int | None = None):
        if self.fail:
            raise ConnectionError("redis down")
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    def pipeline(self, transaction: bool = True) -> FakePipeline:
        return FakePipeline(self)

    async def eval(self, script: str, numkeys: int, key: str, token: str) -> int:
        if self.store.get(key) == token:
            del self.store[key]
            return 1
        return 0


@pytest.fixture
def fake_lock_redis(monkeypatch: pytest.MonkeyPatch) -> FakeLockRedis:
    fake = FakeLockRedis()
    monkeypatch.setattr(guard, "_client", fake)
    return fake


# ---------------------------------------------------------------------------
# 锁本体
# ---------------------------------------------------------------------------


class TestNameWriteLocks:
    def test_keys_sorted_normalized(self):
        keys = guard.name_lock_keys("sp1", "Person", ["汪小红", "张三", " 汪小红 "])
        assert len(keys) == 2
        assert keys == sorted(keys)
        assert keys[0].startswith("kg:entity:name:sp1:Person:")
        # 图空间隔离：不同空间的同名不是同一把锁
        assert guard.name_lock_keys("sp2", "Person", ["汪小红"])[0] not in keys

    async def test_acquire_and_release(self, fake_lock_redis):
        async with guard.name_write_locks("sp1", "Person", ["汪小红"]):
            assert len(fake_lock_redis.store) == 1
        assert fake_lock_redis.store == {}

    async def test_timeout_degrades_and_keeps_others_lock(self, fake_lock_redis):
        # 锁被他人持有且等待为 0：fail-open 进入（不抛错），且退出不误删他人的锁
        key = guard.name_lock_keys("sp1", "Person", ["汪小红"])[0]
        fake_lock_redis.store[key] = "other-token"
        async with guard.name_write_locks("sp1", "Person", ["汪小红"]):
            assert fake_lock_redis.store[key] == "other-token"
        assert fake_lock_redis.store[key] == "other-token"

    async def test_fail_open_on_redis_error(self, fake_lock_redis):
        fake_lock_redis.fail = True
        # Redis 不可用：不抛错、无锁进入（行为退回守卫前）
        async with guard.name_write_locks("sp1", "Person", ["汪小红", "张三"]):
            assert fake_lock_redis.store == {}
        assert fake_lock_redis.store == {}

    async def test_mutual_exclusion_same_name(self, fake_lock_redis):
        inside = 0
        overlaps: list[int] = []
        entered = asyncio.Event()
        release = asyncio.Event()

        async def hold(name: str, first: bool) -> None:
            nonlocal inside
            async with guard.name_write_locks("sp1", "Person", [name]):
                inside += 1
                overlaps.append(inside)
                if first:
                    entered.set()
                    await release.wait()
                inside -= 1

        async def waiter() -> None:
            await entered.wait()
            await asyncio.sleep(0.01)  # 给第二个协程轮询锁的机会
            assert inside == 1  # 持锁期间他人进不来
            release.set()

        await asyncio.gather(hold("汪小红", True), hold("汪小红", False), waiter())
        assert overlaps == [1, 1]  # 两度进入，从不同时

    async def test_different_names_do_not_block(self, fake_lock_redis):
        async with (
            guard.name_write_locks("sp1", "Person", ["汪小红"]),
            guard.name_write_locks("sp1", "Person", ["张三"]),
        ):
            assert len(fake_lock_redis.store) == 2  # 异名两把锁同时持有


def test_guard_helpers_do_not_shadow_activity_decorators():
    """回归：helper 插进 @activity.defn 与函数之间会把真活动顶成裸函数，
    worker 启动即炸（resolve/write 曾两次踩中）——断言注册表完好。"""
    from temporalio import activity

    import service.temporal_workflows as wf

    def _is_activity(fn) -> bool:
        try:
            activity._Definition.must_from_callable(fn)
            return True
        except Exception:  # noqa: BLE001
            return False

    for fn_name in ("resolve_entity_batch", "write_records", "detect_extract_collisions"):
        assert _is_activity(getattr(wf, fn_name)), f"{fn_name} 丢了 @activity.defn"
    for fn_name in ("_execution_context_for_cases", "_open_entity_gray_case", "_prewrite_recheck"):
        assert not _is_activity(getattr(wf, fn_name)), f"{fn_name} 不该是活动"


# ---------------------------------------------------------------------------
# 写前终判（write_records 集成）：图态随写可见的召回桩 + INSERT 语句解析
# ---------------------------------------------------------------------------

# 注：行值解析按单行/无括号字符串的测试数据简化（多行 INSERT 语义由
# test_extract_claim_check 覆盖，这里只需 vid 与 name 落进图态）。
_INSERT_RE = re.compile(r"INSERT VERTEX `(?P<tag>\w+)`\((?P<cols>[^)]*)\) VALUES (?P<rows>.+)$")
_ROW_RE = re.compile(r'"(?P<vid>(?:[^"\\]|\\.)*)":\((?P<vals>.*?)\)(?=,\s*"|$)')


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


def _coerce(raw_val: str) -> Any:
    if raw_val == "NULL":
        return None
    if raw_val in ("true", "false"):
        return raw_val == "true"
    if raw_val.startswith('"'):
        return json.loads(raw_val)
    try:
        return int(raw_val)
    except ValueError:
        return float(raw_val)


class StatefulGraphClient:
    """写进什么，同名召回就能看见什么（模拟图库索引即时可见）。"""

    def __init__(self, state: dict[str, dict[str, Any]]) -> None:
        self.state = state
        self.settings = SimpleNamespace(space="test")
        self.written: list[str] = []

    def connect(self) -> None:
        pass

    def close(self) -> None:
        pass

    def execute_write(self, query: str, params: Any = None):
        self.written.append(query)
        match = _INSERT_RE.search(query)
        assert match, query
        cols = [col.strip().strip("`") for col in match.group("cols").split(",")]
        for row in _ROW_RE.finditer(match.group("rows")):
            vals = [_coerce(v) for v in _split_sql_vals(row.group("vals"))]
            props = dict(zip(cols, vals, strict=False))
            vid = row.group("vid").replace('\\"', '"')
            props.setdefault("name", vid)
            self.state[vid] = {"vid": vid, "name": props.get("name"), "props": props}
        return SimpleNamespace(records=[])

    def execute_read(self, query: str, params: Any = None):
        return SimpleNamespace(records=[])

    def execute_query(self, query: str, params: Any = None):
        return SimpleNamespace(records=[])


@pytest.fixture
def guard_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """守卫全开 + 近邻路/增量索引关（隔离真实 Milvus/控制库）。"""
    monkeypatch.setenv("ENTITY_DISAMBIGUATION_PREWRITE_RECHECK", "1")
    monkeypatch.setenv("ENTITY_DISAMBIGUATION_NAME_LOCK", "1")
    monkeypatch.setenv("ENTITY_DISAMBIGUATION_MILVUS_RECALL", "0")
    monkeypatch.setenv("SCHEMA_EXTRACT_INCREMENTAL_INDEX", "0")
    state: dict[str, dict[str, Any]] = {}

    def factory(settings):
        return StatefulGraphClient(state)

    monkeypatch.setattr("infra.graph_db.client.TRSGraphClient", factory)

    def fake_recall(client, label, names, space=None):
        wanted = set(names)
        return {
            name: [dict(entry) for entry in state.values() if entry["name"] == name]
            for name in wanted
        }

    monkeypatch.setattr("service.entity_disambiguation.recall_candidates", fake_recall)

    created: list[dict[str, Any]] = []

    from service.manual_review_production import manual_review_service

    def fake_create_direct_case(**kwargs):
        created.append(kwargs)
        return {"reviewId": f"MR-{len(created)}"}

    monkeypatch.setattr(manual_review_service, "create_direct_case", fake_create_direct_case)
    return {"state": state, "created": created}


def _request(vid: str, name: str) -> dict[str, Any]:
    return {
        "kind": "entity",
        "name": "Person",
        "activeProps": ["id", "name"],
        "records": [{"id": vid, "props": {"id": vid, "name": name}}],
        "graph": {"space": "sp1"},
        "sourceTable": "t.src",
        "stepId": "source:b1#step",
        "batchIdx": 0,
        "chunkIdx": 0,
    }


class TestPrewriteRecheck:
    async def test_new_record_untouched(self, guard_env, fake_lock_redis):
        result = await write_records(_request("p1", "张三"))
        assert result["written"] == 1
        assert result.get("guardMerged", 0) == 0
        assert set(guard_env["state"]) == {"p1"}

    async def test_merge_rewrites_vid(self, guard_env, fake_lock_redis):
        # 属性全同 → 1.0 ≥0.85 合并：改写 vid 到已有节点
        guard_env["state"]["p_exist"] = {
            "vid": "p_exist",
            "name": "汪小红",
            "props": {"name": "汪小红", "affiliation": "清华", "correspond": 1},
        }
        req = _request("p_new", "汪小红")
        req["records"] = [
            {
                "id": "p_new",
                "props": {
                    "id": "p_new",
                    "name": "汪小红",
                    "affiliation": "清华",
                    "correspond": 1,
                },
            }
        ]
        req["activeProps"] = ["id", "name", "affiliation", "correspond"]
        result = await write_records(req)
        assert result["written"] == 1
        assert result["guardMerged"] == 1
        assert set(guard_env["state"]) == {"p_exist"}  # 落的是目标节点

    async def test_gray_withholds_and_returns_records(self, guard_env, fake_lock_redis):
        # 同名无可比属性 → 0.80 灰区：扣留建案，records 交回工作流
        guard_env["state"]["p_exist"] = {
            "vid": "p_exist",
            "name": "汪小红",
            "props": {"name": "汪小红"},
        }
        result = await write_records(_request("p_new", "汪小红"))
        assert result["written"] == 0
        assert result["guardWithheld"] == 1
        assert result["records"] == []  # 已剔除扣留项
        assert set(guard_env["state"]) == {"p_exist"}
        case = guard_env["created"][0]
        assert case["template_id"] == "T_LINK"
        assert case["candidate"]["existingCandidates"][0]["vid"] == "p_exist"
        assert case["candidate"]["_incoming"]["vid"] == "p_new"
        assert "写前终判" in case["reason"]

    async def test_low_score_writes_new(self, guard_env, fake_lock_redis):
        # 同名但属性全面冲突 → 0.6 <0.65 新建
        guard_env["state"]["p_exist"] = {
            "vid": "p_exist",
            "name": "汪小红",
            "props": {"name": "汪小红", "affiliation": "清华", "correspond": 1},
        }
        req = _request("p_new", "汪小红")
        req["records"] = [
            {
                "id": "p_new",
                "props": {
                    "id": "p_new",
                    "name": "汪小红",
                    "affiliation": "北大",
                    "correspond": 0,
                },
            }
        ]
        req["activeProps"] = ["id", "name", "affiliation", "correspond"]
        result = await write_records(req)
        assert result["written"] == 1
        assert set(guard_env["state"]) == {"p_exist", "p_new"}

    async def test_flag_off_skips_recheck(self, guard_env, fake_lock_redis, monkeypatch):
        monkeypatch.setenv("ENTITY_DISAMBIGUATION_PREWRITE_RECHECK", "0")
        guard_env["state"]["p_exist"] = {
            "vid": "p_exist",
            "name": "汪小红",
            "props": {"name": "汪小红"},
        }
        result = await write_records(_request("p_new", "汪小红"))
        assert result["written"] == 1  # 无终判：照旧双写（旧行为）
        assert guard_env["created"] == []


class TestRaceRootFix:
    """并发同名双写：关锁确定性复现老 bug，开锁恰一节点 + 一灰案。"""

    async def test_lock_off_reproduces_double_write(self, guard_env, fake_lock_redis, monkeypatch):
        monkeypatch.setenv("ENTITY_DISAMBIGUATION_NAME_LOCK", "0")
        import service.temporal_workflows as wf

        original = wf._prewrite_recheck
        barrier_in = asyncio.Barrier(2)
        barrier_out = asyncio.Barrier(2)

        async def racing_recheck(client, name_tag, records, **kwargs):
            await barrier_in.wait()  # 两批同时进入终判
            result = await original(client, name_tag, records, **kwargs)
            await barrier_out.wait()  # 两批召回都读完（图里尚无同名）才放行写图
            return result

        monkeypatch.setattr(wf, "_prewrite_recheck", racing_recheck)

        async def _one(vid: str) -> dict[str, Any]:
            return await write_records(_request(vid, "汪小红"))

        results = await asyncio.gather(_one("person_a"), _one("person_b"))
        assert set(guard_env["state"]) == {"person_a", "person_b"}  # 老 bug：双写
        assert sum(r["written"] for r in results) == 2

    async def test_lock_on_single_write_with_gray(self, guard_env, fake_lock_redis):
        # 终判+INSERT 同锁串行：后到者看见先写节点 → 灰案扣留，图里恰一节点

        async def _one(vid: str) -> dict[str, Any]:
            return await write_records(_request(vid, "汪小红"))

        results = await asyncio.gather(_one("person_a"), _one("person_b"))
        assert len(guard_env["state"]) == 1  # 恰一节点（先到者胜出）
        assert sum(r["written"] for r in results) == 1
        assert sum(r.get("guardWithheld", 0) for r in results) == 1
        case = guard_env["created"][0]
        assert case["candidate"]["existingCandidates"][0]["name"] == "汪小红"
        assert fake_lock_redis.store == {}  # 锁全部释放
