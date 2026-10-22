"""批内灰区幻影候选回归（1022）：批内同名先到记录被写前终判扣留/剔除后，
后到案仍展示永不落图的候选——三层修复的回归测试。

事故链复现（dev2 空间 gkx_compact_full_20261021_01 实录）：chunk 内先到记录
resolve 时图内无同名判 new，后到记录批内同名灰区扣留建案（候选=先到 vid）；
并行来源 worker 在 resolve 与 write 之间把同名节点落图；写前终判重召回后先到
改判灰区扣留、从写集剔除——先到 vid 永不落图，后到案只剩幻影候选，评审
merge 会指向图内不存在的目标。

覆盖：双方扣留纠偏（A1+A2）/ 纠偏失败 fail-open + 裁决端防线兜底（A3）/
多条同名 / 先到自身灰区剔除批内候选 / 重放幂等 / merge 目标存在性终判
（submit 早期 + ``_apply_link_verdict`` 兜底，正常 merge 不受影响）。

补证（PR 前追加，通过标准不止「merge 最终被拒」）：先到判 new 后写入失败
（瞬态重试自愈 + 终局失败大声拦截且案可处置）/ 写前扣留与 resolve 新建案
满足「有效同名候选 + 真实判定灰区」/ 候选纠偏 CAS 版本冲突与并发终态保护。
"""

from __future__ import annotations

import json
import re
from io import BytesIO
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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
# nodes 集合判存在性——A3 裁决端 merge 目标终判需要）
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


class FakeGraph:
    """按查询形状分发的假图客户端（同名召回 / 端点探针 / FETCH / DESCRIBE）。

    ``nodes`` 决定 ``get_node`` 存在性（A3 merge 目标存在性终判）。
    """

    def __init__(self, *, recall=None, existing=None, nodes=None, tag_columns=None):
        self.recall: dict[str, list[dict[str, Any]]] = recall or {}
        self.existing = set(existing or ())
        self.nodes = set(nodes or ())
        self.tag_columns = tag_columns or {"Scholar": ["name"], "Organization": ["name"]}
        self.writes: list[str] = []
        self.edges: list[tuple] = []
        self.reads: list[str] = []

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
        if query.lstrip().startswith("DESCRIBE"):
            return _result([])
        if "WHERE id(v) IN [" in query:
            return _result([{"vid": v} for v in sorted(self.existing)])
        if query.startswith("MATCH (v:`"):
            tag = re.search(r"MATCH \(v:`([^`]+)`\)", query).group(1)
            return _result([dict(row) for row in self.recall.get(tag, [])])
        if query.startswith("FETCH PROP ON"):
            return _result([])  # 顶点不存在 → 空合并
        raise AssertionError(f"意外读查询: {query}")

    def execute_write(self, query: str, params: Any = None):
        self.writes.append(query)
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
    """关近邻路/写前守卫开关/同名锁/VID 锁（守卫函数本身直调）。"""
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


def _cases(review_service: ManualReviewService):
    with review_service.sf() as s:
        rows = s.scalars(select(ReviewCase).where(ReviewCase.template_id == "T_LINK")).all()
        return [(r.id, r.diagnosis, json.loads(r.candidate_snapshot)) for r in rows]


def _case_row(review_service: ManualReviewService, case_id: str) -> ReviewCase:
    with review_service.sf() as s:
        return s.get(ReviewCase, case_id)


# ---------------------------------------------------------------------------
# 事故复现 + 三层修复（A1 阶段3并评 / A2 写前终判纠偏 / A3 裁决端防线）
# ---------------------------------------------------------------------------


class TestBatchGrayPhantomFix:
    @pytest.mark.asyncio
    async def test_incident_double_withhold_rescopes_phantom_candidate(
        self, review_service, monkeypatch
    ):
        """事故复现：resolve 判 new 的先到在写前终判被改判灰区扣留——
        后到案的幻影候选被纠偏为图内真实节点（CANDIDATES_RESCOPED 留痕）。"""
        from service.temporal_workflows import _prewrite_recheck, resolve_entity_batch

        graph = use_graph(monkeypatch, FakeGraph(recall={"Scholar": []}))
        use_space_client(monkeypatch, graph)
        out = await resolve_entity_batch(_resolve_request([dict(FIRST), dict(LATER)]))
        # resolve：先到 new 随批落图；后到批内同名灰区扣留，候选=先到 vid
        assert out["new"] == 1 and out["withheld"] == 1
        assert [r["id"] for r in out["records"]] == ["sch_first"]
        refs = out["batchCandidateRefs"]
        assert list(refs) == ["sch_first"]
        later_case_id = refs["sch_first"][0]
        _, reason, snapshot = _cases(review_service)[0]
        assert [c["vid"] for c in snapshot["existingCandidates"]] == ["sch_first"]
        assert "批内同名" in reason

        # 写前终判时并行 worker 已把同名 RSCH 落图（事故时序；nodes 使 get_node
        # 可验候选真实存在）
        graph.recall["Scholar"] = [dict(RSCH_ROW)]
        graph.nodes.add("sch_rsch")
        kept = [dict(r) for r in out["records"]]
        stats = await _prewrite_recheck(
            graph,
            "Scholar",
            kept,
            graph={"space": "dev2"},
            source_table="dwd.dwd_scholar",
            step_id="source:bind-1#main",
            decision_policy=decision_policy(),
            batch_candidate_refs=refs,
        )
        # 先到被写前终判改判灰区扣留：建自己的案（候选=RSCH 真实节点），写集清空
        assert stats["guardWithheld"] == 1 and kept == []
        cases = {cid: snap for cid, _, snap in _cases(review_service)}
        assert len(cases) == 2
        assert [c["vid"] for c in cases[later_case_id]["existingCandidates"]] == ["sch_rsch"]
        assert cases[later_case_id]["_candidateRescope"]["deadVids"] == ["sch_first"]
        # 纠偏幂等：候选已无死 vid，重放跳过（版本不二跳）
        again = review_service.rescope_case_candidates(
            later_case_id, dead_vids={"sch_first"}, graph_space="dev2", node_label="Scholar"
        )
        assert again["rescoped"] is False and again["reason"] == "no-change"
        row = _case_row(review_service, later_case_id)
        assert row.version == 2  # 只跳了一次
        with review_service.sf() as s:
            audits = s.scalars(
                select(ReviewAuditLog).where(
                    ReviewAuditLog.case_id == later_case_id,
                    ReviewAuditLog.event_type == "CANDIDATES_RESCOPED",
                )
            ).all()
        assert len(audits) == 1
        detail = json.loads(audits[0].detail)
        assert detail["deadVids"] == ["sch_first"]
        assert detail["oldCandidates"] == ["sch_first"]
        assert detail["newCandidates"] == ["sch_rsch"]
        # 新建 T_LINK 有效性补证：两案候选全部是图内真实节点（get_node 可验），
        # 判定均为真实灰区（scoreDecision=gray，分数落在 [0.65, 0.85)），证据
        # 字段真实上桌——不是无候选强建，也不是 merge 误判
        for _, _, snap in _cases(review_service):
            res = snap["_resolution"]
            assert res["scoreDecision"] == "gray"
            assert res["effectiveDisposition"] == "withhold_pending_review"
            assert GRAY_LOW <= res["matchScore"] < MERGE_THRESHOLD
            cands = snap["existingCandidates"]
            assert cands  # 有效同名候选非空才建案
            for cand in cands:
                assert cand["vid"] == "sch_rsch"  # 无幻影候选残留
                assert graph.get_node(cand["vid"]) is not None
                assert GRAY_LOW <= cand["score"] < MERGE_THRESHOLD
                assert cand["propCompared"] == 3

    @pytest.mark.asyncio
    async def test_rescope_failure_fails_open_verdict_guard_holds(
        self, review_service, monkeypatch
    ):
        """纠偏失败（fail-open）不阻断写图，但裁决端 A3 防线拦住幻影 merge。"""
        from service.temporal_workflows import _prewrite_recheck, resolve_entity_batch

        graph = use_graph(monkeypatch, FakeGraph(recall={"Scholar": []}))
        use_space_client(monkeypatch, graph)
        out = await resolve_entity_batch(_resolve_request([dict(FIRST), dict(LATER)]))
        refs = out["batchCandidateRefs"]
        later_case_id = refs["sch_first"][0]

        def boom(*args, **kwargs):
            raise RuntimeError("图库不可达")

        monkeypatch.setattr(review_service, "rescope_case_candidates", boom)
        graph.recall["Scholar"] = [dict(RSCH_ROW)]
        kept = [dict(r) for r in out["records"]]
        # fail-open：纠偏抛错只记 warning，写前终判本身不受影响
        stats = await _prewrite_recheck(
            graph,
            "Scholar",
            kept,
            graph={"space": "dev2"},
            source_table="dwd.dwd_scholar",
            step_id="source:bind-1#main",
            decision_policy=decision_policy(),
            batch_candidate_refs=refs,
        )
        assert stats["guardWithheld"] == 1 and kept == []
        # 后到案未纠偏（仍幻影候选、版本未动）
        _, _, snapshot = next(
            (cid, r, s) for cid, r, s in _cases(review_service) if cid == later_case_id
        )
        assert [c["vid"] for c in snapshot["existingCandidates"]] == ["sch_first"]
        assert _case_row(review_service, later_case_id).version == 1
        # A3 兜底：merge 幻影目标被拒，案保持可提交（版本未占）
        with pytest.raises(ReviewValidationError) as ei:
            review_service.submit(
                later_case_id,
                1,
                "entity-confirm",
                {"entityVerdict": "merge", "targetEntityId": "sch_first"},
                "",
                actor(),
            )
        assert "不在图内" in str(ei.value)
        row = _case_row(review_service, later_case_id)
        assert row.status == "OPEN" and row.version == 1
        assert graph.writes == []

    @pytest.mark.asyncio
    async def test_multiple_same_name_share_first_candidate_refs(self, review_service, monkeypatch):
        """多条同名：两个后到案都引用先到候选，纠偏清单覆盖全部引用案。"""
        from service.temporal_workflows import resolve_entity_batch

        use_graph(monkeypatch, FakeGraph(recall={"Scholar": []}))
        out = await resolve_entity_batch(_resolve_request([dict(FIRST), dict(LATER), dict(LATER2)]))
        assert out["new"] == 1 and out["withheld"] == 2
        assert [r["id"] for r in out["records"]] == ["sch_first"]
        refs = out["batchCandidateRefs"]
        assert sorted(refs) == ["sch_first"] and len(refs["sch_first"]) == 2
        for cid, reason, snapshot in _cases(review_service):
            assert [c["vid"] for c in snapshot["existingCandidates"]] == ["sch_first"]
            assert "批内同名" in reason
            assert cid in refs["sch_first"]

    @pytest.mark.asyncio
    async def test_first_itself_gray_excludes_batch_candidate(self, review_service, monkeypatch):
        """先到自身判灰区（扣留）：批内候选剔除，两案都只指向图内真实节点。"""
        from service.temporal_workflows import resolve_entity_batch

        use_graph(monkeypatch, FakeGraph(recall={"Scholar": [dict(RSCH_ROW)]}))
        out = await resolve_entity_batch(_resolve_request([dict(FIRST), dict(LATER)]))
        assert out["withheld"] == 2 and out["records"] == []
        assert "batchCandidateRefs" not in out
        cases = _cases(review_service)
        assert len(cases) == 2
        for _, reason, snapshot in cases:
            vids = [c["vid"] for c in snapshot["existingCandidates"]]
            assert vids == ["sch_rsch"]  # 无一案引用永不落图的先到 vid
            assert "批内同名" not in reason

    @pytest.mark.asyncio
    async def test_resolve_replay_registers_no_refs(self, review_service, monkeypatch):
        """重放：后到 R2 并入既有案（不重复建案），不再登记纠偏引用。"""
        from service.temporal_workflows import resolve_entity_batch

        use_graph(monkeypatch, FakeGraph(recall={"Scholar": []}))
        request = _resolve_request([dict(FIRST), dict(LATER)])
        first = await resolve_entity_batch(dict(request, records=[dict(FIRST), dict(LATER)]))
        assert list(first["batchCandidateRefs"]) == ["sch_first"]
        second = await resolve_entity_batch(dict(request, records=[dict(FIRST), dict(LATER)]))
        assert second["withheld"] == 1  # 后到并入既有案
        assert "batchCandidateRefs" not in second
        assert len(_cases(review_service)) == 1

    @pytest.mark.asyncio
    async def test_v1_path_result_shape_unaffected(self, review_service, monkeypatch):
        """v1 请求（无 decisionPolicy）不走纠偏链，返回形状不变。"""
        from service.temporal_workflows import resolve_entity_batch

        use_graph(monkeypatch, FakeGraph(recall={"Scholar": []}))
        request = _resolve_request([dict(FIRST), dict(LATER)])
        del request["decisionPolicy"]
        out = await resolve_entity_batch(request)
        assert "batchCandidateRefs" not in out
        assert out["records"] == [dict(FIRST)]


# ---------------------------------------------------------------------------
# 裁决端存在性终判（A3）：submit 早期校验 + _apply_link_verdict 兜底
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
        },
        object_id="org_new_1",
        object_name="示例研究院",
        node_label="Organization",
        reason="消歧得分 0.80 落入灰区",
        confidence=0.9,
        graph_space="dev2",
        template_id="T_LINK",
    )
    value.update(overrides)
    return value


class TestVerdictTargetExistence:
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


# ---------------------------------------------------------------------------
# 补证（PR 前）：先到判 new 后写入失败 / 新建案有效性 / 纠偏 CAS 冲突
# ---------------------------------------------------------------------------


class TestEvidenceSupplement1022:
    """三场景补证：通过标准不止「merge 最终被拒」——新建 T_LINK 必须满足
    「有效同名候选 + 真实判定灰区」，幻影候选滞留路径必须大声报错（非静默）
    且案可处置、有恢复机制。
    """

    @pytest.mark.asyncio
    async def test_first_write_transient_failure_self_heals_on_retry(
        self, review_service, monkeypatch
    ):
        """场景1a 先到判 new 后写入失败（瞬态）：INSERT 失败上抛触发活动重试，
        重试重跑写前终判——先到无既有案可命中仍判 new 照写；先到落图后后到
        案候选由幻影成真，merge 一次通过（自愈链，无需纠偏）。"""
        from service.temporal_workflows import _prewrite_recheck, resolve_entity_batch

        graph = use_graph(monkeypatch, FakeGraph(recall={"Scholar": []}))
        use_space_client(monkeypatch, graph)
        out = await resolve_entity_batch(_resolve_request([dict(FIRST), dict(LATER)]))
        refs = out["batchCandidateRefs"]
        later_case_id = refs["sch_first"][0]
        # 第一次尝试：写前终判放行（图内无同名），INSERT 随后失败——以「图内
        # 仍无该节点」表达失败后的图状态（activity 上抛，Temporal 同请求重试）
        kept = [dict(r) for r in out["records"]]
        stats = await _prewrite_recheck(
            graph,
            "Scholar",
            kept,
            graph={"space": "dev2"},
            source_table="dwd.dwd_scholar",
            step_id="source:bind-1#main",
            decision_policy=decision_policy(),
            batch_candidate_refs=refs,
        )
        assert stats["guardWithheld"] == 0 and [r["id"] for r in kept] == ["sch_first"]
        assert graph.get_node("sch_first") is None  # 写入失败：先到未落图
        # 重试：同一请求重跑写前终判——不因重试被扣留（先到无既有案）
        retry_records = [dict(FIRST)]
        stats2 = await _prewrite_recheck(
            graph,
            "Scholar",
            retry_records,
            graph={"space": "dev2"},
            source_table="dwd.dwd_scholar",
            step_id="source:bind-1#main",
            decision_policy=decision_policy(),
            batch_candidate_refs=refs,
        )
        assert stats2["guardWithheld"] == 0 and [r["id"] for r in retry_records] == ["sch_first"]
        assert len(_cases(review_service)) == 1  # 先到判 new：无有效候选不建案
        # 重试写入成功：先到落图，后到案候选成真——A3 校验通过，merge 畅通
        graph.nodes.add("sch_first")
        result = review_service.submit(
            later_case_id,
            1,
            "entity-confirm",
            {"entityVerdict": "merge", "targetEntityId": "sch_first"},
            "",
            actor(),
        )
        assert result["status"] == "RESOLVED"
        assert any('VALUES "sch_first"' in w for w in graph.writes)

    @pytest.mark.asyncio
    async def test_first_write_terminal_failure_phantom_is_loud_and_disposable(
        self, review_service, monkeypatch
    ):
        """场景1b 先到判 new 后写入终局失败：写前未扣留 → 无纠偏触发点，后到
        案确实滞留幻影候选——但绝不静默：A3 大声拒绝 merge（不凭空建点）、案
        保持可提交且可驳回处置不卡死；执行失败水位不推进，重跑按场景1a 自愈。"""
        from service.temporal_workflows import _prewrite_recheck, resolve_entity_batch

        graph = use_graph(monkeypatch, FakeGraph(recall={"Scholar": []}))
        use_space_client(monkeypatch, graph)
        out = await resolve_entity_batch(_resolve_request([dict(FIRST), dict(LATER)]))
        refs = out["batchCandidateRefs"]
        later_case_id = refs["sch_first"][0]
        kept = [dict(r) for r in out["records"]]
        stats = await _prewrite_recheck(
            graph,
            "Scholar",
            kept,
            graph={"space": "dev2"},
            source_table="dwd.dwd_scholar",
            step_id="source:bind-1#main",
            decision_policy=decision_policy(),
            batch_candidate_refs=refs,
        )
        assert stats["guardWithheld"] == 0 and [r["id"] for r in kept] == ["sch_first"]
        assert graph.get_node("sch_first") is None  # 终局失败：先到永未落图
        assert len(_cases(review_service)) == 1  # 无有效候选不建案：先到零案
        # A3：幻影 merge 大声拒绝，事务回滚不留副作用，案保持可提交
        with pytest.raises(ReviewValidationError) as ei:
            review_service.submit(
                later_case_id,
                1,
                "entity-confirm",
                {"entityVerdict": "merge", "targetEntityId": "sch_first"},
                "",
                actor(),
            )
        assert "不在图内" in str(ei.value)
        row = _case_row(review_service, later_case_id)
        assert row.status == "OPEN" and row.version == 1
        assert graph.writes == []
        # 恢复路径：评审员驳回处置（reject 不做图写）——案不卡死
        result = review_service.submit(
            later_case_id, 1, "reject-candidate", {"entityVerdict": "reject"}, "", actor()
        )
        assert result["status"] == "RESOLVED"
        assert graph.writes == []

    @pytest.mark.asyncio
    async def test_prewrite_withheld_new_case_valid_candidate_real_gray(
        self, review_service, monkeypatch
    ):
        """场景2 写前扣留新建案的有效性：先到被写前终判改判灰区建案——候选
        =图内真实节点（get_node 非 None），判定=真实灰区（分数落在
        [GRAY_LOW, MERGE_THRESHOLD)，证据字段上桌，stage=写前终判）；resolve
        建的后到案纠偏后同样满足有效候选 + 真实 gray。"""
        from service.temporal_workflows import _prewrite_recheck, resolve_entity_batch

        graph = use_graph(monkeypatch, FakeGraph(recall={"Scholar": []}))
        use_space_client(monkeypatch, graph)
        out = await resolve_entity_batch(_resolve_request([dict(FIRST), dict(LATER)]))
        refs = out["batchCandidateRefs"]
        later_case_id = refs["sch_first"][0]
        graph.recall["Scholar"] = [dict(RSCH_ROW)]
        graph.nodes.add("sch_rsch")
        kept = [dict(r) for r in out["records"]]
        stats = await _prewrite_recheck(
            graph,
            "Scholar",
            kept,
            graph={"space": "dev2"},
            source_table="dwd.dwd_scholar",
            step_id="source:bind-1#main",
            decision_policy=decision_policy(),
            batch_candidate_refs=refs,
        )
        assert stats["guardWithheld"] == 1 and kept == []
        cases = {
            snap["_incoming"]["vid"]: (cid, reason, snap)
            for cid, reason, snap in _cases(review_service)
        }
        # 写前终判为「先到」新建的案：真实 gray + 图内真实候选
        first_case_id, first_reason, first_snap = cases["sch_first"]
        res = first_snap["_resolution"]
        assert res["scoreDecision"] == "gray"
        assert res["effectiveDisposition"] == "withhold_pending_review"
        assert GRAY_LOW <= res["matchScore"] < MERGE_THRESHOLD
        assert res["thresholds"]["merge"] == 0.85 and res["thresholds"]["grayLow"] == 0.65
        assert "写前终判" in first_reason and "灰区" in first_reason
        cands = first_snap["existingCandidates"]
        assert len(cands) == 1 and cands[0]["vid"] == "sch_rsch"
        assert graph.get_node(cands[0]["vid"]) is not None
        assert GRAY_LOW <= cands[0]["score"] < MERGE_THRESHOLD
        assert cands[0]["propCompared"] == 3 and cands[0]["propMatched"] == 1
        assert first_case_id != later_case_id  # 各自独立成案
        # resolve 建的后到案（纠偏后）：同样真实 gray + 图内真实候选
        _, _, later_snap = cases["sch_later"]
        lres = later_snap["_resolution"]
        assert lres["scoreDecision"] == "gray"
        assert GRAY_LOW <= lres["matchScore"] < MERGE_THRESHOLD
        later_cands = later_snap["existingCandidates"]
        assert [c["vid"] for c in later_cands] == ["sch_rsch"]
        for cand in later_cands:
            assert graph.get_node(cand["vid"]) is not None
            assert GRAY_LOW <= cand["score"] < MERGE_THRESHOLD

    @pytest.mark.asyncio
    async def test_rescope_skips_resolved_case_concurrent_verdict_wins(
        self, review_service, monkeypatch
    ):
        """场景3a 纠偏遇并发终态：评审员先一步驳回（RESOLVED）——门控跳过
        纠偏，终态决议/候选/版本不被覆盖（不会把已结案改回可合并状态）。"""
        from service.temporal_workflows import _prewrite_recheck, resolve_entity_batch

        graph = use_graph(monkeypatch, FakeGraph(recall={"Scholar": []}))
        use_space_client(monkeypatch, graph)
        out = await resolve_entity_batch(_resolve_request([dict(FIRST), dict(LATER)]))
        refs = out["batchCandidateRefs"]
        later_case_id = refs["sch_first"][0]
        # 并发写者：评审员先驳回后到案（终态，version 1→2）
        result = review_service.submit(
            later_case_id, 1, "reject-candidate", {"entityVerdict": "reject"}, "", actor()
        )
        assert result["status"] == "RESOLVED"
        # 写前终判扣留先到并触发纠偏——门控发现终态即跳过（不覆盖）
        graph.recall["Scholar"] = [dict(RSCH_ROW)]
        graph.nodes.add("sch_rsch")
        kept = [dict(r) for r in out["records"]]
        stats = await _prewrite_recheck(
            graph,
            "Scholar",
            kept,
            graph={"space": "dev2"},
            source_table="dwd.dwd_scholar",
            step_id="source:bind-1#main",
            decision_policy=decision_policy(),
            batch_candidate_refs=refs,
        )
        assert stats["guardWithheld"] == 1 and kept == []
        row = _case_row(review_service, later_case_id)
        assert row.status == "RESOLVED" and row.version == 2
        snapshot = json.loads(row.candidate_snapshot)
        assert [c["vid"] for c in snapshot["existingCandidates"]] == ["sch_first"]  # 终态原样
        assert "_candidateRescope" not in snapshot
        with review_service.sf() as s:
            audits = s.scalars(
                select(ReviewAuditLog).where(
                    ReviewAuditLog.case_id == later_case_id,
                    ReviewAuditLog.event_type == "CANDIDATES_RESCOPED",
                )
            ).all()
        assert audits == []
        # 门控直证：终态案再纠偏 = 状态门拒绝
        gated = review_service.rescope_case_candidates(
            later_case_id, dead_vids={"sch_first"}, graph_space="dev2", node_label="Scholar"
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
            _prewrite_recheck,
            _rescope_batch_gray_cases,
            resolve_entity_batch,
        )

        graph = use_graph(monkeypatch, FakeGraph(recall={"Scholar": []}))
        use_space_client(monkeypatch, graph)
        out = await resolve_entity_batch(_resolve_request([dict(FIRST), dict(LATER)]))
        refs = out["batchCandidateRefs"]
        later_case_id = refs["sch_first"][0]
        graph.recall["Scholar"] = [dict(RSCH_ROW)]
        graph.nodes.add("sch_rsch")
        # 在「读案之后、CAS 之前」注入并发写者：rescope 在读案与更新之间必经
        # eligible_candidates（纯函数），借道它先把版本落一版（version+7）
        orig_eligible = ed.eligible_candidates

        def racing_eligible(*args, **kwargs):
            with review_service.sf.begin() as s2:
                s2.execute(
                    sa_update(ReviewCase)
                    .where(ReviewCase.id == later_case_id)
                    .values(version=ReviewCase.version + 7)
                )
            return orig_eligible(*args, **kwargs)

        monkeypatch.setattr(ed, "eligible_candidates", racing_eligible)
        with pytest.raises(ReviewConflictError):
            review_service.rescope_case_candidates(
                later_case_id, dead_vids={"sch_first"}, graph_space="dev2", node_label="Scholar"
            )
        ed.eligible_candidates = orig_eligible  # 竞争注入只此一次
        # 并发写者的成果不被覆盖：版本已到 8、候选仍原样、无纠偏审计
        row = _case_row(review_service, later_case_id)
        assert row.version == 8 and row.status == "OPEN"
        snapshot = json.loads(row.candidate_snapshot)
        assert [c["vid"] for c in snapshot["existingCandidates"]] == ["sch_first"]
        assert "_candidateRescope" not in snapshot
        # helper 层 fail-open：CAS 冲突上抛被吞，写前终判照常完成
        real_rescope = review_service.rescope_case_candidates

        def conflict(*args, **kwargs):
            raise ReviewConflictError("版本竞争")

        monkeypatch.setattr(review_service, "rescope_case_candidates", conflict)
        _rescope_batch_gray_cases(refs, "sch_first", {"space": "dev2"}, "Scholar")  # 不上抛
        kept = [dict(r) for r in out["records"]]
        stats = await _prewrite_recheck(
            graph,
            "Scholar",
            kept,
            graph={"space": "dev2"},
            source_table="dwd.dwd_scholar",
            step_id="source:bind-1#main",
            decision_policy=decision_policy(),
            batch_candidate_refs=refs,
        )
        assert stats["guardWithheld"] == 1 and kept == []
        # A3 仍拦幻影 merge；案保持可提交（并发版本 8 未被占）
        with pytest.raises(ReviewValidationError) as ei:
            review_service.submit(
                later_case_id,
                8,
                "entity-confirm",
                {"entityVerdict": "merge", "targetEntityId": "sch_first"},
                "",
                actor(),
            )
        assert "不在图内" in str(ei.value)
        assert _case_row(review_service, later_case_id).version == 8
        # 恢复机制：冲突消解（无并发）后重纠一次即成功，merge 畅通
        monkeypatch.setattr(review_service, "rescope_case_candidates", real_rescope)
        fixed = review_service.rescope_case_candidates(
            later_case_id, dead_vids={"sch_first"}, graph_space="dev2", node_label="Scholar"
        )
        assert fixed["rescoped"] is True and fixed["candidates"] == ["sch_rsch"]
        result = review_service.submit(
            later_case_id,
            9,
            "entity-confirm",
            {"entityVerdict": "merge", "targetEntityId": "sch_rsch"},
            "",
            actor(),
        )
        assert result["status"] == "RESOLVED"
        assert any('VALUES "sch_rsch"' in w for w in graph.writes)
