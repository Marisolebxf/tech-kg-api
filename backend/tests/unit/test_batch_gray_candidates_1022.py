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
from service.gray_gate import decision_policy
from service.manual_review_domain import ReviewIdentity, ReviewValidationError
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

        # 写前终判时并行 worker 已把同名 RSCH 落图（事故时序）
        graph.recall["Scholar"] = [dict(RSCH_ROW)]
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
