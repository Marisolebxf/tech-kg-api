"""批内灰区幻影候选回归（1022 + Codex 复核 R1/R2/R3）：三层修复的回归测试。

事故链复现（dev2 空间 gkx_compact_full_20261021_01 实录）：chunk 内先到记录
resolve 时图内无同名判 new，后到记录批内同名灰区（候选=先到 vid）；先到写前
终判被改判灰区扣留、从写集剔除——先到 vid 永不落图，后到案只剩幻影候选，
评审 merge 会指向图内不存在的目标。

Codex 复核修复（本文件全量重写为真实活动路径——不再手工改 FakeGraph.nodes
模拟恢复，一律经 ``write_records`` 实跑失败/重试/终败）：

- **R1 建案有效性**：批内同名灰区建案推迟到本批 INSERT 成功后的写后终判
  （resolve 只回传 ``deferredGray``）——先到未落图前**零建案**；写入失败/
  活动重试/终局失败时案从未发布；写后重判 merge → ``DEFERRED_MERGE_BLOCKED``
  失败关闭（stage=post-write-deferred）；召回失败上抛重试。
- **R2 重跑丢纠偏关联**：既有案复用（R2 并入）时按先到本 run 落图与否恢复
  ``batchCandidateRefs``（落图→refs 供写前终判纠偏）或立即纠偏（不落图→
  既有案此刻就是幻影）；既有 test_resolve_replay_registers_no_refs 的
  「丢失关联当预期」改为验证重跑后实际候选正确。
- **R3 纠偏证据版本**：``_resolution`` 原始证据只读；``_candidateRescope``
  独立成证（candidates/oldCandidates/decide/bestScore/margin/阈值/规则版本/
  时点）；decide=merge 只入证据不自动执行。

FakeGraph 支持：INSERT VERTEX 语句解析后反映进 nodes+recall（写后终判的召回
必见本批已提交 INSERT）；写失败/召回失败可注入。
"""

from __future__ import annotations

import copy
import json
import re
from io import BytesIO
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from temporalio.exceptions import ApplicationError

from db_model.base import Base
from db_model.manual_review import ReviewAuditLog, ReviewCase
from service.entity_disambiguation import GRAY_LOW, MERGE_THRESHOLD
from service.gray_gate import decision_policy
from service.manual_review_domain import (
    ReviewConflictError,
    ReviewIdentity,
    ReviewValidationError,
)
from service.manual_review_production import ManualReviewService

# ---------------------------------------------------------------------------
# 测试基础设施（与 test_gray_gate_v2_pipeline.py 同款假图/内存库；get_node 按
# nodes 集合判存在性——A3 裁决端 merge 目标终判需要；INSERT VERTEX 解析后
# 反映进 nodes/recall——写后终判的召回必见本批已提交 INSERT，R1）
# ---------------------------------------------------------------------------


class FakeBody(BytesIO):
    def close(self) -> None:  # noqa: D102
        pass


class FakeS3:  # pragma: no cover - 本文件内联 records，不触发 S3 中转
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    @property
    def bucket(self) -> str:
        return "b"

    def put_bytes(self, key: str, data: bytes, content_type: str) -> SimpleNamespace:
        self.objects[key] = data
        return SimpleNamespace(bucket=self.bucket, object_key=key, etag=None)

    def get_object(self, bucket: str, key: str) -> FakeBody:
        return FakeBody(self.objects[key])


def _result(rows):
    return SimpleNamespace(records=list(rows))


def _nGQL_literal(token: str) -> Any:
    """nGQL 字面量 → Python 值（字符串/bool/NULL/数字）。"""
    if token.startswith('"'):
        return json.loads(token)
    if token == "true":
        return True
    if token == "false":
        return False
    if token == "NULL" or token == "":
        return None
    try:
        return int(token)
    except ValueError:
        try:
            return float(token)
        except ValueError:
            return token


def _split_top_level(raw: str) -> list[str]:
    """顶层逗号切分（字符串字面量内的逗号/转义不切）。"""
    parts: list[str] = []
    buf: list[str] = []
    in_str = False
    i = 0
    while i < len(raw):
        ch = raw[i]
        if in_str:
            buf.append(ch)
            if ch == "\\" and i + 1 < len(raw):
                buf.append(raw[i + 1])
                i += 2
                continue
            if ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
            buf.append(ch)
        elif ch == ",":
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
        i += 1
    if buf:
        parts.append("".join(buf).strip())
    return parts


_INSERT_VERTEX_RE = re.compile(r"^INSERT VERTEX `([^`]+)`\(([^)]*)\) VALUES (.+)$")
_INSERT_ROW_RE = re.compile(r'\s*("(?:[^"\\]|\\.)*")\s*:\s*\(')


class FakeGraph:
    """按查询形状分发的假图客户端（同名召回 / 端点探针 / FETCH / DESCRIBE）。

    R1 关键能力：``execute_write`` 的 ``INSERT VERTEX`` 语句被解析并**反映**
    进 ``nodes``（get_node 存在性）与 ``_reflected``（随后的同名召回/FETCH 都
    能看见本批已提交的 INSERT）——写后终判按图内现状重判的前提。
    ``write_error``/``write_error_times``（-1=恒失败）注入写失败；
    ``recall_error`` 注入召回失败（MATCH 查询抛错）。
    """

    def __init__(self, *, recall=None, existing=None, nodes=None, tag_columns=None):
        self.recall: dict[str, list[dict[str, Any]]] = recall or {}
        self.existing = set(existing or ())
        self.nodes = set(nodes or ())
        self.tag_columns = tag_columns or {
            "Scholar": [
                "name",
                "org",
                "city",
                "email",
                "id",
                "source_table",
                "create_time",
                "update_time",
            ],
            "Organization": ["name", "province"],
        }
        self.writes: list[str] = []
        self.edges: list[tuple] = []
        self.reads: list[str] = []
        self._reflected: dict[str, dict[str, dict[str, Any]]] = {}
        self.write_error: Exception | None = None
        self.write_error_times: int = 0
        self.recall_error: Exception | None = None

    # -- 写后反映（R1）：INSERT VERTEX 解析 → nodes + 召回可见 ----------------

    def _reflect_insert(self, query: str) -> None:
        m = _INSERT_VERTEX_RE.match(query.strip())
        if not m:
            return
        tag, cols_raw, values_raw = m.groups()
        cols = [c.strip().strip("`") for c in cols_raw.split(",")]
        pos = 0
        while pos < len(values_raw):
            row = _INSERT_ROW_RE.match(values_raw, pos)
            if row is None:
                break
            vid = json.loads(row.group(1))
            depth, start = 1, row.end()
            in_str = False
            i = start
            while i < len(values_raw) and depth:
                ch = values_raw[i]
                if in_str:
                    if ch == "\\":
                        i += 2
                        continue
                    if ch == '"':
                        in_str = False
                elif ch == '"':
                    in_str = True
                elif ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                i += 1
            values = [_nGQL_literal(tok) for tok in _split_top_level(values_raw[start : i - 1])]
            props = {
                col: value for col, value in zip(cols, values, strict=False) if value is not None
            }
            self.nodes.add(vid)
            self._reflected.setdefault(tag, {})[vid] = props
            pos = i

    def _recall_rows(self, tag: str) -> list[dict[str, Any]]:
        """静态召回行 + 反映行（vid 去重，静态在前——同 vid 以注入行优先）。"""
        rows = [dict(row) for row in self.recall.get(tag, [])]
        seen = {str(row.get("vid")) for row in rows}
        for vid, props in (self._reflected.get(tag) or {}).items():
            if vid not in seen and props.get("name"):
                rows.append({"vid": vid, "props": dict(props)})
        return rows

    def connect(self) -> None:
        pass

    def close(self) -> None:
        pass

    def get_node(self, vid):
        if str(vid) in self.nodes:
            return SimpleNamespace(properties={"name": "节点存在"}, vid=str(vid))
        return None

    def create_edge(self, frm, to, edge_type, props):
        self.edges.append((frm, to, edge_type, props))

    def execute_query(self, query: str, params: Any = None):
        if query.startswith("DESCRIBE TAG"):
            tag = re.search(r"DESCRIBE TAG `([^`]+)`", query).group(1)
            cols = self.tag_columns.get(tag, ["name"])
            return _result([{"Field": c, "Type": "string", "Null": "YES"} for c in cols])
        return _result([])

    def execute_read(self, query: str, params: Any = None):
        self.reads.append(query)
        q = query.strip()
        if q.startswith("DESCRIBE"):
            if q.startswith("DESCRIBE TAG `"):
                tag = re.search(r"DESCRIBE TAG `([^`]+)`", q).group(1)
                cols = self.tag_columns.get(tag, ["name"])
                return _result([{"Field": c, "Type": "string", "Null": "YES"} for c in cols])
            return _result([])
        if "WHERE id(v) IN [" in query:
            return _result([{"vid": v} for v in sorted(self.existing)])
        if query.startswith("MATCH (v:`"):
            if self.recall_error is not None:
                raise self.recall_error
            tag = re.search(r"MATCH \(v:`([^`]+)`\)", query).group(1)
            return _result([dict(row) for row in self._recall_rows(tag)])
        if query.startswith("FETCH PROP ON"):
            tag = re.search(r"FETCH PROP ON `([^`]+)`", query).group(1)
            rows = [
                {"vid": vid, "props": dict(props)}
                for vid, props in (self._reflected.get(tag) or {}).items()
            ]
            return _result(rows)
        raise AssertionError(f"意外读查询: {query}")

    def execute_write(self, query: str, params: Any = None):
        if self.write_error is not None and self.write_error_times != 0:
            if self.write_error_times > 0:
                self.write_error_times -= 1
            raise self.write_error
        self.writes.append(query)
        self._reflect_insert(query)
        return _result([])


@pytest.fixture
def review_service(monkeypatch: pytest.MonkeyPatch) -> ManualReviewService:
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    svc = ManualReviewService(sessionmaker(engine, expire_on_commit=False))
    monkeypatch.setattr("service.manual_review_production.manual_review_service", svc)
    monkeypatch.setenv("GRAY_GATE_DEDUPE_IDENTITY_KEY", "unit-test-identity-key")
    return svc


@pytest.fixture(autouse=True)
def pipeline_env(monkeypatch: pytest.MonkeyPatch):
    """关近邻路/写前守卫开关/同名锁/VID 锁（需要守卫的用例单独 setenv=1）。"""
    monkeypatch.setenv("ENTITY_DISAMBIGUATION_MILVUS_RECALL", "0")
    monkeypatch.setenv("ENTITY_DISAMBIGUATION_PREWRITE_RECHECK", "0")
    monkeypatch.setenv("ENTITY_DISAMBIGUATION_NAME_LOCK", "0")
    monkeypatch.setenv("ENTITY_WRITE_VID_LOCK_ENABLED", "0")


@pytest.fixture(autouse=True)
def entity_search_sync_stub(monkeypatch: pytest.MonkeyPatch):
    """隔离真实索引联动钩子（连控制库/Milvus/Redis）——替成记录桩。"""
    calls: list[dict] = []
    monkeypatch.setattr(
        ManualReviewService,
        "_sync_entity_search_after_write",
        lambda self, apply_detail: calls.append(apply_detail),
    )
    return calls


def use_graph(monkeypatch: pytest.MonkeyPatch, graph: FakeGraph) -> FakeGraph:
    import infra.graph_db.client as graph_client_module

    monkeypatch.setattr(graph_client_module, "TRSGraphClient", lambda settings: graph)
    return graph


def use_space_client(monkeypatch: pytest.MonkeyPatch, graph: FakeGraph) -> FakeGraph:
    """服务端路径（rescope/submit/_apply 的 ``_graph_client_for``）图客户端桩。"""
    import infra.graph_db as graph_db_module

    monkeypatch.setattr(graph_db_module, "get_space_client", lambda space: graph)
    return graph


def actor(uid="reviewer-1") -> ReviewIdentity:
    return ReviewIdentity(uid, uid, frozenset({"reviewer"}), frozenset({"graph"}), "org", "req-1")


# 先到/后到同批记录：同名 + 3 可比属性 1 命中 → 0.6+0.4/3 ≈ 0.733 ∈ 灰区
FIRST = {"id": "sch_first", "props": {"name": "张三", "org": "A", "city": "X", "email": "E1"}}
LATER = {"id": "sch_later", "props": {"name": "张三", "org": "A", "city": "Y", "email": "E2"}}
LATER2 = {"id": "sch_later2", "props": {"name": "张三", "org": "A", "city": "Z", "email": "E3"}}
# 并行来源 worker 落图的同名节点：与先到/后到均为灰区（非 merge）
RSCH_ROW = {"vid": "sch_rsch", "props": {"name": "张三", "org": "A", "city": "X2", "email": "E9"}}
# 与后到属性完全一致的图内节点：1.0 分（≥ merge 阈值）
CLONE_ROW = {"vid": "sch_clone", "props": {"name": "张三", "org": "A", "city": "Y", "email": "E2"}}


def _resolve_request(records, **overrides):
    request = {
        "name": "Scholar",
        "graph": {"space": "dev2"},
        "schemaKey": "sk",
        "stepId": "source:bind-1#main",
        "sourceTable": "dwd.dwd_scholar",
        "batchIdx": 0,
        "chunkIdx": 0,
        "records": records,
        "decisionPolicy": decision_policy(),
    }
    request.update(overrides)
    return request


def _write_request(records, deferred=None, refs=None, **overrides):
    request = {
        "kind": "entity",
        "name": "Scholar",
        "activeProps": [],
        "graph": {"space": "dev2"},
        "sourceTable": "dwd.dwd_scholar",
        "stepId": "source:bind-1#main",
        "batchIdx": 0,
        "chunkIdx": 0,
        "records": records,
        "decisionPolicy": decision_policy(),
    }
    if deferred is not None:
        request["deferredGray"] = deferred
    if refs is not None:
        request["batchCandidateRefs"] = refs
    request.update(overrides)
    return request


def _cases(review_service: ManualReviewService):
    with review_service.sf() as s:
        rows = s.scalars(select(ReviewCase).where(ReviewCase.template_id == "T_LINK")).all()
        return [(r.id, r.diagnosis, json.loads(r.candidate_snapshot)) for r in rows]


def _case_row(review_service: ManualReviewService, case_id: str) -> ReviewCase:
    with review_service.sf() as s:
        return s.get(ReviewCase, case_id)


def _rescope_audits(review_service: ManualReviewService, case_id: str):
    with review_service.sf() as s:
        return s.scalars(
            select(ReviewAuditLog).where(
                ReviewAuditLog.case_id == case_id,
                ReviewAuditLog.event_type == "CANDIDATES_RESCOPED",
            )
        ).all()


# ---------------------------------------------------------------------------
# R1：写后终判——建案有效性（写入失败/活动重试/终局失败全覆盖）
# ---------------------------------------------------------------------------


class TestDeferredAdjudicationR1:
    @pytest.mark.asyncio
    async def test_case_published_only_after_insert_with_real_candidate(
        self, review_service, monkeypatch
    ):
        """主链：resolve 零建案（推迟），INSERT 成功后写后终判才建案——候选=
        先到 vid 且为图内真实节点（INSERT 已反映），真实 gray 证据上桌。"""
        from service.temporal_workflows import resolve_entity_batch, write_records

        graph = use_graph(monkeypatch, FakeGraph(recall={"Scholar": []}))
        use_space_client(monkeypatch, graph)
        out = await resolve_entity_batch(_resolve_request([dict(FIRST), dict(LATER)]))
        # R1 核心：resolve 只推迟、不建案——此刻图内没有任何 T_LINK 案
        assert out["new"] == 1 and out["deferred"] == 1 and out["withheld"] == 0
        assert [r["id"] for r in out["records"]] == ["sch_first"]
        assert "batchCandidateRefs" not in out
        deferred = out["deferredGray"]
        assert len(deferred) == 1  # 恰好一条推迟条目（后到 LATER）
        assert deferred[0]["batchVid"] == "sch_first"
        assert deferred[0]["batchStage"] == "批内同名"
        assert deferred[0]["record"]["id"] == "sch_later"
        assert "_batchGray" not in deferred[0]["record"]  # 打标列不进推迟载荷
        assert _cases(review_service) == []  # 零建案：案未发布

        result = await write_records(
            _write_request([dict(r) for r in out["records"]], deferred=deferred)
        )
        assert result["written"] == 1  # 先到 INSERT
        assert result["deferredGray"] == 1 and result["deferredCases"] == 1
        # 写后终判建的案：候选=先到 vid，且已随本批 INSERT 真实落图（反映可见）
        [(case_id, reason, snapshot)] = _cases(review_service)
        assert snapshot["_incoming"]["vid"] == "sch_later"
        cands = snapshot["existingCandidates"]
        assert [c["vid"] for c in cands] == ["sch_first"]
        assert graph.get_node("sch_first") is not None  # INSERT 反映：真实候选
        res = snapshot["_resolution"]
        assert res["scoreDecision"] == "gray"
        assert res["effectiveDisposition"] == "withhold_pending_review"
        assert GRAY_LOW <= res["matchScore"] < MERGE_THRESHOLD
        assert cands[0]["propCompared"] == 3 and cands[0]["propMatched"] == 1
        assert GRAY_LOW <= cands[0]["score"] < MERGE_THRESHOLD
        assert "写后终判" in reason
        # 候选真实 → merge 一次通过（A3 存在性终判不拦真实目标）
        verdict = review_service.submit(
            case_id,
            1,
            "entity-confirm",
            {"entityVerdict": "merge", "targetEntityId": "sch_first"},
            "",
            actor(),
        )
        assert verdict["status"] == "RESOLVED"
        assert any('VALUES "sch_first"' in w for w in graph.writes)

    @pytest.mark.asyncio
    async def test_write_transient_failure_then_retry_publishes_case(
        self, review_service, monkeypatch
    ):
        """R1 写入失败：INSERT 失败上抛 → 活动重试（同请求重放）——失败期间
        零建案（幻影案从未发布）；重试成功后案才发布且候选真实。"""
        from infra.graph_db.exceptions import GraphRequestError
        from service.temporal_workflows import resolve_entity_batch, write_records

        graph = use_graph(monkeypatch, FakeGraph(recall={"Scholar": []}))
        use_space_client(monkeypatch, graph)
        out = await resolve_entity_batch(_resolve_request([dict(FIRST), dict(LATER)]))
        deferred = out["deferredGray"]
        request = _write_request([dict(r) for r in out["records"]], deferred=deferred)
        # 非瞬态错误（不匹配高水位正则）：立即上抛，不烧退避
        graph.write_error = GraphRequestError(
            "注入：graphd 写入失败（终局语义验证）", status_code=500
        )
        graph.write_error_times = 1
        with pytest.raises(GraphRequestError):
            await write_records(request)
        assert _cases(review_service) == []  # 建案有效性：写败时案从未发布
        assert graph.get_node("sch_first") is None
        # 活动重试（Temporal 同请求重放）：写入成功 → 写后终判发布案
        graph.write_error = None
        result = await write_records(request)
        assert result["written"] == 1 and result["deferredCases"] == 1
        [(case_id, _, snapshot)] = _cases(review_service)
        assert [c["vid"] for c in snapshot["existingCandidates"]] == ["sch_first"]
        assert graph.get_node("sch_first") is not None

    @pytest.mark.asyncio
    async def test_write_terminal_failure_never_publishes_case(self, review_service, monkeypatch):
        """R1 终局失败：持续写败（重试烧尽/终败）——零建案、零节点、零幻影案
        （水位不推进，执行重跑按重试路径重放；不存在「案在、候选不在图」态）。"""
        from infra.graph_db.exceptions import GraphRequestError
        from service.temporal_workflows import resolve_entity_batch, write_records

        graph = use_graph(monkeypatch, FakeGraph(recall={"Scholar": []}))
        use_space_client(monkeypatch, graph)
        out = await resolve_entity_batch(_resolve_request([dict(FIRST), dict(LATER)]))
        deferred = out["deferredGray"]
        graph.write_error = GraphRequestError("注入：graphd 长期不可写", status_code=503)
        graph.write_error_times = -1  # 恒失败（终局）
        request = _write_request([dict(FIRST)], deferred=deferred)
        for _ in range(3):  # 多轮重试同样失败
            with pytest.raises(GraphRequestError):
                await write_records(request)
        assert _cases(review_service) == []  # 案从未发布
        assert graph.get_node("sch_first") is None and graph.nodes == set()

    @pytest.mark.asyncio
    async def test_post_write_deferred_merge_fail_closed(self, review_service, monkeypatch):
        """R1 写后重判 merge：失败关闭（DEFERRED_MERGE_BLOCKED，stage=
        post-write-deferred）——先到的 INSERT 已成功，但后到不得在无 remap 下
        「被合并」照写；零建案、零静默。"""
        from service.temporal_workflows import resolve_entity_batch, write_records

        graph = use_graph(monkeypatch, FakeGraph(recall={"Scholar": []}))
        use_space_client(monkeypatch, graph)
        out = await resolve_entity_batch(_resolve_request([dict(FIRST), dict(LATER)]))
        # resolve 与 write 之间并行 worker 落图了与后到完全一致的节点（1.0 分）
        graph.recall["Scholar"] = [dict(CLONE_ROW)]
        with pytest.raises(ApplicationError) as ei:
            await write_records(
                _write_request([dict(r) for r in out["records"]], deferred=out["deferredGray"])
            )
        assert ei.value.type == "DEFERRED_MERGE_BLOCKED"
        assert "post-write-deferred" in str(ei.value)
        assert _cases(review_service) == []  # 两阶段：merge 在任何建案副作用前抛出
        assert graph.get_node("sch_first") is not None  # 先到的 INSERT 已成功提交

    @pytest.mark.asyncio
    async def test_post_write_recall_failure_raises_for_retry(self, review_service, monkeypatch):
        """R1 召回失败：上抛活动重试（不 fail-open 照写——推迟记录的 resolve
        判定本身就是「待判」，无「按 resolve 原样写」可退；也绝不静默丢）。"""
        from service.temporal_workflows import resolve_entity_batch, write_records

        graph = use_graph(monkeypatch, FakeGraph(recall={"Scholar": []}))
        use_space_client(monkeypatch, graph)
        out = await resolve_entity_batch(_resolve_request([dict(FIRST), dict(LATER)]))
        graph.recall_error = RuntimeError("图库召回通道抖动")
        with pytest.raises(RuntimeError) as ei:
            await write_records(
                _write_request([dict(r) for r in out["records"]], deferred=out["deferredGray"])
            )
        assert "写后终判召回失败" in str(ei.value)
        assert _cases(review_service) == []  # 零建案（重试收敛后再发布）
        assert graph.get_node("sch_first") is not None  # INSERT 已提交（幂等重试）

    @pytest.mark.asyncio
    async def test_retry_after_case_published_merges_into_existing(
        self, review_service, monkeypatch
    ):
        """R1 活动重试幂等：案已发布后活动重试（后续步骤失败重放整活动）——
        写后终判经 R2 前置裁决并入既有案，不重复建案；驳回终态则按 priorVerdict
        丢弃（dropped），后到记录不复活写图。"""
        from service.temporal_workflows import resolve_entity_batch, write_records

        graph = use_graph(monkeypatch, FakeGraph(recall={"Scholar": []}))
        use_space_client(monkeypatch, graph)
        out = await resolve_entity_batch(_resolve_request([dict(FIRST), dict(LATER)]))
        deferred = out["deferredGray"]
        request = _write_request([dict(r) for r in out["records"]], deferred=deferred)
        first = await write_records(request)
        assert first["deferredCases"] == 1
        [(case_id, _, _)] = _cases(review_service)
        # 活动重试一（案仍 OPEN，未裁决）：R2 前置裁决并入既有案——不重复建案
        retried_open = await write_records(request)
        assert retried_open["deferredCases"] == 0
        assert retried_open.get("deferredPriorDropped", 0) == 0
        assert retried_open["written"] == 1  # 先到幂等重写
        assert len(_cases(review_service)) == 1
        # 评审员驳回（终态）→ 活动重试二：priorVerdict=reject → 丢弃不复活
        review_service.submit(
            case_id, 1, "reject-candidate", {"entityVerdict": "reject"}, "", actor()
        )
        retried_reject = await write_records(request)
        assert retried_reject["deferredCases"] == 0
        assert retried_reject.get("deferredPriorDropped") == 1
        assert len(_cases(review_service)) == 1

    @pytest.mark.asyncio
    async def test_deferred_key_claim_check_shape(self, review_service, monkeypatch):
        """R1 S3 中转：deferredKey 载荷（大文本不进历史）下载后与内联路径
        同口径发布案。"""
        from service.temporal_workflows import resolve_entity_batch, write_records

        graph = use_graph(monkeypatch, FakeGraph(recall={"Scholar": []}))
        use_space_client(monkeypatch, graph)
        out = await resolve_entity_batch(_resolve_request([dict(FIRST), dict(LATER)]))
        deferred = out["deferredGray"]

        async def fake_load(key: str):
            if key == "payloads/deferred-test":
                return deferred
            return [dict(FIRST)]

        monkeypatch.setattr("service.temporal_workflows._load_records_from_key", fake_load)
        result = await write_records(
            _write_request(
                None, recordsKey="payloads/records-test", deferredKey="payloads/deferred-test"
            )
        )
        assert result["written"] == 1 and result["deferredCases"] == 1
        [(case_id, _, snapshot)] = _cases(review_service)
        assert [c["vid"] for c in snapshot["existingCandidates"]] == ["sch_first"]
        assert graph.get_node("sch_first") is not None

    @pytest.mark.asyncio
    async def test_prewrite_withholds_first_post_write_rejudges_later(
        self, review_service, monkeypatch
    ):
        """R1 先到被写前终判扣留（不落图）：写后终判按图内现状重判后到——
        候选=图内真实 RSCH（无幻影）；两案候选全部真实、判定真实灰区。"""
        from service.temporal_workflows import resolve_entity_batch, write_records

        graph = use_graph(monkeypatch, FakeGraph(recall={"Scholar": []}))
        use_space_client(monkeypatch, graph)
        out = await resolve_entity_batch(_resolve_request([dict(FIRST), dict(LATER)]))
        # resolve 与 write 之间并行 worker 把 RSCH 落图（事故时序）
        graph.recall["Scholar"] = [dict(RSCH_ROW)]
        graph.nodes.add("sch_rsch")
        monkeypatch.setenv("ENTITY_DISAMBIGUATION_PREWRITE_RECHECK", "1")
        result = await write_records(
            _write_request([dict(r) for r in out["records"]], deferred=out["deferredGray"])
        )
        # 先到被写前终判改判灰区扣留（建自己的案，候选=RSCH 真实），写集清空
        assert result["guardWithheld"] == 1 and result["written"] == 0
        # 后到写后终判：图内现状只有 RSCH → 仍灰区 → 建案（候选=RSCH 真实）
        assert result["deferredCases"] == 1
        cases = {
            snap["_incoming"]["vid"]: (cid, reason, snap)
            for cid, reason, snap in _cases(review_service)
        }
        assert set(cases) == {"sch_first", "sch_later"}
        for _vid, (_cid, _reason, snap) in cases.items():
            res = snap["_resolution"]
            assert res["scoreDecision"] == "gray"
            assert GRAY_LOW <= res["matchScore"] < MERGE_THRESHOLD
            cands = snap["existingCandidates"]
            assert [c["vid"] for c in cands] == ["sch_rsch"]  # 无幻影候选
            assert graph.get_node(cands[0]["vid"]) is not None
        assert "写前终判" in cases["sch_first"][1]
        assert "写后终判" in cases["sch_later"][1]
        # 先到 vid 不落图（写集清空）且不进任何案候选
        assert graph.get_node("sch_first") is None

    @pytest.mark.asyncio
    async def test_multiple_same_name_deferred_both_cased_post_write(
        self, review_service, monkeypatch
    ):
        """R1 多条同名：两个后到都推迟，写后终判各建案（候选=先到，真实落图）。"""
        from service.temporal_workflows import resolve_entity_batch, write_records

        graph = use_graph(monkeypatch, FakeGraph(recall={"Scholar": []}))
        use_space_client(monkeypatch, graph)
        out = await resolve_entity_batch(_resolve_request([dict(FIRST), dict(LATER), dict(LATER2)]))
        assert out["new"] == 1 and out["deferred"] == 2
        assert [r["id"] for r in out["records"]] == ["sch_first"]
        assert len(out["deferredGray"]) == 2
        assert _cases(review_service) == []
        result = await write_records(
            _write_request([dict(r) for r in out["records"]], deferred=out["deferredGray"])
        )
        assert result["deferredCases"] == 2
        cases = _cases(review_service)
        assert len(cases) == 2
        for _cid, _reason, snapshot in cases:
            assert snapshot["_incoming"]["vid"] in {"sch_later", "sch_later2"}
            assert [c["vid"] for c in snapshot["existingCandidates"]] == ["sch_first"]
            assert graph.get_node("sch_first") is not None

    @pytest.mark.asyncio
    async def test_first_itself_gray_no_deferral(self, review_service, monkeypatch):
        """先到自身判灰区（扣留）：批内候选剔除，后到不推迟（图内候选已真实），
        两案都只指向图内真实节点。"""
        from service.temporal_workflows import resolve_entity_batch

        graph = use_graph(monkeypatch, FakeGraph(recall={"Scholar": [dict(RSCH_ROW)]}))
        graph.nodes.add("sch_rsch")
        use_space_client(monkeypatch, graph)
        out = await resolve_entity_batch(_resolve_request([dict(FIRST), dict(LATER)]))
        assert out["withheld"] == 2 and out["records"] == []
        assert out["deferred"] == 0 and "deferredGray" not in out
        assert "batchCandidateRefs" not in out
        cases = _cases(review_service)
        assert len(cases) == 2
        for _, _reason, snapshot in cases:
            vids = [c["vid"] for c in snapshot["existingCandidates"]]
            assert vids == ["sch_rsch"]  # 无一案引用永不落图的先到 vid
            for c in snapshot["existingCandidates"]:
                assert graph.get_node(c["vid"]) is not None

    @pytest.mark.asyncio
    async def test_v1_path_result_shape_unaffected(self, review_service, monkeypatch):
        """v1 请求（无 decisionPolicy）不走推迟/纠偏链，返回形状不变。"""
        from service.temporal_workflows import resolve_entity_batch

        use_graph(monkeypatch, FakeGraph(recall={"Scholar": []}))
        request = _resolve_request([dict(FIRST), dict(LATER)])
        del request["decisionPolicy"]
        out = await resolve_entity_batch(request)
        assert "batchCandidateRefs" not in out and "deferredGray" not in out
        assert out["records"] == [dict(FIRST)]


# ---------------------------------------------------------------------------
# R2：重跑/复用既有案时恢复纠偏关联（refs 供写前终判纠偏 / 不落图立即纠偏）
# ---------------------------------------------------------------------------


def _seed_legacy_phantom_case(review_service: ManualReviewService, record, first_vid: str) -> str:
    """种「旧代码口径」的批内灰区案（候选=批内先到 vid，先到未落图）——
    R2 恢复链的起点（重跑时后到记录 R2 并入该案）。"""
    from service.temporal_workflows import _execution_context_for_cases, _gray_ingress_material

    info, task_id, execution_id, execution = _execution_context_for_cases()
    material, event_version, basis = _gray_ingress_material(
        step_id="source:bind-1#main",
        record=record,
        graph_space="dev2",
        name_tag="Scholar",
    )
    display = "张三"
    created = review_service.create_direct_case(
        graph_space="dev2",
        task_id=task_id,
        execution_id=execution_id,
        step_id="source:bind-1#main",
        kind="entity",
        candidate={
            "name": display,
            "newIds": [str(record.get("id"))],
            "existingCandidates": [{"vid": first_vid, "name": display, "score": 0.733}],
            "_incoming": {
                "vid": str(record.get("id")),
                "props": record.get("props") or {},
                "sourceTable": "dwd.dwd_scholar",
                "sourceEventVersion": event_version,
                "sourceEventBasis": basis,
            },
            "_pendingRelations": [],
            "_graphSpace": "dev2",
            "_nodeLabel": "Scholar",
            "_resolution": {
                "policyVersion": "gray-gate-v2-test",
                "scoreDecision": "gray",
                "effectiveDisposition": "withhold_pending_review",
                "matchScore": 0.733,
                "margin": None,
                "weights": {"name": 0.6, "props": 0.4},
                "thresholds": {"merge": 0.85, "grayLow": 0.65, "margin": 0.08},
                "nameRuleVersion": "normalized-displayname-v1",
            },
        },
        object_id=str(record.get("id")),
        object_name=display,
        node_label="Scholar",
        reason="消歧得分 0.73 落入灰区 [0.65, 0.85)，需人工裁决（legacy-batch）",
        confidence=0.733,
        workflow_id=getattr(info, "workflow_id", "wf-unit"),
        workflow_run_id=getattr(info, "workflow_run_id", "run-unit"),
        template_id="T_LINK",
        workflow_type="kg.schema.extract",
        exception_code="KG_ENTITY_DISAMBIGUATION_GRAY",
        resume_token=f"extract-resolve:{execution_id}:{record.get('id')}",
        source_table="dwd.dwd_scholar",
        source_record_id=str(record.get("id")),
        dedupe_material=material,
    )
    return str(created.get("reviewId") or "")


class TestReplayRefRecoveryR2:
    @pytest.mark.asyncio
    async def test_replay_recovers_refs_and_prewrite_rescopes(self, review_service, monkeypatch):
        """R2 主链（重写 test_resolve_replay_registers_no_refs 的「丢失关联当
        预期」）：重跑时后到 R2 并入既有案 + 先到本 run 落图 → refs 恢复下发；
        先到在写前终判被扣留 → 纠偏实际发生（重跑后候选正确，非仅不重复建案）。"""
        from service.temporal_workflows import resolve_entity_batch, write_records

        graph = use_graph(monkeypatch, FakeGraph(recall={"Scholar": []}))
        use_space_client(monkeypatch, graph)
        case_id = _seed_legacy_phantom_case(review_service, dict(LATER), "sch_first")
        seed_resolution = copy.deepcopy(
            json.loads(_case_row(review_service, case_id).candidate_snapshot)["_resolution"]
        )
        # 重跑 resolve：先到无案判 new（将落图）；后到 R2 并入既有案
        out = await resolve_entity_batch(_resolve_request([dict(FIRST), dict(LATER)]))
        assert out["new"] == 1 and out["withheld"] == 1 and out["deferred"] == 0
        assert [r["id"] for r in out["records"]] == ["sch_first"]
        # refs 恢复：既有案此刻仍引用先到 vid（幻影），先到落图前先登记依赖
        assert out["batchCandidateRefs"] == {"sch_first": [case_id]}
        assert len(_cases(review_service)) == 1  # 并入不重复建案
        # resolve 与 write 之间并行 worker 落图 RSCH → 写前终判扣留先到
        graph.recall["Scholar"] = [dict(RSCH_ROW)]
        graph.nodes.add("sch_rsch")
        monkeypatch.setenv("ENTITY_DISAMBIGUATION_PREWRITE_RECHECK", "1")
        result = await write_records(
            _write_request([dict(r) for r in out["records"]], refs=out["batchCandidateRefs"])
        )
        assert result["guardWithheld"] == 1 and result["written"] == 0
        # 纠偏实际发生：既有案候选换为图内真实 RSCH（不再是永不落图的先到 vid）
        row = _case_row(review_service, case_id)
        snapshot = json.loads(row.candidate_snapshot)
        assert [c["vid"] for c in snapshot["existingCandidates"]] == ["sch_rsch"]
        assert row.version == 2
        # R3：建案原始证据只读——_resolution 逐字节未动，纠偏独立成证
        assert snapshot["_resolution"] == seed_resolution
        rescope_ev = snapshot["_candidateRescope"]
        assert rescope_ev["deadVids"] == ["sch_first"]
        assert rescope_ev["oldCandidates"] == [{"vid": "sch_first", "name": "张三", "score": 0.733}]
        assert [c["vid"] for c in rescope_ev["candidates"]] == ["sch_rsch"]
        assert rescope_ev["resolution"]["decide"] == "gray"
        assert GRAY_LOW <= rescope_ev["resolution"]["bestScore"] < MERGE_THRESHOLD
        assert rescope_ev["resolution"]["thresholds"] == {
            "merge": 0.85,
            "grayLow": 0.65,
            "margin": 0.08,
        }
        assert rescope_ev["resolution"]["ruleVersion"] == "normalized-displayname-v1"
        # 审计带纠偏判定（R3）
        [audit] = _rescope_audits(review_service, case_id)
        detail = json.loads(audit.detail)
        assert detail["decide"] == "gray" and detail["oldCandidates"] == ["sch_first"]
        # 纠偏后 merge 指向真实节点，一次通过
        verdict = review_service.submit(
            case_id,
            2,
            "entity-confirm",
            {"entityVerdict": "merge", "targetEntityId": "sch_rsch"},
            "",
            actor(),
        )
        assert verdict["status"] == "RESOLVED"

    @pytest.mark.asyncio
    async def test_replay_first_not_landing_rescopes_immediately(self, review_service, monkeypatch):
        """R2 立即纠偏：重跑时先到自身被判灰区扣留（本 run 不落图）——既有案
        此刻就是幻影，resolve 阶段即纠偏（不等写前终判）。"""
        from service.temporal_workflows import resolve_entity_batch

        graph = use_graph(monkeypatch, FakeGraph(recall={"Scholar": [dict(RSCH_ROW)]}))
        graph.nodes.add("sch_rsch")
        use_space_client(monkeypatch, graph)
        case_id = _seed_legacy_phantom_case(review_service, dict(LATER), "sch_first")
        out = await resolve_entity_batch(_resolve_request([dict(FIRST), dict(LATER)]))
        # 先到灰区扣留（不落图）+ 后到并入既有案；refs 不再登记（无落图依赖）
        assert out["withheld"] == 2 and out["records"] == []
        assert "batchCandidateRefs" not in out
        # 立即纠偏已发生：候选换为图内真实 RSCH，版本+1，审计留痕
        row = _case_row(review_service, case_id)
        snapshot = json.loads(row.candidate_snapshot)
        assert [c["vid"] for c in snapshot["existingCandidates"]] == ["sch_rsch"]
        assert row.version == 2
        assert len(_rescope_audits(review_service, case_id)) == 1
        # 全案核对：既有案（已纠偏）+ 先到自身新建案，候选全部图内真实
        assert len(_cases(review_service)) == 2
        for _, _, snap in _cases(review_service):
            assert [c["vid"] for c in snap["existingCandidates"]] == ["sch_rsch"]
        assert graph.get_node("sch_first") is None

    @pytest.mark.asyncio
    async def test_rescope_failure_fails_open_verdict_guard_holds(
        self, review_service, monkeypatch
    ):
        """R2 纠偏失败（fail-open）不阻断写图，但裁决端 A3 防线拦住幻影 merge
        （案保持可提交、可驳回处置）。"""
        from service.temporal_workflows import resolve_entity_batch, write_records

        graph = use_graph(monkeypatch, FakeGraph(recall={"Scholar": []}))
        use_space_client(monkeypatch, graph)
        case_id = _seed_legacy_phantom_case(review_service, dict(LATER), "sch_first")
        out = await resolve_entity_batch(_resolve_request([dict(FIRST), dict(LATER)]))
        refs = out["batchCandidateRefs"]

        def boom(*args, **kwargs):
            raise RuntimeError("图库不可达")

        monkeypatch.setattr(review_service, "rescope_case_candidates", boom)
        graph.recall["Scholar"] = [dict(RSCH_ROW)]
        graph.nodes.add("sch_rsch")
        monkeypatch.setenv("ENTITY_DISAMBIGUATION_PREWRITE_RECHECK", "1")
        # fail-open：纠偏抛错只记 warning，写前终判/写图照常
        result = await write_records(_write_request([dict(r) for r in out["records"]], refs=refs))
        assert result["guardWithheld"] == 1
        # 案未纠偏：仍幻影候选、版本未动
        row = _case_row(review_service, case_id)
        snapshot = json.loads(row.candidate_snapshot)
        assert [c["vid"] for c in snapshot["existingCandidates"]] == ["sch_first"]
        assert row.version == 1
        # A3 兜底：merge 幻影目标被拒，案保持可提交（事务回滚释放占位）
        with pytest.raises(ReviewValidationError) as ei:
            review_service.submit(
                case_id,
                1,
                "entity-confirm",
                {"entityVerdict": "merge", "targetEntityId": "sch_first"},
                "",
                actor(),
            )
        assert "不在图内" in str(ei.value)
        assert _case_row(review_service, case_id).status == "OPEN"
        # 恢复路径：驳回处置不卡死（reject 零图写）
        verdict = review_service.submit(
            case_id, 1, "reject-candidate", {"entityVerdict": "reject"}, "", actor()
        )
        assert verdict["status"] == "RESOLVED"


# ---------------------------------------------------------------------------
# 裁决端存在性终判（A3）+ 纠偏证据版本（R3）
# ---------------------------------------------------------------------------


def _verdict_service(monkeypatch: pytest.MonkeyPatch, nodes: set[str]):
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    svc = ManualReviewService(sessionmaker(engine, expire_on_commit=False))
    graph = FakeGraph(nodes=set(nodes))
    monkeypatch.setattr(ManualReviewService, "_graph_client_for", lambda self, snapshot: graph)
    return svc, graph


def _gray_case_kwargs(**overrides):
    value = dict(
        task_id="TASK-1",
        execution_id="EXEC-1",
        step_id="align",
        kind="entity",
        candidate={
            "name": "示例研究院",
            "newIds": ["org_new_1"],
            "existingCandidates": [{"vid": "org_phantom", "name": "示例研究院", "score": 0.8}],
            "_incoming": {
                "vid": "org_new_1",
                "props": {"name": "示例研究院", "province": "北京"},
                "sourceTable": "db.org_table",
            },
            "_pendingRelations": [],
            "_graphSpace": "dev2",
            "_nodeLabel": "Organization",
            "_resolution": {
                "policyVersion": "gray-gate-v2-test",
                "scoreDecision": "gray",
                "effectiveDisposition": "withhold_pending_review",
                "matchScore": 0.733,
                "margin": None,
                "thresholds": {"merge": 0.85, "grayLow": 0.65, "margin": 0.08},
                "nameRuleVersion": "normalized-displayname-v1",
            },
        },
        object_id="org_new_1",
        object_name="示例研究院",
        node_label="Organization",
        reason="消歧得分 0.73 落入灰区",
        confidence=0.9,
        graph_space="dev2",
        template_id="T_LINK",
    )
    value.update(overrides)
    return value


class TestVerdictTargetExistenceAndRescopeEvidence:
    def test_submit_merge_phantom_target_rejected_then_rescope_recovers(self, monkeypatch):
        """幻影目标：Tx1 前拒绝（案保持可提交）；纠偏出真实候选后 merge 成功。"""
        svc, graph = _verdict_service(monkeypatch, nodes={"org_9"})
        created = svc.create_direct_case(**_gray_case_kwargs())
        detail = svc.get_case(created["reviewId"], actor())
        case_id, version = detail["id"], detail["version"]
        with pytest.raises(ReviewValidationError) as ei:
            svc.submit(
                case_id,
                version,
                "entity-confirm",
                {"entityVerdict": "merge", "targetEntityId": "org_phantom"},
                "",
                actor(),
            )
        assert "不在图内" in str(ei.value)
        assert graph.writes == []
        with svc.sf() as s:
            row = s.get(ReviewCase, case_id)
            assert row.status == "OPEN" and row.version == version  # 回滚释放占位
        # 纠偏：图内同名 org_9 真实存在 → 候选整组替换
        graph.recall["Organization"] = [
            {"vid": "org_9", "props": {"name": "示例研究院", "province": "北京"}}
        ]
        out = svc.rescope_case_candidates(
            case_id, dead_vids={"org_phantom"}, graph_space="dev2", node_label="Organization"
        )
        assert out["rescoped"] is True and out["candidates"] == ["org_9"]
        # 恢复后的合法 merge 照常执行（早期校验不误伤真实目标）
        result = svc.submit(
            case_id,
            version + 1,
            "entity-confirm",
            {"entityVerdict": "merge", "targetEntityId": "org_9"},
            "",
            actor(),
        )
        assert result["status"] == "RESOLVED"
        assert any('VALUES "org_9"' in w for w in graph.writes)

    def test_apply_backstop_blocks_phantom_merge_without_write(self, monkeypatch):
        """兜底防线：_apply_link_verdict 对图内不存在的 merge 目标失败关闭，
        不经 INSERT VERTEX 凭空建点。"""
        svc, graph = _verdict_service(monkeypatch, nodes={"org_9"})
        created = svc.create_direct_case(**_gray_case_kwargs())
        with svc.sf() as s:
            case = s.get(ReviewCase, created["reviewId"])
        with pytest.raises(ReviewValidationError) as ei:
            svc._apply_link_verdict(
                case, {"entityVerdict": "merge", "targetEntityId": "org_phantom"}
            )
        assert "不在图内" in str(ei.value)
        assert graph.writes == [] and graph.edges == []

    def test_apply_backstop_passes_live_target(self, monkeypatch):
        """目标真实存在时兜底不拦：merge 正常落图。"""
        svc, graph = _verdict_service(monkeypatch, nodes={"org_9"})
        created = svc.create_direct_case(
            **_gray_case_kwargs(
                candidate={
                    **_gray_case_kwargs()["candidate"],
                    "existingCandidates": [{"vid": "org_9", "name": "示例研究院", "score": 0.8}],
                }
            )
        )
        with svc.sf() as s:
            case = s.get(ReviewCase, created["reviewId"])
        out = svc._apply_link_verdict(case, {"entityVerdict": "merge", "targetEntityId": "org_9"})
        assert out["applied"] is True and out["vid"] == "org_9"
        assert any('VALUES "org_9"' in w for w in graph.writes)

    def test_rescope_to_empty_candidates_lands_and_blocks_merge(self, monkeypatch):
        """刷新为空同样落库：候选清空后 merge 无目标可选（走新建/驳回），
        不再保留死候选。"""
        svc, graph = _verdict_service(monkeypatch, nodes=set())
        created = svc.create_direct_case(**_gray_case_kwargs())
        detail = svc.get_case(created["reviewId"], actor())
        case_id, version = detail["id"], detail["version"]
        graph.recall["Organization"] = []  # 图内无同名
        out = svc.rescope_case_candidates(
            case_id, dead_vids={"org_phantom"}, graph_space="dev2", node_label="Organization"
        )
        assert out["rescoped"] is True and out["candidates"] == []
        with pytest.raises(ReviewValidationError) as ei:
            svc.submit(
                case_id,
                version + 1,
                "entity-confirm",
                {"entityVerdict": "merge", "targetEntityId": "org_phantom"},
                "",
                actor(),
            )
        assert "不在候选集内" in str(ei.value)  # 候选集已清空
        assert graph.writes == []

    def test_rescope_evidence_version_separate_from_resolution(self, monkeypatch):
        """R3 证据分离：纠偏换出 1.0 分候选——原始 _resolution（0.733 gray）
        逐字节只读；纠偏判定独立成证（decide=merge/bestScore=1.0/阈值/规则
        版本/时点/新旧候选留档），且 merge 只入证据不自动执行（案仍 OPEN、
        零图写，不碰任何已有裁决）。"""
        svc, graph = _verdict_service(monkeypatch, nodes={"org_9"})
        created = svc.create_direct_case(**_gray_case_kwargs())
        case_id = str(created["reviewId"])
        with svc.sf() as s:
            row = s.get(ReviewCase, case_id)
            original_snapshot = json.loads(row.candidate_snapshot)
            original_resolution = copy.deepcopy(original_snapshot["_resolution"])
        # 纠偏出与待入库完全一致的真实节点（name+province 全中 → 1.0 分）
        graph.recall["Organization"] = [
            {"vid": "org_9", "props": {"name": "示例研究院", "province": "北京"}}
        ]
        out = svc.rescope_case_candidates(
            case_id, dead_vids={"org_phantom"}, graph_space="dev2", node_label="Organization"
        )
        assert out["rescoped"] is True and out["candidates"] == ["org_9"]
        with svc.sf() as s:
            row = s.get(ReviewCase, case_id)
            snapshot = json.loads(row.candidate_snapshot)
        # 原始证据未被覆盖：0.733/gray 原样（与新候选 1.0 并存两时点）
        assert snapshot["_resolution"] == original_resolution
        assert snapshot["existingCandidates"][0]["score"] == 1.0
        ev = snapshot["_candidateRescope"]
        assert ev["deadVids"] == ["org_phantom"]
        assert ev["oldCandidates"] == original_snapshot["existingCandidates"]
        assert [c["vid"] for c in ev["candidates"]] == ["org_9"]
        assert ev["candidates"][0]["score"] == 1.0
        res = ev["resolution"]
        assert res["decide"] == "merge"  # 达到合并阈值——只入证据
        assert res["bestScore"] == 1.0
        assert res["thresholds"] == {"merge": 0.85, "grayLow": 0.65, "margin": 0.08}
        assert res["ruleVersion"] == "normalized-displayname-v1"
        assert res["at"]
        # 不自动执行：案仍待裁决、零图写——合并仍需评审员提交且过存在性终判
        assert row.status == "OPEN"
        assert graph.writes == [] and graph.edges == []
        # 审计带纠偏判定
        with svc.sf() as s:
            audits = s.scalars(
                select(ReviewAuditLog).where(
                    ReviewAuditLog.case_id == case_id,
                    ReviewAuditLog.event_type == "CANDIDATES_RESCOPED",
                )
            ).all()
        assert len(audits) == 1
        detail = json.loads(audits[0].detail)
        assert detail["decide"] == "merge" and detail["bestScore"] == 1.0
        # 人工裁决不受影响：评审员 merge 真实目标照常执行
        result = svc.submit(
            case_id,
            row.version,
            "entity-confirm",
            {"entityVerdict": "merge", "targetEntityId": "org_9"},
            "",
            actor(),
        )
        assert result["status"] == "RESOLVED"


# ---------------------------------------------------------------------------
# 补证：纠偏并发终态保护 / CAS 版本冲突（场景3，经真实建案流程种案）
# ---------------------------------------------------------------------------


class TestRescopeConcurrencySupplement:
    @pytest.mark.asyncio
    async def test_rescope_skips_resolved_case_concurrent_verdict_wins(
        self, review_service, monkeypatch
    ):
        """场景3a 纠偏遇并发终态：评审员先一步驳回（RESOLVED）——门控跳过
        纠偏，终态决议/候选/版本不被覆盖（不会把已结案改回可合并状态）。"""
        from service.temporal_workflows import (
            _rescope_batch_gray_cases,
            resolve_entity_batch,
            write_records,
        )

        graph = use_graph(monkeypatch, FakeGraph(recall={"Scholar": []}))
        use_space_client(monkeypatch, graph)
        out = await resolve_entity_batch(_resolve_request([dict(FIRST), dict(LATER)]))
        await write_records(
            _write_request([dict(r) for r in out["records"]], deferred=out["deferredGray"])
        )
        [(case_id, _, _)] = _cases(review_service)
        # 并发写者：评审员先驳回（终态，version 1→2）
        result = review_service.submit(
            case_id, 1, "reject-candidate", {"entityVerdict": "reject"}, "", actor()
        )
        assert result["status"] == "RESOLVED"
        # 写前终判扣留先到并触发纠偏（refs 手工按 R2 口径下发）——门控发现
        # 终态即跳过（不覆盖），helper 不上抛
        _rescope_batch_gray_cases(
            {"sch_first": [case_id]}, "sch_first", {"space": "dev2"}, "Scholar"
        )
        row = _case_row(review_service, case_id)
        assert row.status == "RESOLVED" and row.version == 2
        snapshot = json.loads(row.candidate_snapshot)
        assert [c["vid"] for c in snapshot["existingCandidates"]] == ["sch_first"]  # 终态原样
        assert "_candidateRescope" not in snapshot
        assert _rescope_audits(review_service, case_id) == []
        # 门控直证：终态案再纠偏 = 状态门拒绝
        gated = review_service.rescope_case_candidates(
            case_id, dead_vids={"sch_first"}, graph_space="dev2", node_label="Scholar"
        )
        assert gated == {"rescoped": False, "reason": "status-RESOLVED"}

    @pytest.mark.asyncio
    async def test_rescope_version_conflict_fails_open_concurrent_state_intact(
        self, review_service, monkeypatch
    ):
        """场景3b 纠偏 CAS 版本冲突（案仍 OPEN）：审查读后并发写者先落一版
        ——CAS 拒绝上抛（不盲写覆盖并发修改）；helper 层 fail-open 吞掉不阻断
        写图；并发版本/候选原样保留；A3 仍拦幻影 merge，案可提交；冲突消解
        后重纠一次即恢复（rescope 幂等可重试）。"""
        from sqlalchemy import update as sa_update

        import service.entity_disambiguation as ed
        from service.temporal_workflows import (
            _rescope_batch_gray_cases,
            resolve_entity_batch,
            write_records,
        )

        graph = use_graph(monkeypatch, FakeGraph(recall={"Scholar": []}))
        use_space_client(monkeypatch, graph)
        out = await resolve_entity_batch(_resolve_request([dict(FIRST), dict(LATER)]))
        # 写入失败一次再重试成功：案发布后 sch_first 已落图——候选此刻真实；
        # 但把 sch_first 视作 dead 纠偏（重跑口径）仍成立：候选应换为 RSCH
        await write_records(
            _write_request([dict(r) for r in out["records"]], deferred=out["deferredGray"])
        )
        [(case_id, _, _)] = _cases(review_service)
        graph.recall["Scholar"] = [dict(RSCH_ROW)]
        graph.nodes.add("sch_rsch")
        # 在「读案之后、CAS 之前」注入并发写者：rescope 在读案与更新之间必经
        # eligible_candidates（纯函数），借道它先把版本落一版（version+7）
        orig_eligible = ed.eligible_candidates

        def racing_eligible(*args, **kwargs):
            with review_service.sf.begin() as s2:
                s2.execute(
                    sa_update(ReviewCase)
                    .where(ReviewCase.id == case_id)
                    .values(version=ReviewCase.version + 7)
                )
            return orig_eligible(*args, **kwargs)

        monkeypatch.setattr(ed, "eligible_candidates", racing_eligible)
        with pytest.raises(ReviewConflictError):
            review_service.rescope_case_candidates(
                case_id, dead_vids={"sch_first"}, graph_space="dev2", node_label="Scholar"
            )
        ed.eligible_candidates = orig_eligible  # 竞争注入只此一次
        # 并发写者的成果不被覆盖：版本已到 8、候选仍原样、无纠偏审计
        row = _case_row(review_service, case_id)
        assert row.version == 8 and row.status == "OPEN"
        snapshot = json.loads(row.candidate_snapshot)
        assert [c["vid"] for c in snapshot["existingCandidates"]] == ["sch_first"]
        assert "_candidateRescope" not in snapshot
        # helper 层 fail-open：CAS 冲突上抛被吞，写前终判照常完成（类级补丁，
        # 覆盖模块级 manual_review_service 实例的调用路径）
        real_rescope = ManualReviewService.rescope_case_candidates

        def conflict(*args, **kwargs):
            raise ReviewConflictError("版本竞争")

        monkeypatch.setattr(ManualReviewService, "rescope_case_candidates", conflict)
        _rescope_batch_gray_cases(
            {"sch_first": [case_id]}, "sch_first", {"space": "dev2"}, "Scholar"
        )
        # A3 仍拦幻影 merge；案保持可提交（并发版本 8 未被占）
        graph.nodes.discard("sch_first")  # 表达「先到实际未落图」的终局失败口径
        with pytest.raises(ReviewValidationError) as ei:
            review_service.submit(
                case_id,
                8,
                "entity-confirm",
                {"entityVerdict": "merge", "targetEntityId": "sch_first"},
                "",
                actor(),
            )
        assert "不在图内" in str(ei.value)
        assert _case_row(review_service, case_id).version == 8
        # 恢复机制：冲突消解（无并发）后重纠一次即成功，merge 畅通
        monkeypatch.setattr(ManualReviewService, "rescope_case_candidates", real_rescope)
        fixed = review_service.rescope_case_candidates(
            case_id, dead_vids={"sch_first"}, graph_space="dev2", node_label="Scholar"
        )
        assert fixed["rescoped"] is True and fixed["candidates"] == ["sch_rsch"]
        result = review_service.submit(
            case_id,
            9,
            "entity-confirm",
            {"entityVerdict": "merge", "targetEntityId": "sch_rsch"},
            "",
            actor(),
        )
        assert result["status"] == "RESOLVED"
        assert any('VALUES "sch_rsch"' in w for w in graph.writes)
