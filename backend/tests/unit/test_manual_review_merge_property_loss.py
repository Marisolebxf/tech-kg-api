"""人工审核 T_LINK merge 裁决整标签覆盖丢列缺陷（2026-10-19）的修复单测。

背景：merge 裁决曾把扣留行非空列直接拼 ``INSERT VERTEX``——Nebula 对已存在
顶点是**整标签覆盖**（未列出列被清空），服务器隔离空间实测 8 个合并目标
学者 h_index 等既有列全 None、source_record_id 被改写为作者行 vid；旧
docstring「空值列不写＝不覆盖目标已有值」与真实语义相反。

修复语义（service/manual_review_production.py::_insert_withheld_vertex，
与平台写图路径 #526 同款）：

- per-VID fail-closed Redis 锁（``entity_write_guard.vid_write_lock_sync``）
  包住「FETCH 旧值 → 列级合并 → INSERT」，与工作流写图路径同一把锁
  （``vid_lock_keys`` 同键）——跨路径并发写同 VID 互斥；
- 列级合并：扣留行非空列覆盖目标既有值；缺失/空值列保留目标值；图上
  NULL 不进合并；create_time/update_time 每次由平台刷新；
- FETCH 失败 / 图上旧属性无法解析 → 抛错零写入（fail-closed），submit
  事务回滚、案件状态不前移，重提即重试。

第二轮（同日 Codex 复核，协作文档 4e06992c）——**租约生命周期**：同步锁
曾无续租、无失效标记、不在 INSERT 前校验持有权，临界区耗时超过 TTL 时
租约被另一写者接管后，原写者按旧快照 INSERT 仍会清掉对方列且全程不抛
错。修复：锁 yield 租约句柄（``_SyncVidLease``），FETCH 耗时超 TTL/3 先
续租（``refresh_if_aged``）、INSERT 派发前必须续租并校验持有权
（``ensure_lease``），续租失败/租约丢失抛 ``VidWriteLeaseLostError``
禁止新的 INSERT。

驱动方式：真实 ``TRSGraphClient`` + ``httpx.MockTransport`` 伪 trs-graph
REST（DESCRIBE/FETCH/INSERT 按整标签覆盖语义维护内存 vid→props 状态）；
锁不连真 Redis——注入假同步 Redis 客户端（dict 后备 + 可拨动时钟的 TTL
过期语义，可预占键模拟工作流持锁、可注错模拟 Redis 故障），真实走
``_acquire_sync``/``_renew_sync``/``_release_sync_quiet``。
"""

from __future__ import annotations

import json
import re
import threading
import time
from typing import Any

import httpx
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db_model.base import Base
from db_model.manual_review import ReviewAuditLog, ReviewCase, ReviewDecision
from infra.graph_db.client import TRSGraphClient
from infra.graph_db.config import TRSGraphSettings
from infra.graph_db.exceptions import GraphRequestError
from service import entity_write_guard as guard
from service.manual_review_domain import ReviewIdentity
from service.manual_review_production import ManualReviewService


def _actor():
    return ReviewIdentity("r1", "r1", frozenset({"reviewer"}), frozenset({"*"}), "org", "req-m")


def _make_service():
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return ManualReviewService(sessionmaker(engine, expire_on_commit=False))


@pytest.fixture
def service():
    return _make_service()


@pytest.fixture(autouse=True)
def _stub_entity_search_sync(monkeypatch):
    """隔离真实钩子（连控制库/Milvus/Redis）：裁决语义测试不关心索引联动。"""
    monkeypatch.setattr(
        ManualReviewService,
        "_sync_entity_search_after_write",
        lambda self, apply_detail: None,
    )


# ---------------------------------------------------------------------------
# 假同步 Redis 客户端（dict 后备 + 可拨动时钟的 TTL 语义）
# ---------------------------------------------------------------------------


class FakeClock:
    """真实单调时钟 + 可拨动偏移：不拨动时行为等同真实时间（锁等待超时等
    照常触发）；``advance`` 确定性跨过租约 TTL，复现「临界区停滞 → 租约
    过期被接管」。线程安全（GIL 下属性读写原子，submit 跑在测试线程外）。"""

    def __init__(self):
        self._offset = 0.0

    def __call__(self) -> float:
        return time.monotonic() + self._offset

    def advance(self, seconds: float) -> None:
        self._offset += seconds


class FakeSyncRedis:
    """假同步 Redis：SET NX PX（按假时钟执行 TTL 过期）+ eval 按 Lua 文本
    派发 ``_RELEASE_LUA``（token 比删）/``_RENEW_LUA``（token 校验才刷新
    过期）——调用方 ``_acquire_sync``/``_renew_sync``/``_release_sync_quiet``
    原样执行，顺带证明同步续租与异步版共用同一脚本。预占 ``held``（不带
    expires）= 模拟工作流路径持锁；``acquire_error``/``renew_error`` 注入
    Redis 故障。
    """

    def __init__(self, clock: FakeClock):
        self.clock = clock
        self.held: dict[str, str] = {}
        self.expires: dict[str, float] = {}
        self.attempts: list[str] = []
        self.eval_calls: list[tuple[str, tuple]] = []
        self.acquire_error: Exception | None = None
        self.renew_error: Exception | None = None

    def _purge_expired(self) -> None:
        now = self.clock()
        for key in [k for k, exp in self.expires.items() if exp <= now]:
            self.held.pop(key, None)
            self.expires.pop(key, None)

    def set(self, key, value, nx=False, px=None):
        if self.acquire_error is not None:
            raise self.acquire_error
        self._purge_expired()
        self.attempts.append(key)
        if nx and key in self.held:
            return None
        self.held[key] = value
        if px:
            self.expires[key] = self.clock() + px / 1000
        return True

    def eval(self, script, numkeys, *args):
        if self.renew_error is not None and script == guard._RENEW_LUA:
            raise self.renew_error
        self._purge_expired()
        self.eval_calls.append((script, args))
        key, token = args[0], args[1]
        if self.held.get(key) != token:
            return 0
        if script == guard._RENEW_LUA:
            self.expires[key] = self.clock() + int(args[2]) / 1000
            return 1
        if script == guard._RELEASE_LUA:
            del self.held[key]
            self.expires.pop(key, None)
            return 1
        raise AssertionError(f"未知 Lua 脚本: {script[:40]}")

    def renew_count(self, token: str | None = None) -> int:
        """已发生的续租 eval 次数（可按 token 过滤）。"""
        return sum(
            1
            for script, args in self.eval_calls
            if script == guard._RENEW_LUA and (token is None or args[1] == token)
        )


@pytest.fixture
def lock_store(monkeypatch):
    clock = FakeClock()
    fake = FakeSyncRedis(clock)
    monkeypatch.setattr(guard, "_sync_client", fake)
    # 租约句柄的「距上次续租时长」与等待超时判定都走同一可拨动时钟
    monkeypatch.setattr(guard, "_monotonic", clock)
    # 等待上限压短：持锁冲突场景快速走 fail-closed，不拖慢测试
    monkeypatch.setenv("ENTITY_WRITE_VID_LOCK_WAIT_SECONDS", "0.2")
    return fake


# ---------------------------------------------------------------------------
# 伪 trs-graph REST：真实 TRSGraphClient + MockTransport
# ---------------------------------------------------------------------------

_UNSET = object()

PERSON_TAG_FIELDS = {
    "name": "string",
    "name_cn": "string",
    "person_kind": "string",
    "h_index": "int64",
    "paper_nums": "int64",
    "scholar_org": "string",
    "source_record_id": "string",
    "source_table": "string",
    "extra_json": "string",
    "create_time": "string",
    "update_time": "string",
}

EDGE_FIELDS = {
    "role": "string",
    "create_time": "string",
    "update_time": "string",
    "source_table": "string",
}

TARGET_VID = "person_9"
RESERVED_VID = "person_new_1"

TARGET_PROPS = {
    "name": "汪小红",
    "name_cn": "汪小红",
    "person_kind": "scholar",
    "h_index": 31,
    "paper_nums": 210,
    "scholar_org": "某大学",
    "source_record_id": "dwd_scholar:1001",
    "source_table": "dwd_scholar",
    "create_time": "2020-01-01 08:00:00",
    "update_time": "2020-01-01 08:00:00",
}

_INSERT_RE = re.compile(
    r"INSERT VERTEX `(?P<tag>[^`]+)`\((?P<cols>[^)]*)\) "
    r'VALUES (?P<vid>"(?:[^"\\]|\\.)*"):\((?P<vals>.*)\)\s*$',
    re.S,
)
_VID_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')


def _split_vals(raw: str) -> list[str]:
    """字符串感知的逗号切分（值里可有转义引号/逗号）。"""
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


def _coerce_literal(raw: str) -> Any:
    raw = raw.strip()
    if raw == "NULL":
        return None
    if raw == "true":
        return True
    if raw == "false":
        return False
    if raw.startswith('"'):
        return json.loads(raw)
    try:
        return int(raw)
    except ValueError:
        return float(raw)


class FakeTRSREST:
    """伪 trs-graph REST handler：DESCRIBE/FETCH/INSERT/edges。

    INSERT 按 Nebula **整标签覆盖**语义维护 ``state``（vid→props）：语句列出
    的列即新状态全部，未列出列被清掉——与真实图库一致，断言最终状态即验证
    「保留目标既有列」。``fetch_error`` 注入 FETCH 读失败；``fetch_raw_props``
    注入损坏旧属性形状（P2 熔断）。``fetch_gate`` 置位后 FETCH 进入即停住等
    待放行（``fetch_entered`` 同步通知测试线程）——配合拨动时钟复现「临界
    区停滞跨过租约 TTL」。
    """

    def __init__(
        self,
        *,
        tag_fields: dict[str, str] | None = None,
        edge_fields: dict[str, str] | None = None,
        existing: dict[str, dict[str, Any]] | None = None,
    ):
        self.tag_fields = dict(tag_fields or PERSON_TAG_FIELDS)
        self.edge_fields = dict(edge_fields or EDGE_FIELDS)
        self.state: dict[str, dict[str, Any]] = {
            vid: dict(props) for vid, props in (existing or {}).items()
        }
        self.write_stmts: list[str] = []
        self.fetch_stmts: list[str] = []
        self.edge_writes: list[tuple[str, str, str, dict]] = []
        self.fetch_error = False
        self.fetch_raw_props: Any = _UNSET
        self.fetch_gate: threading.Event | None = None
        self.fetch_entered = threading.Event()

    def _ok(self, records: list[dict[str, Any]] | None = None) -> httpx.Response:
        return httpx.Response(200, json={"records": records or [], "summary": {}})

    def _describe(self, query: str) -> httpx.Response:
        fields = self.edge_fields if "DESCRIBE EDGE" in query else self.tag_fields
        return self._ok([{"Field": f, "Type": t, "Null": "YES"} for f, t in fields.items()])

    def _fetch(self, query: str) -> httpx.Response:
        self.fetch_stmts.append(query)
        if self.fetch_error:
            return httpx.Response(500, json={"message": "graphd transient error"})
        vid = _VID_RE.search(query).group(1)
        if vid not in self.state:
            response = self._ok([])  # 目标不存在：Nebula FETCH 返回空
        else:
            props: Any = (
                self.fetch_raw_props
                if self.fetch_raw_props is not _UNSET
                else dict(self.state[vid])
            )
            response = self._ok([{"vid": vid, "props": props}])
        if self.fetch_gate is not None:
            # 快照先取（= FETCH 在停滞前已完成读），再停住等放行：放行后
            # 返回的是停滞前的旧快照——复现 Codex 探针时序「B 在 A 停滞
            # 期间写入，A 按旧快照 INSERT」
            self.fetch_entered.set()
            self.fetch_gate.wait()
        return response

    def _apply_insert(self, query: str) -> None:
        m = _INSERT_RE.search(query)
        assert m, f"无法解析 INSERT VERTEX 语句: {query[:120]}"
        vid = json.loads(m.group("vid"))
        cols = [c.strip().strip("`") for c in m.group("cols").split(",")]
        vals = [_coerce_literal(v) for v in _split_vals(m.group("vals"))]
        assert len(cols) == len(vals)
        # 整标签覆盖：未列出列被清掉（与真实 Nebula 语义一致）
        self.state[vid] = {c: v for c, v in zip(cols, vals, strict=True)}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/health":
            return httpx.Response(200, json={"status": "UP"})
        if path == "/api/v1/edges":
            body = json.loads(request.content or b"{}")
            self.edge_writes.append(
                (
                    str(body["sourceId"]),
                    str(body["targetId"]),
                    str(body["type"]),
                    body["properties"],
                )
            )
            return httpx.Response(
                200,
                json={
                    "id": f"{body['sourceId']}->{body['targetId']}@0",
                    "type": body["type"],
                    "sourceId": body["sourceId"],
                    "targetId": body["targetId"],
                    "properties": body["properties"],
                },
            )
        if path in ("/api/v1/query", "/api/v1/query/read", "/api/v1/query/write"):
            body = json.loads(request.content or b"{}")
            query = str(body.get("query") or "")
            if query.lstrip().upper().startswith("USE "):
                query = query.split(";", 1)[1].strip()
            if path == "/api/v1/query/write":
                self.write_stmts.append(query)
                self._apply_insert(query)
                return self._ok([])
            if query.startswith("DESCRIBE"):
                return self._describe(query)
            if path == "/api/v1/query/read" and query.startswith("FETCH PROP ON"):
                return self._fetch(query)
            return self._ok([])
        return httpx.Response(404, json={"message": f"no route: {path}"})


def _install_graph(service: Any, monkeypatch: Any, handler: FakeTRSREST) -> None:
    client = TRSGraphClient(
        TRSGraphSettings(base_url="http://trs-graph-fake", space="dev2", api_key="k", timeout=5),
        transport=httpx.MockTransport(handler),
    )
    client.connect()
    monkeypatch.setattr(ManualReviewService, "_graph_client_for", lambda self, snapshot: client)


def _link_kwargs(**overrides) -> dict[str, Any]:
    value = dict(
        task_id="TASK-MERGE",
        execution_id="EXEC-MERGE",
        step_id="align",
        kind="entity",
        candidate={
            "name": "汪小红",
            "newIds": [RESERVED_VID],
            "existingCandidates": [{"vid": TARGET_VID, "name": "汪小红", "score": 0.8}],
            "_incoming": {
                "vid": RESERVED_VID,
                # name 空串 / h_index None = 扣留行缺失列（不得毁目标既有值）
                "props": {
                    "name": "",
                    "name_cn": "汪小红",
                    "person_kind": "legal_representative",
                    "h_index": None,
                },
                "sourceTable": "dwd_zh_author",
            },
            "_pendingRelations": [],
            "_graphSpace": "dev2",
        },
        object_id=RESERVED_VID,
        object_name="汪小红",
        node_label="Person",
        reason="消歧得分落入灰区",
        confidence=0.9,
        domain="talent",
        template_id="T_LINK",
    )
    value.update(overrides)
    return value


def _open(service: Any, **overrides) -> tuple[str, int]:
    created = service.create_direct_case(**_link_kwargs(**overrides))
    detail = service.get_case(created["reviewId"], _actor())
    return detail["id"], detail["version"]


def _merge_submit(service: Any, case_id: str, version: int) -> dict[str, Any]:
    return service.submit(
        case_id,
        version,
        "entity-confirm",
        {"entityVerdict": "merge", "targetEntityId": TARGET_VID},
        "",
        _actor(),
    )


def _db_state(service: Any, case_id: str) -> tuple[str, int, int, int]:
    with service.sf() as s:
        case = s.get(ReviewCase, case_id)
        decisions = s.scalar(
            select(func.count())
            .select_from(ReviewDecision)
            .where(ReviewDecision.case_id == case_id)
        )
        audits = s.scalar(
            select(func.count())
            .select_from(ReviewAuditLog)
            .where(ReviewAuditLog.case_id == case_id)
        )
        return case.status, case.version, decisions, audits


# ---------------------------------------------------------------------------
# (a) FETCH 有值 + 新行缺列 → 目标既有列保留
# ---------------------------------------------------------------------------


def test_merge_preserves_target_columns_missing_from_incoming(service, monkeypatch, lock_store):
    handler = FakeTRSREST(existing={TARGET_VID: dict(TARGET_PROPS)})
    _install_graph(service, monkeypatch, handler)
    case_id, version = _open(service)

    out = _merge_submit(service, case_id, version)

    assert out["status"] == "RESOLVED"
    final = handler.state[TARGET_VID]
    # 目标既有业务列/溯源列全部保留（修复前这里全被整标签覆盖清掉）
    assert final["h_index"] == 31
    assert final["paper_nums"] == 210
    assert final["scholar_org"] == "某大学"
    assert final["source_record_id"] == "dwd_scholar:1001"
    assert final["source_table"] == "dwd_scholar"
    # 扣留行非空列正常落图；name 由快照展示名兜底补齐
    assert final["person_kind"] == "legal_representative"
    assert final["name_cn"] == "汪小红"
    assert final["name"] == "汪小红"
    # INSERT 语句本身带上保留列（未列出=被 Nebula 清空）
    (stmt,) = handler.write_stmts
    for col in ("h_index", "paper_nums", "scholar_org", "source_record_id", "source_table"):
        assert f"`{col}`" in stmt, f"INSERT 缺保留列 {col}: {stmt}"
    # 锁获取过且已释放（不留死锁）
    assert lock_store.attempts
    assert not lock_store.held


# ---------------------------------------------------------------------------
# (b) 新值按策略合并：非空覆盖、空列不毁、时间列刷新
# ---------------------------------------------------------------------------


def test_merge_conflict_rule_nonempty_overrides_and_times_refreshed(
    service, monkeypatch, lock_store
):
    handler = FakeTRSREST(existing={TARGET_VID: dict(TARGET_PROPS)})
    _install_graph(service, monkeypatch, handler)
    case_id, version = _open(
        service,
        candidate={
            **_link_kwargs()["candidate"],
            "_incoming": {
                "vid": RESERVED_VID,
                "props": {
                    "h_index": 99,  # 非空 → 覆盖目标 31（冲突规则：新值非空才覆盖）
                    "source_record_id": "dwd_zh_author:9",  # 溯源列非空 → 覆盖
                },
                "sourceTable": "dwd_zh_author",
            },
        },
    )

    _merge_submit(service, case_id, version)

    final = handler.state[TARGET_VID]
    assert final["h_index"] == 99
    assert final["source_record_id"] == "dwd_zh_author:9"
    # 未携带列保留目标值
    assert final["paper_nums"] == 210
    assert final["scholar_org"] == "某大学"
    assert final["source_table"] == "dwd_scholar"
    # create_time/update_time 不从图上保留：每次由平台刷新
    assert final["create_time"] != "2020-01-01 08:00:00"
    assert final["update_time"] != "2020-01-01 08:00:00"
    assert re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", final["create_time"])


def test_create_verdict_absent_vid_equivalent_to_create_path(service, monkeypatch, lock_store):
    """create 裁决（预留 vid 图上不存在）：FETCH 空 → 只写扣留行列，不凭空补列。"""
    handler = FakeTRSREST(existing={TARGET_VID: dict(TARGET_PROPS)})
    _install_graph(service, monkeypatch, handler)
    case_id, version = _open(service)

    out = service.submit(
        case_id, version, "entity-confirm", {"entityVerdict": "create"}, "", _actor()
    )

    assert out["status"] == "RESOLVED"
    final = handler.state[RESERVED_VID]
    assert final["person_kind"] == "legal_representative"
    assert final["name"] == "汪小红"
    assert "h_index" not in final  # 未提供列不捏造
    assert final["create_time"]
    # 合并目标未被触碰
    assert handler.state[TARGET_VID]["h_index"] == 31


# ---------------------------------------------------------------------------
# (c) 跨路径同 VID 并发：工作流持锁 → MRP fail-closed 零覆盖，等待后可重试
# ---------------------------------------------------------------------------


def test_workflow_holding_vid_lock_blocks_mrp_write_fail_closed(service, monkeypatch, lock_store):
    handler = FakeTRSREST(existing={TARGET_VID: dict(TARGET_PROPS)})
    _install_graph(service, monkeypatch, handler)
    case_id, version = _open(service)

    # 工作流写图路径持锁：同一键名（vid_lock_keys）预占，token 不同
    (key,) = guard.vid_lock_keys("dev2", "Person", [TARGET_VID])
    lock_store.held[key] = "wr-workflow-holder"

    with pytest.raises(TimeoutError):
        _merge_submit(service, case_id, version)

    # fail-closed 零覆盖：无 INSERT、无 FETCH（锁在 FETCH 之前），案件状态未前移
    assert handler.write_stmts == []
    assert handler.fetch_stmts == []
    status, ver, decisions, audits = _db_state(service, case_id)
    assert status == "OPEN"
    assert ver == version
    assert decisions == 0
    assert audits == 1  # 仅建案的 CASE_CREATED，失败提交零追加
    # 同键证明：MRP 尝试获取的正是工作流占用的那把锁（跨路径互斥）
    assert key in lock_store.attempts

    # 工作流释放后重提成功（等待语义的兜底路径：稍后重试）
    del lock_store.held[key]
    out = _merge_submit(service, case_id, version)
    assert out["status"] == "RESOLVED"
    assert handler.state[TARGET_VID]["h_index"] == 31


def test_lock_acquire_failure_fail_closed_zero_write(service, monkeypatch, lock_store):
    """Redis 故障（获取即抛）→ fail-closed 拒绝覆盖，不降级无锁写。"""
    handler = FakeTRSREST(existing={TARGET_VID: dict(TARGET_PROPS)})
    _install_graph(service, monkeypatch, handler)
    case_id, version = _open(service)

    lock_store.acquire_error = RuntimeError("redis connection refused")
    with pytest.raises(RuntimeError, match="redis connection refused"):
        _merge_submit(service, case_id, version)

    assert handler.write_stmts == []
    assert handler.fetch_stmts == []
    assert _db_state(service, case_id)[0] == "OPEN"


# ---------------------------------------------------------------------------
# (d) FETCH 读取失败 / 旧属性损坏 → 零覆盖
# ---------------------------------------------------------------------------


def test_fetch_read_failure_zero_write_case_not_advanced(service, monkeypatch, lock_store):
    handler = FakeTRSREST(existing={TARGET_VID: dict(TARGET_PROPS)})
    handler.fetch_error = True
    _install_graph(service, monkeypatch, handler)
    case_id, version = _open(service)

    with pytest.raises(GraphRequestError):
        _merge_submit(service, case_id, version)

    # 单次抖动重试一次后仍失败 → 上抛；绝无 INSERT
    assert len(handler.fetch_stmts) == 2
    assert handler.write_stmts == []
    status, ver, decisions, audits = _db_state(service, case_id)
    assert status == "OPEN"
    assert ver == version
    assert decisions == 0 and audits == 1  # 仅建案审计，失败提交零追加
    # 锁在 finally 里已释放，不留死锁
    assert not lock_store.held


@pytest.mark.parametrize(
    "raw",
    [
        "{broken-json",  # trs-graph 序列化成 JSON 字符串但坏了
        ["not", "dict"],  # 形状异常：list
        12345,  # 形状异常：标量
    ],
    ids=["broken-json-str", "list-shape", "scalar-shape"],
)
def test_corrupt_existing_props_zero_write(service, monkeypatch, lock_store, raw):
    """图上旧属性无法解析/形状异常：按「无旧值」继续写=静默覆盖清列 → 必须熔断。"""
    handler = FakeTRSREST(existing={TARGET_VID: dict(TARGET_PROPS)})
    handler.fetch_raw_props = raw
    _install_graph(service, monkeypatch, handler)
    case_id, version = _open(service)

    with pytest.raises(GraphRequestError):
        _merge_submit(service, case_id, version)

    assert handler.write_stmts == []
    assert _db_state(service, case_id)[0] == "OPEN"
    assert not lock_store.held


# ---------------------------------------------------------------------------
# (e) apply 失败不产半写状态：案件状态不前移、决议/审计/暂存边零落，
#     重提幂等成功后顶点与暂存边各写一次
# ---------------------------------------------------------------------------


def test_apply_failure_then_resubmit_is_idempotent_with_pending_edges(
    service, monkeypatch, lock_store
):
    handler = FakeTRSREST(existing={TARGET_VID: dict(TARGET_PROPS)})
    _install_graph(service, monkeypatch, handler)
    case_id, version = _open(
        service,
        candidate={
            **_link_kwargs()["candidate"],
            "_pendingRelations": [
                {
                    "edgeType": "EMPLOYED_BY",
                    "fromId": RESERVED_VID,
                    "toId": "person_77",
                    "props": {"role": "engineer"},
                }
            ],
        },
    )

    # FETCH 失败 → 整个 apply 在任何图写之前中止（顶点与暂存边都零写入）
    handler.fetch_error = True
    with pytest.raises(GraphRequestError):
        _merge_submit(service, case_id, version)
    assert handler.write_stmts == []
    assert handler.edge_writes == []
    assert _db_state(service, case_id) == ("OPEN", version, 0, 1)  # audits 仅建案 1 条

    # 恢复后重提：同 version 仍有效（回滚已还原占位），一次成功
    handler.fetch_error = False
    out = _merge_submit(service, case_id, version)
    assert out["status"] == "RESOLVED"
    assert len(handler.write_stmts) == 1
    assert handler.state[TARGET_VID]["h_index"] == 31
    # 暂存边按改写端点（预留 vid → 合并目标）补写一次，审计列按边 schema 补
    ((frm, to, etype, eprops),) = handler.edge_writes
    assert (frm, to, etype) == (TARGET_VID, "person_77", "EMPLOYED_BY")
    assert eprops["role"] == "engineer"
    assert eprops["create_time"] and eprops["update_time"]
    assert eprops["source_table"] == "schema_extract"
    status, ver, decisions, audits = _db_state(service, case_id)
    assert status == "RESOLVED" and decisions == 1 and ver == version + 1
    assert audits == 2  # CASE_CREATED + DECISION_SUBMITTED


# ---------------------------------------------------------------------------
# 第二轮（Codex 复核 4e06992c）：租约生命周期——临界区跨过 TTL 的接管防护
# ---------------------------------------------------------------------------


def _run_submit_in_thread(service: Any, case_id: str, version: int):
    """后台线程跑裁决提交（主线程同时拨时钟/扮演第二写者），捕获异常/结果。"""
    outcome: dict[str, Any] = {}

    def runner() -> None:
        try:
            outcome["result"] = _merge_submit(service, case_id, version)
        except BaseException as exc:  # noqa: BLE001
            outcome["exc"] = exc

    thread = threading.Thread(target=runner, name="mrp-submit-under-test")
    thread.start()
    return thread, outcome


def test_lease_expired_takeover_second_writer_no_insert(service, monkeypatch, lock_store):
    """a) 临界区超过原 TTL：租约过期被第二写者接管后，原写者续租失败抛错
    零 INSERT，接管者落下的列完好（Codex 探针场景——修复前按旧快照整标签
    INSERT 清掉 writer_B_column 且全程不抛错）。"""
    monkeypatch.setenv("ENTITY_DISAMBIGUATION_NAME_LOCK_TTL_SECONDS", "5")
    handler = FakeTRSREST(existing={TARGET_VID: dict(TARGET_PROPS)})
    handler.fetch_gate = threading.Event()
    _install_graph(service, monkeypatch, handler)
    case_id, version = _open(service)
    (key,) = guard.vid_lock_keys("dev2", "Person", [TARGET_VID])

    thread, outcome = _run_submit_in_thread(service, case_id, version)
    assert handler.fetch_entered.wait(5)  # A 已持锁进入 FETCH，停滞中
    # 拨时钟跨过 5s TTL：A 的租约过期，B 获同键锁并落一列（持有不放）
    lock_store.clock.advance(6)
    assert guard._acquire_sync(key, "wr-writer-b", 5000)
    handler.state[TARGET_VID]["writer_B_column"] = 99  # B 已落图的一列
    handler.fetch_gate.set()  # 放行 A：拿到的是停滞前的旧快照（不含 B 的列）
    thread.join(5)
    assert not thread.is_alive()

    # A 续租失败 → 明确异常（语义类似 LeaseLost），零 INSERT（execute_write
    # 从未被调用）
    assert isinstance(outcome.get("exc"), guard.VidWriteLeaseLostError)
    assert handler.write_stmts == []
    # B 的列完好（修复前：A 按旧快照整标签 INSERT 静默清掉 writer_B_column）
    assert handler.state[TARGET_VID]["writer_B_column"] == 99
    assert handler.state[TARGET_VID]["h_index"] == 31
    # 边界续租真实发生过（INSERT 派发前的持有权校验不是空转）
    assert lock_store.renew_count() >= 1
    # d) token 失配不删：A 退出的 finally 释放没有误删 B 正持有的锁
    assert lock_store.held.get(key) == "wr-writer-b"
    guard._release_sync_quiet(key, "wr-writer-b")
    assert key not in lock_store.held
    # submit 事务回滚：案件状态/版本不前移、决议零落、审计仅建案 1 条
    assert _db_state(service, case_id) == ("OPEN", version, 0, 1)


def test_renew_failure_zero_new_write(service, monkeypatch, lock_store):
    """b) 续租失败（续期通道 Redis 故障）→ 零新增写：FETCH 已完成、锁仍在，
    但 execute_write 从未被调用，submit 回滚。"""
    handler = FakeTRSREST(existing={TARGET_VID: dict(TARGET_PROPS)})
    _install_graph(service, monkeypatch, handler)
    case_id, version = _open(service)

    # 锁获取/释放通道正常、租约未过期；仅续租 Lua 注错（Redis 拨不通续期）
    lock_store.renew_error = RuntimeError("redis renew down")
    with pytest.raises(guard.VidWriteLeaseLostError):
        _merge_submit(service, case_id, version)

    assert len(handler.fetch_stmts) == 1  # FETCH 正常完成（合并输入已就绪）
    assert handler.write_stmts == []  # 续租失败熔断：execute_write 零调用
    assert _db_state(service, case_id) == ("OPEN", version, 0, 1)
    assert not lock_store.held  # 释放通道不受续租注错影响，不留死锁


class _FakeAsyncPipeline:
    """异步 pipeline：操作排队、``execute`` 落到共享的假同步存储。"""

    def __init__(self, store: FakeSyncRedis) -> None:
        self._store = store
        self._ops: list[tuple] = []

    def set(self, key, value, nx=False, px=None):
        self._ops.append(("set", key, value, nx, px))
        return self

    def eval(self, script, numkeys, *args):
        self._ops.append(("eval", script, args))
        return self

    async def execute(self):
        out = []
        for op in self._ops:
            if op[0] == "set":
                out.append(self._store.set(op[1], op[2], nx=op[3], px=op[4]))
            else:  # ("eval", script, args)：numkeys 恒为 1，透传给存储端 eval
                out.append(self._store.eval(op[1], 1, *op[2]))
        return out


class FakeAsyncRedisFacade:
    """把假同步存储包装成异步客户端接口：工作流异步锁与裁决同步锁落在
    **同一个存储**上（生产环境两者本就连同一 Redis），验证跨路径同键互斥。"""

    def __init__(self, store: FakeSyncRedis) -> None:
        self._store = store

    def pipeline(self, transaction: bool = True):
        return _FakeAsyncPipeline(self._store)


async def test_workflow_async_lock_blocks_sync_acquire_on_same_key(monkeypatch, lock_store):
    """c) 与工作流路径实际共享同键互斥：异步锁真实持键 → 同步获取等待
    超时 fail-closed；异步退出释放后同步立即可取（反向通路同一把锁）。"""
    monkeypatch.setattr(guard, "_client", FakeAsyncRedisFacade(lock_store))
    (key,) = guard.vid_lock_keys("dev2", "Person", [TARGET_VID])

    async with guard.vid_write_locks("dev2", "Person", [TARGET_VID]):
        assert lock_store.held.get(key)  # 异步获取路径真实持有该键
        with pytest.raises(TimeoutError):
            with guard.vid_write_lock_sync("dev2", "Person", TARGET_VID):
                raise AssertionError("异步持键期间同步锁不该获取成功")
    assert key not in lock_store.held  # 异步退出已释放

    with guard.vid_write_lock_sync("dev2", "Person", TARGET_VID) as lease:
        assert lease.key == key  # 同步拿到正是异步刚释放的同一把锁
        assert lease.token == lock_store.held[key]


def test_release_token_mismatch_keeps_others_lock(lock_store):
    """d) token 失配不删别人的锁（单点）：比删是唯一合法释放通道。"""
    key = guard.vid_lock_keys("dev2", "Person", [TARGET_VID])[0]
    assert guard._acquire_sync(key, "tok-a", 5000)

    guard._release_sync_quiet(key, "tok-b")  # 失配：不删
    assert lock_store.held[key] == "tok-a"

    guard._release_sync_quiet(key, "tok-a")  # 匹配：删
    assert key not in lock_store.held


def test_slow_fetch_renew_success_insert_proceeds(service, monkeypatch, lock_store):
    """e) 正向对照：FETCH 停滞跨过 TTL/3 但未跨过 TTL，续租成功 → INSERT
    正常派发且仅一次，合并语义不变。"""
    monkeypatch.setenv("ENTITY_DISAMBIGUATION_NAME_LOCK_TTL_SECONDS", "5")
    handler = FakeTRSREST(existing={TARGET_VID: dict(TARGET_PROPS)})
    handler.fetch_gate = threading.Event()
    _install_graph(service, monkeypatch, handler)
    case_id, version = _open(service)

    thread, outcome = _run_submit_in_thread(service, case_id, version)
    assert handler.fetch_entered.wait(5)
    lock_store.clock.advance(2)  # 超过 TTL/3（≈1.67s）、未到 TTL（5s）
    handler.fetch_gate.set()
    thread.join(5)
    assert not thread.is_alive()

    assert "exc" not in outcome, outcome.get("exc")
    assert outcome["result"]["status"] == "RESOLVED"
    assert len(handler.write_stmts) == 1  # INSERT 正常派发
    final = handler.state[TARGET_VID]
    assert final["h_index"] == 31  # 合并保留语义不受边界续租影响
    assert final["person_kind"] == "legal_representative"
    # 两次边界续租都真实发生：慢 FETCH 触发 refresh_if_aged（无停滞时只有
    # INSERT 前的 ensure_lease 一次）+ INSERT 前 ensure_lease；每次都按满
    # TTL（5000ms）续
    assert lock_store.renew_count() >= 2
    assert all(
        args[2] == 5000 for script, args in lock_store.eval_calls if script == guard._RENEW_LUA
    )
    assert not lock_store.held
    assert _db_state(service, case_id)[0] == "RESOLVED"
