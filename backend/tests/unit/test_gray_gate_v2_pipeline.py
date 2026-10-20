"""gray-gate-v2 流水线 activity 单测：eligibility / 证据 v2 / resolve v2 失败关闭 /
pending 旁路真实灰区门控 / 关系写边失败关闭链（覆写→park→端点终判）/ 双流形状。

假图客户端按查询形状分发（tag 限定同名召回 / 端点存在性探针 / FETCH /
DESCRIBE），审核服务走 sqlite 内存库（manual_review_service 打桩替换）。
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
from temporalio.exceptions import ApplicationError

from db_model.base import Base
from db_model.manual_review import ReviewCase, ReviewCaseSource
from db_model.schema_management import GraphSchemaDefinition
from service import extract_payload_store as store
from service.gray_gate import decision_policy
from service.manual_review_production import ManualReviewService

# ---------------------------------------------------------------------------
# 测试基础设施
# ---------------------------------------------------------------------------


class FakeBody(BytesIO):
    def close(self) -> None:  # noqa: D102
        pass


class FakeS3:
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

    def dumped(self, key: str) -> Any:
        return store.load_extract_payload_json(key)


def _result(rows):
    return SimpleNamespace(records=list(rows))


class FakeGraph:
    """按查询形状分发的假图客户端。

    - ``recall``：tag → [候选行]（同名召回 MATCH，props 决定显示名与评分）；
    - ``existing``：端点存在性探针命中的 vid 集（其余=未知端点）；
    - ``writes``：所有 execute_write 语句（INSERT VERTEX/EDGE 断言用）。
    """

    def __init__(self, *, recall=None, existing=None, tag_columns=None):
        self.recall: dict[str, list[dict[str, Any]]] = recall or {}
        self.existing = set(existing or ())
        self.tag_columns = tag_columns or {"Person": ["name"], "Scholar": ["name"]}
        self.writes: list[str] = []
        self.reads: list[str] = []

    def connect(self) -> None:
        pass

    def close(self) -> None:
        pass

    def execute_query(self, query: str, params: Any = None):
        if query.startswith("DESCRIBE TAG"):
            tag = re.search(r"DESCRIBE TAG `([^`]+)`", query).group(1)
            cols = self.tag_columns.get(tag, ["name"])
            return _result([{"Field": c, "Type": "string", "Null": "YES"} for c in cols])
        raise AssertionError(f"意外查询: {query}")

    def execute_read(self, query: str, params: Any = None):
        self.reads.append(query)
        if query.lstrip().startswith("DESCRIBE"):
            return _result([])
        if "WHERE id(v) IN [" in query:
            # 端点存在性终判：返回已知存在的 vid
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


@pytest.fixture
def pipeline_env(monkeypatch: pytest.MonkeyPatch):
    """关近邻路/写前守卫/VID 锁（本文件只验证 v2 分支判定本身）。"""
    monkeypatch.setenv("ENTITY_DISAMBIGUATION_MILVUS_RECALL", "0")
    monkeypatch.setenv("ENTITY_DISAMBIGUATION_PREWRITE_RECHECK", "0")
    monkeypatch.setenv("ENTITY_DISAMBIGUATION_NAME_LOCK", "0")
    monkeypatch.setenv("ENTITY_WRITE_VID_LOCK_ENABLED", "0")


@pytest.fixture
def fake_s3(monkeypatch: pytest.MonkeyPatch) -> FakeS3:
    fake = FakeS3()
    monkeypatch.setattr("infra.s3.get_schema_s3_storage", lambda: fake)
    return fake


def use_graph(monkeypatch: pytest.MonkeyPatch, graph: FakeGraph) -> FakeGraph:
    import infra.graph_db.client as graph_client_module

    monkeypatch.setattr(graph_client_module, "TRSGraphClient", lambda settings: graph)
    return graph


def schema_catalog(monkeypatch: pytest.MonkeyPatch, *labels: str, space: str = "dev2") -> None:
    """写入描述符门控用的平台目录（kg_schema_definition：entity + ddl succeeded）。

    kg_schema_definition 挂在 service.workflow_models 的独立 Base 上（与
    db_model 业务库解耦），两套 metadata 都要建。
    """
    from service.workflow_models import Base as WorkflowBase

    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    WorkflowBase.metadata.create_all(engine)
    with sessionmaker(engine)() as s:
        for label in labels:
            s.add(
                GraphSchemaDefinition(
                    schema_key=f"sk-{label}",
                    graph_space=space,
                    kind="entity",
                    name=label,
                    label=label,
                    ddl_status="succeeded",
                    is_deleted=False,
                )
            )
        s.commit()
    import infra.mysql as mysql_module

    monkeypatch.setattr(mysql_module, "get_session_factory", lambda: sessionmaker(engine))


def _cases(review_service: ManualReviewService, template="T_LINK"):
    with review_service.sf() as s:
        rows = s.scalars(select(ReviewCase).where(ReviewCase.template_id == template)).all()
        return [(r.id, json.loads(r.candidate_snapshot)) for r in rows]


def _app_error_type(exc_info) -> str:
    return exc_info.value.type


# ---------------------------------------------------------------------------
# eligibility 前置过滤 + 证据 v2（纯函数层）
# ---------------------------------------------------------------------------


class TestEligibilityAndEvidence:
    def test_eligibility_filters_self_and_non_same_name(self):
        from service.entity_disambiguation import eligible_candidates

        candidates = [
            {"vid": "v_self", "name": "张三"},
            {"vid": "v_same", "name": "张三"},
            {"vid": "v_diff", "name": "张四"},  # 近邻路召回的异名候选：只作诊断
            {"vid": "v_norm", "name": " 张三 "},  # 归一后同名
        ]
        eligible, info = eligible_candidates(
            "张三", "v_self", candidates, graph_space="dev2", node_label="Scholar"
        )
        assert [c["vid"] for c in eligible] == ["v_same", "v_norm"]
        assert info == {
            "skippedSelfVid": 1,
            "skippedNonSameName": 1,
            "graphSpace": "dev2",
            "nodeLabel": "Scholar",
        }

    def test_empty_incoming_name_skips_all(self):
        from service.entity_disambiguation import eligible_candidates

        eligible, info = eligible_candidates("", None, [{"vid": "v", "name": "x"}])
        assert eligible == []
        assert info["skippedNonSameName"] == 1

    def test_evidence_v2_recomputes_agreement(self):
        # comparedProps 布尔化（零业务值）：propMatched/propCompared 可精确重算
        from service.entity_disambiguation import score_candidate

        _, detail = score_candidate(
            "张三",
            {"org": "A", "city": "X", "email": "E1"},
            "张三",
            {"org": "A", "city": "Y", "email": "E2"},
        )
        assert detail["propCompared"] == 3
        assert detail["propMatched"] == 1
        assert detail["propsAgree"] == round(1 / 3, 3)
        assert detail["comparedProps"] == [
            {"key": "org", "match": True, "side": "both"},
            {"key": "city", "match": False, "side": "both"},
            {"key": "email", "match": False, "side": "both"},
        ]

    def test_recall_envelope_carries_route_status(self, monkeypatch):
        from service.entity_disambiguation import (
            ROUTE_DEGRADED,
            ROUTE_TRUE_ZERO,
            recall_candidates_envelope,
        )

        monkeypatch.setenv("ENTITY_DISAMBIGUATION_MILVUS_RECALL", "0")
        graph = FakeGraph()
        envelope = recall_candidates_envelope(graph, "Scholar", ["张三"], space="dev2")
        assert envelope["routes"] == {"exact": ROUTE_TRUE_ZERO, "near": ROUTE_DEGRADED}
        assert envelope["candidates"] == {}
        graph.recall["Scholar"] = [{"vid": "sch_9", "props": {"name": "张三", "org": "A"}}]
        envelope = recall_candidates_envelope(graph, "Scholar", ["张三"], space="dev2")
        assert envelope["routes"]["exact"] == "ok"
        assert list(envelope["candidates"]) == ["张三"]


# ---------------------------------------------------------------------------
# 端点覆写 / 存在性终判（纯 helper）
# ---------------------------------------------------------------------------


class TestEndpointHelpers:
    def test_rewrite_then_filter_order(self):
        from service.temporal_workflows import _apply_endpoint_overrides

        records = [
            {"fromId": "old_1", "toId": "paper_1", "props": {}},  # 改写后保留
            {"fromId": "old_1", "toId": "bad_vid", "props": {}},  # 改写后仍撞无效端点→丢弃
            {"fromId": "good", "toId": "bad_vid", "props": {}},  # 无效端点→丢弃
            {"fromId": "good", "toId": "paper_1", "props": {}},  # 原样保留
        ]
        kept, skipped = _apply_endpoint_overrides(
            records, invalid_vids={"bad_vid"}, rewrite_map={"old_1": "org_9"}
        )
        assert skipped == 2
        assert kept == [
            {"fromId": "org_9", "toId": "paper_1", "props": {}},
            {"fromId": "good", "toId": "paper_1", "props": {}},
        ]

    @pytest.mark.asyncio
    async def test_assert_endpoints_exist_reports_unknown(self):
        from service.temporal_workflows import _assert_endpoints_exist

        graph = FakeGraph(existing={"sch_9", "paper_1"})
        records = [{"fromId": "sch_9", "toId": "paper_1"}, {"fromId": "sch_9", "toId": "ghost"}]
        unknown = await _assert_endpoints_exist(
            graph, records, step_id="s", batch_idx=0, chunk_idx=0
        )
        assert unknown == ["ghost"]

    @pytest.mark.asyncio
    async def test_assert_endpoints_exist_empty_records(self):
        from service.temporal_workflows import _assert_endpoints_exist

        graph = FakeGraph()
        assert await _assert_endpoints_exist(graph, [], step_id="s", batch_idx=0, chunk_idx=0) == []


# ---------------------------------------------------------------------------
# resolve_entity_batch v2：失败关闭 / 真实灰区建案 / 批内同名去重
# ---------------------------------------------------------------------------


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


class TestResolveEntityBatchV2:
    @pytest.mark.asyncio
    async def test_merge_decision_fails_closed_before_any_side_effect(
        self, review_service, pipeline_env, monkeypatch
    ):
        from service.temporal_workflows import resolve_entity_batch

        graph = use_graph(
            monkeypatch,
            FakeGraph(
                recall={"Scholar": [{"vid": "sch_9", "props": {"name": "张三", "org": "A"}}]}
            ),
        )
        records = [{"id": "sch_new", "props": {"name": "张三", "org": "A"}}]
        with pytest.raises(ApplicationError) as ei:
            await resolve_entity_batch(_resolve_request(records))
        # B′：scoreDecision=merge 不是真实灰区——不可重试、零标识符、无副作用
        assert _app_error_type(ei) == "DEFERRED_MERGE_BLOCKED"
        assert ei.value.non_retryable is True
        assert ei.value.details[0] == {
            "stage": "resolve",
            "score": 1.0,
            "autoMergeEnabled": False,
            "policyVersion": "gray-gate-v2",
        }
        assert _cases(review_service) == []
        assert graph.writes == []

    @pytest.mark.asyncio
    async def test_real_gray_creates_case_with_v2_evidence(
        self, review_service, pipeline_env, monkeypatch
    ):
        from service.temporal_workflows import resolve_entity_batch

        use_graph(
            monkeypatch,
            FakeGraph(
                recall={
                    "Scholar": [
                        {
                            "vid": "sch_9",
                            "props": {"name": "张三", "org": "A", "city": "X", "email": "E1"},
                        }
                    ]
                }
            ),
        )
        # 同名 + 3 可比属性 1 命中 → 0.6+0.4/3 ≈ 0.733 ∈ 灰区 [0.65, 0.85)
        records = [
            {"id": "sch_new", "props": {"name": "张三", "org": "A", "city": "Y", "email": "E2"}}
        ]
        out = await resolve_entity_batch(_resolve_request(records))
        assert out["withheld"] == 1 and out["records"] == []
        cases = _cases(review_service)
        assert len(cases) == 1
        _, snapshot = cases[0]
        assert snapshot["_resolution"]["policyVersion"] == "gray-gate-v2"
        assert snapshot["_resolution"]["scoreDecision"] == "gray"
        assert snapshot["_resolution"]["effectiveDisposition"] == "withhold_pending_review"
        assert snapshot["_resolution"]["weights"] == {"name": 0.6, "props": 0.4}
        assert snapshot["_incoming"]["vid"] == "sch_new"
        assert snapshot["_incoming"]["sourceEventBasis"] == "row-hmac"
        # 证据 v2：候选带 comparedProps/propMatched/propCompared
        cand = snapshot["existingCandidates"][0]
        assert cand["vid"] == "sch_9"
        assert cand["propMatched"] == 1 and cand["propCompared"] == 3
        assert any(not p["match"] for p in cand["comparedProps"])
        # 来源账本一行（evidence 只存字段名）
        with review_service.sf() as s:
            src = s.scalar(select(ReviewCaseSource))
            case = s.scalar(select(ReviewCase))
        assert src.case_id == case.id
        assert case.source_count == 1
        assert json.loads(src.evidence)["stage"] == "resolve"

    @pytest.mark.asyncio
    async def test_new_records_pass_through(self, review_service, pipeline_env, monkeypatch):
        from service.temporal_workflows import resolve_entity_batch

        use_graph(monkeypatch, FakeGraph(recall={"Scholar": []}))
        records = [{"id": "sch_a", "props": {"name": "李四"}}]
        out = await resolve_entity_batch(_resolve_request(records))
        assert out["records"] == records and out["new"] == 1
        assert _cases(review_service) == []

    @pytest.mark.asyncio
    async def test_batch_same_name_merge_fails_closed(
        self, review_service, pipeline_env, monkeypatch
    ):
        from service.temporal_workflows import resolve_entity_batch

        graph = use_graph(monkeypatch, FakeGraph())
        # R3：批内同名真实 merge 与阶段 3 同口径统一失败关闭（B′）——不改写
        # id 继续写图（那等于在无 remap 的情况下执行合并）、零副作用、受影响
        # 来源水位不推进；remap 方案 A 落地后手动重跑恢复
        records = [
            {"id": "sch_1", "props": {"name": "张三", "org": "A"}},
            {"id": "sch_2", "props": {"name": "张三", "org": "A"}},
        ]
        with pytest.raises(ApplicationError) as ei:
            await resolve_entity_batch(_resolve_request(records))
        assert _app_error_type(ei) == "DEFERRED_MERGE_BLOCKED"
        assert ei.value.details[0]["stage"] == "resolve-batch-dedupe"
        assert ei.value.non_retryable is True
        assert _cases(review_service) == []  # 零建案副作用
        assert graph.writes == []

    @pytest.mark.asyncio
    async def test_unknown_policy_fails_closed(self, review_service, pipeline_env, monkeypatch):
        from service.temporal_workflows import resolve_entity_batch

        use_graph(monkeypatch, FakeGraph())
        request = _resolve_request([{"id": "x", "props": {"name": "n"}}])
        request["decisionPolicy"] = {"version": "gray-gate-v3"}
        with pytest.raises(ApplicationError) as ei:
            await resolve_entity_batch(request)
        assert _app_error_type(ei) == "UNKNOWN_POLICY_VERSION"

    @pytest.mark.asyncio
    async def test_auto_merge_true_rejected(self, review_service, pipeline_env, monkeypatch):
        from service.temporal_workflows import resolve_entity_batch

        use_graph(monkeypatch, FakeGraph())
        request = _resolve_request([{"id": "x", "props": {"name": "n"}}])
        request["decisionPolicy"] = {**decision_policy(), "autoMergeEnabled": True}
        with pytest.raises(ApplicationError) as ei:
            await resolve_entity_batch(request)
        # v3 auto-merge 未实施：传 true=UNKNOWN_POLICY_VERSION 失败关闭
        assert _app_error_type(ei) == "UNKNOWN_POLICY_VERSION"

    @pytest.mark.asyncio
    async def test_no_policy_runs_v1_path(self, review_service, pipeline_env, monkeypatch):
        from service.temporal_workflows import resolve_entity_batch

        use_graph(monkeypatch, FakeGraph())
        request = _resolve_request([{"id": "sch_a", "props": {"name": "李四"}}])
        del request["decisionPolicy"]
        out = await resolve_entity_batch(request)
        assert out["records"] == [{"id": "sch_a", "props": {"name": "李四"}}]


# ---------------------------------------------------------------------------
# 稳定事件身份前置裁决（R2）：重新评分/副作用之前按既有案处置
# ---------------------------------------------------------------------------


class _GrayRecallGraph:
    """首跑带同名候选（真实落灰区）的图夹具工厂。"""

    @staticmethod
    def make(monkeypatch, with_candidate: bool):
        recall = {
            "Scholar": [
                {
                    "vid": "sch_9",
                    "props": {"name": "张三", "org": "A", "city": "X", "email": "E1"},
                }
            ]
            if with_candidate
            else []
        }
        return use_graph(monkeypatch, FakeGraph(recall=recall))


class TestPriorIngressDisposition:
    @pytest.mark.asyncio
    async def test_rejected_case_replay_stays_rejected_on_recall_change(
        self, review_service, pipeline_env, monkeypatch
    ):
        # R2：reject 后召回退化（重跑时空召回）不得让旧裁决失效复活写图
        from service.temporal_workflows import resolve_entity_batch

        _GrayRecallGraph.make(monkeypatch, with_candidate=True)
        records = [
            {"id": "sch_new", "props": {"name": "张三", "org": "A", "city": "Y", "email": "E2"}}
        ]
        await resolve_entity_batch(_resolve_request(records))
        case_id, _ = _cases(review_service)[0]
        from service.manual_review_domain import ReviewIdentity

        review_service.submit(
            case_id,
            1,
            "reject-candidate",
            {"entityVerdict": "reject"},
            "r2 回归",
            ReviewIdentity("u", "u", frozenset({"reviewer"}), frozenset({"graph"}), "o", "e"),
        )
        # 重跑：空召回（无候选 → 无前置裁决时会判 new 放行写图）
        graph = _GrayRecallGraph.make(monkeypatch, with_candidate=False)
        out = await resolve_entity_batch(_resolve_request(records))
        assert out["priorDropped"] == 1
        assert out["records"] == [] and out["new"] == 0
        assert graph.writes == []
        assert len(_cases(review_service)) == 1  # 不重复建案

    @pytest.mark.asyncio
    async def test_open_case_replay_withholds_without_rescoring(
        self, review_service, pipeline_env, monkeypatch
    ):
        # R2：待裁决案重复命中——并入既有案（来源行幂等），不重新评分建新案
        from service.temporal_workflows import resolve_entity_batch

        _GrayRecallGraph.make(monkeypatch, with_candidate=True)
        records = [
            {"id": "sch_new", "props": {"name": "张三", "org": "A", "city": "Y", "email": "E2"}}
        ]
        first = await resolve_entity_batch(_resolve_request(records))
        assert first["withheld"] == 1
        _GrayRecallGraph.make(monkeypatch, with_candidate=False)
        second = await resolve_entity_batch(_resolve_request(records))
        assert second["withheld"] == 1
        assert len(_cases(review_service)) == 1
        from db_model.manual_review import ReviewCase

        with review_service.sf() as s:
            case = s.scalar(select(ReviewCase))
            assert case.source_count == 1  # 同执行同源记录重放：来源行不加计

    @pytest.mark.asyncio
    async def test_apply_failed_case_replay_fails_closed(
        self, review_service, pipeline_env, monkeypatch
    ):
        # R5/R2：应用失败的案重放 → VERDICT_NOT_APPLIED 失败关闭（不吞入开放案）
        from db_model.manual_review import ReviewVerdictApplication
        from service.temporal_workflows import resolve_entity_batch

        _GrayRecallGraph.make(monkeypatch, with_candidate=True)
        records = [
            {"id": "sch_new", "props": {"name": "张三", "org": "A", "city": "Y", "email": "E2"}}
        ]
        await resolve_entity_batch(_resolve_request(records))
        case_id, _ = _cases(review_service)[0]
        with review_service.sf() as s:
            from db_model.manual_review import ReviewCase as _Case

            case = s.get(_Case, case_id)
            case.status = "APPLY_FAILED"
            s.add(
                ReviewVerdictApplication(
                    case_id=case_id,
                    verdict="create",
                    apply_status="FAILED",
                    created_at=case.created_at,
                    updated_at=case.updated_at,
                )
            )
            s.commit()
        _GrayRecallGraph.make(monkeypatch, with_candidate=False)
        with pytest.raises(ApplicationError) as ei:
            await resolve_entity_batch(_resolve_request(records))
        assert _app_error_type(ei) == "VERDICT_NOT_APPLIED"


class TestIngressIdentity:
    """R4：sourceRecordId 权威 + 运行时摄取列不进事件摘要。"""

    def _material(self, monkeypatch, record):
        from service.temporal_workflows import _gray_ingress_material

        monkeypatch.setenv("GRAY_GATE_DEDUPE_IDENTITY_KEY", "unit-test-identity-key")
        return _gray_ingress_material(
            step_id="source:bind-1#main",
            record=record,
            graph_space="dev2",
            name_tag="Scholar",
        )

    def test_source_record_id_is_authoritative(self, monkeypatch):
        material, _, _ = self._material(
            monkeypatch, {"id": "vid-1", "sourceRecordId": "row-9", "props": {"name": "张三"}}
        )
        assert material[1] == "row-9"  # 来源行主键，不取 vid
        assert material[5] == "vid-1"  # vid 元素保持记录 vid

    def test_falls_back_to_vid_when_no_source_record_id(self, monkeypatch):
        material, _, _ = self._material(monkeypatch, {"id": "vid-1", "props": {"name": "张三"}})
        assert material[1] == "vid-1"

    def test_same_source_row_stable_across_reruns_and_chunks(self, monkeypatch):
        # 跨重跑：脚本重写 ingest_time/update_time/ingest_batch；跨 chunk：
        # step_id 同源绑定恒定——同一源业务行材料不变，重放命中同一案
        first, _, _ = self._material(
            monkeypatch,
            {
                "id": "vid-1",
                "sourceRecordId": "row-9",
                "ingest_time": "2026-10-21 09:00:00",
                "ingest_batch": "run-1",
                "props": {"name": "张三", "update_time": "2026-10-21 09:00:01"},
            },
        )
        second, _, _ = self._material(
            monkeypatch,
            {
                "id": "vid-1",
                "sourceRecordId": "row-9",
                "ingest_time": "2026-10-21 11:30:00",
                "ingest_batch": "run-2",
                "props": {"name": "张三", "update_time": "2026-10-21 11:30:02"},
            },
        )
        assert first == second

    def test_same_vid_different_source_rows_are_distinct_cases(self, monkeypatch):
        # 同 VID 多源行（一条记录出现在多个来源行）：身份键按源行区分，
        # 各自建案（不因同 vid 塌缩成一个事件）
        r1, _, _ = self._material(
            monkeypatch, {"id": "vid-1", "sourceRecordId": "row-1", "props": {"name": "张三"}}
        )
        r2, _, _ = self._material(
            monkeypatch, {"id": "vid-1", "sourceRecordId": "row-2", "props": {"name": "张三"}}
        )
        assert r1 != r2


# ---------------------------------------------------------------------------
# resolve_pending_entities：pending 旁路真实灰区门控
# ---------------------------------------------------------------------------


def _pending_item(name="张三", *, vid=None, props=None, label="Person"):
    from script.relation_extractors_one_relation.patent_matching import pending_entity_vid

    return {
        "kind": "entity",
        "nodeLabel": label,
        "objectId": vid or pending_entity_vid("person", name),
        "objectName": name,
        "candidate": {"name": name, "props": props if props is not None else {"name": name}},
        "reason": "只有姓名证据",
        "confidence": 0.6,
        "evidence": [],
        "sourceTable": "dwd_patent",
        "sourceRecordId": "123:inventors:0",
    }


def _pending_request(items, **overrides):
    request = {
        "graph": {"space": "dev2"},
        "stepId": "source:bind-1#main",
        "batchIdx": 0,
        "chunkIdx": 0,
        "sourceTable": "dwd_patent",
        "pending": items,
        "decisionPolicy": decision_policy(),
    }
    request.update(overrides)
    return request


class TestResolvePendingEntities:
    @pytest.mark.asyncio
    async def test_new_decision_writes_vertex_no_case(
        self, review_service, pipeline_env, monkeypatch
    ):
        from service.temporal_workflows import resolve_pending_entities

        schema_catalog(monkeypatch, "Person")
        graph = use_graph(monkeypatch, FakeGraph(recall={"Person": []}))
        out = await resolve_pending_entities(_pending_request([_pending_item()]))
        assert out == {
            "written": 1,
            "grayCases": 0,
            "skippedInvalidPending": 0,
            "invalidEndpointVids": [],
            "rewriteMap": {},
        }
        assert len(graph.writes) == 1
        assert graph.writes[0].startswith("INSERT VERTEX `Person`")
        assert _cases(review_service) == []

    @pytest.mark.asyncio
    async def test_real_gray_creates_case_only(self, review_service, pipeline_env, monkeypatch):
        from service.temporal_workflows import resolve_pending_entities

        schema_catalog(monkeypatch, "Person")
        name = "张三"
        graph = use_graph(
            monkeypatch,
            FakeGraph(
                recall={
                    "Person": [
                        {
                            "vid": "p_9",
                            "props": {"name": name, "org": "A", "city": "X", "email": "E"},
                        }
                    ]
                }
            ),
        )
        item = _pending_item(name, props={"name": name, "org": "A", "city": "Y", "email": "F"})
        out = await resolve_pending_entities(_pending_request([item]))
        assert out["written"] == 0 and out["grayCases"] == 1
        assert graph.writes == []
        cases = _cases(review_service)
        assert len(cases) == 1
        _, snapshot = cases[0]
        assert snapshot["_resolution"]["policyVersion"] == "gray-gate-v2"
        assert snapshot["_resolution"]["scoreDecision"] == "gray"
        assert snapshot["_incoming"]["sourceTable"] == "dwd_patent"

    @pytest.mark.asyncio
    async def test_merge_decision_fails_closed_before_writes(
        self, review_service, pipeline_env, monkeypatch
    ):
        from service.temporal_workflows import resolve_pending_entities

        schema_catalog(monkeypatch, "Person")
        name = "张三"
        props = {"name": name, "org": "计算所"}
        graph = use_graph(
            monkeypatch,
            FakeGraph(recall={"Person": [{"vid": "p_9", "props": props}]}),
        )
        with pytest.raises(ApplicationError) as ei:
            await resolve_pending_entities(_pending_request([_pending_item(name, props=props)]))
        assert _app_error_type(ei) == "DEFERRED_MERGE_BLOCKED"
        assert ei.value.details[0]["stage"] == "pending"
        assert graph.writes == []
        assert _cases(review_service) == []

    @pytest.mark.asyncio
    async def test_descriptor_gate_failure_marks_invalid_endpoint(
        self, review_service, pipeline_env, monkeypatch
    ):
        from service.temporal_workflows import resolve_pending_entities

        schema_catalog(monkeypatch)  # 目录里没有 Person → 门控不通过
        graph = use_graph(monkeypatch, FakeGraph(recall={"Person": []}))
        item = _pending_item()
        out = await resolve_pending_entities(_pending_request([item]))
        assert out["skippedInvalidPending"] == 1
        assert out["invalidEndpointVids"] == [item["objectId"]]
        assert out["written"] == 0 and out["grayCases"] == 0
        assert graph.writes == []
        assert _cases(review_service) == []

    @pytest.mark.asyncio
    async def test_relation_items_dropped_with_warning(
        self, review_service, pipeline_env, monkeypatch
    ):
        from service.temporal_workflows import resolve_pending_entities

        schema_catalog(monkeypatch, "Person")
        graph = use_graph(monkeypatch, FakeGraph())
        out = await resolve_pending_entities(
            _pending_request(
                [
                    {"kind": "relation", "edgeType": "X", "fromId": "a", "toId": "b"},
                    _pending_item("李四"),
                ]
            )
        )
        assert out["written"] == 1  # 只有实体项处理，关系项丢弃
        assert len(graph.writes) == 1

    @pytest.mark.asyncio
    async def test_missing_identity_fails_closed(self, review_service, pipeline_env, monkeypatch):
        from service.temporal_workflows import resolve_pending_entities

        schema_catalog(monkeypatch, "Person")
        use_graph(monkeypatch, FakeGraph())
        broken = _pending_item()
        broken["objectId"] = ""  # 身份字段缺失
        with pytest.raises(ApplicationError) as ei:
            await resolve_pending_entities(_pending_request([broken]))
        assert _app_error_type(ei) == "UNSTABLE_SOURCE_IDENTITY"

    @pytest.mark.asyncio
    async def test_terminal_reject_replay_drops_and_invalidates(
        self, review_service, pipeline_env, monkeypatch
    ):
        from service.manual_review_domain import ReviewIdentity
        from service.temporal_workflows import resolve_pending_entities

        schema_catalog(monkeypatch, "Person")
        name = "王五"
        props = {"name": name, "org": "A", "city": "X", "email": "E"}
        use_graph(
            monkeypatch,
            FakeGraph(recall={"Person": [{"vid": "p_9", "props": props}]}),
        )
        item = _pending_item(name, props={"name": name, "org": "A", "city": "Y", "email": "F"})
        vid = item["objectId"]
        first = await resolve_pending_entities(_pending_request([item]))
        assert first["grayCases"] == 1
        # 人工驳回（reject → NOT_REQUIRED）
        case_id, _ = _cases(review_service)[0]
        reviewer = ReviewIdentity(
            "u1", "u1", frozenset({"reviewer"}), frozenset({"graph"}), "o", "r"
        )
        review_service.submit(
            case_id, 1, "reject-candidate", {"entityVerdict": "reject"}, "驳回", reviewer
        )
        # 同一 pending 重放：priorVerdict=reject+NOT_REQUIRED → drop_record，
        # vid 进 invalidEndpointVids（引用它的边随后被过滤）
        second = await resolve_pending_entities(_pending_request([item]))
        assert second["grayCases"] == 0 and second["written"] == 0
        assert second["invalidEndpointVids"] == [vid]
        assert second["rewriteMap"] == {}
        assert len(_cases(review_service)) == 1  # 不建新案（逻辑键命中）

    @pytest.mark.asyncio
    async def test_open_case_replay_withholds_into_existing_case(
        self, review_service, pipeline_env, monkeypatch
    ):
        # R2（pending 流）：待裁决案重复命中 → 并入既有案不再建案，行为 withheld
        from service.temporal_workflows import resolve_pending_entities

        schema_catalog(monkeypatch, "Person")
        name = "张三"
        use_graph(
            monkeypatch,
            FakeGraph(
                recall={
                    "Person": [
                        {
                            "vid": "p_9",
                            "props": {"name": name, "org": "A", "city": "X", "email": "E"},
                        }
                    ]
                }
            ),
        )
        item = _pending_item(name, props={"name": name, "org": "A", "city": "Y", "email": "F"})
        first = await resolve_pending_entities(_pending_request([item]))
        assert first["grayCases"] == 1 and first["written"] == 0
        second = await resolve_pending_entities(_pending_request([item]))
        assert second["grayCases"] == 1 and second["written"] == 0
        assert second["invalidEndpointVids"] == [] and second["rewriteMap"] == {}
        assert len(_cases(review_service)) == 1  # 同逻辑键命中：不建新案

    @pytest.mark.asyncio
    async def test_pending_key_shape_downloads_from_s3(
        self, review_service, pipeline_env, monkeypatch, fake_s3
    ):
        from service.temporal_workflows import resolve_pending_entities

        schema_catalog(monkeypatch, "Person")
        use_graph(monkeypatch, FakeGraph())
        key = store.put_extract_payload_json(
            "source:bind-1#main", 0, "pending-00", [_pending_item("赵六")]
        )
        request = _pending_request([], pendingKey=key)
        request.pop("pending")  # 中转形状：pending 键不在，才走 pendingKey 下载
        out = await resolve_pending_entities(request)
        assert out["written"] == 1


# ---------------------------------------------------------------------------
# write_records 关系分支 v2 失败关闭链
# ---------------------------------------------------------------------------


def _relation_request(records, **overrides):
    request = {
        "kind": "relation",
        "name": "AUTHORED_BY",
        "graph": {"space": "dev2"},
        "sourceTable": "dwd.dwd_patent",
        "stepId": "source:bind-1#main",
        "batchIdx": 0,
        "chunkIdx": 0,
        "records": records,
        "decisionPolicy": decision_policy(),
    }
    request.update(overrides)
    return request


class TestWriteRecordsRelationV2:
    @pytest.mark.asyncio
    async def test_override_filter_and_park_chain(self, review_service, pipeline_env, monkeypatch):
        from service.temporal_workflows import write_records

        schema_catalog(monkeypatch, "Person")
        graph = use_graph(monkeypatch, FakeGraph(existing={"sch_9", "paper_1"}))
        # 先造一个 v2 开放案（端点 sch_park 的边应挂进案快照）
        pending_graph_case = review_service.create_direct_case(
            task_id="T",
            execution_id="E",
            step_id="s",
            kind="entity",
            candidate={
                "name": "钱七",
                "newIds": ["sch_park"],
                "existingCandidates": [{"vid": "sch_9", "name": "钱七", "score": 0.8}],
                "_incoming": {"vid": "sch_park", "props": {"name": "钱七"}, "sourceTable": "t"},
                "_pendingRelations": [],
                "_graphSpace": "dev2",
                "_nodeLabel": "Scholar",
                "_resolution": {
                    "policyVersion": "gray-gate-v2",
                    "scoreDecision": "gray",
                    "effectiveDisposition": "withhold_pending_review",
                },
            },
            object_id="sch_park",
            object_name="钱七",
            template_id="T_LINK",
            graph_space="dev2",
        )
        records = [
            {"id": "e1", "fromId": "sch_park", "toId": "paper_1", "props": {"w": 1}},  # 挂案
            {"id": "e2", "fromId": "old_1", "toId": "paper_1", "props": {"w": 2}},  # 改写
            {"id": "e3", "fromId": "sch_9", "toId": "bad_vid", "props": {"w": 3}},  # 无效端点过滤
        ]
        out = await write_records(
            _relation_request(
                records,
                invalidEndpointVids=["bad_vid"],
                rewriteMap={"old_1": "sch_9"},
            )
        )
        assert out["written"] == 1  # e1 挂案、e3 被无效端点过滤，只有 e2（改写后）落图
        # 改写后的边真实写图，端点终判通过
        assert len(graph.writes) == 1
        assert '"old_1"' not in graph.writes[0]
        assert '"sch_9"' in graph.writes[0] and '"paper_1"' in graph.writes[0]
        # 挂案：_pendingRelations 落 v2 案快照
        case_id = pending_graph_case["reviewId"]
        with review_service.sf() as s:
            snapshot = json.loads(
                s.scalar(select(ReviewCase).where(ReviewCase.id == case_id)).candidate_snapshot
            )
        assert snapshot["_pendingRelations"] == [
            {"edgeType": "AUTHORED_BY", "fromId": "sch_park", "toId": "paper_1", "props": {"w": 1}}
        ]

    @pytest.mark.asyncio
    async def test_unknown_endpoint_fails_closed_with_claim_check(
        self, review_service, pipeline_env, monkeypatch, fake_s3
    ):
        from service.temporal_workflows import write_records

        schema_catalog(monkeypatch, "Person")
        use_graph(monkeypatch, FakeGraph(existing={"sch_9"}))  # paper_ghost 不存在
        with pytest.raises(ApplicationError) as ei:
            await write_records(
                _relation_request(
                    [{"id": "e1", "fromId": "sch_9", "toId": "paper_ghost", "props": {}}]
                )
            )
        assert _app_error_type(ei) == "BLOCKED_ENDPOINT_UNKNOWN"
        detail = ei.value.details[0]
        assert set(detail) == {"edgeType", "claimCheckKey", "sha256", "unknownEndpointCount"}
        assert detail["unknownEndpointCount"] == 1
        # claim-check：完整清单归档 S3，错误负载只带 key+摘要（零标识符）
        archived = fake_s3.dumped(detail["claimCheckKey"])
        assert archived == {"unknownEndpoints": ["paper_ghost"]}
        import hashlib

        assert (
            detail["sha256"]
            == hashlib.sha256(json.dumps(["paper_ghost"], ensure_ascii=False).encode()).hexdigest()
        )

    @pytest.mark.asyncio
    async def test_legacy_case_fails_closed_no_silent_write(
        self, review_service, pipeline_env, monkeypatch
    ):
        from service.temporal_workflows import write_records

        schema_catalog(monkeypatch, "Person")
        graph = use_graph(monkeypatch, FakeGraph(existing={"sch_9", "paper_1"}))
        review_service.create_direct_case(
            task_id="T",
            execution_id="E",
            step_id="s",
            kind="entity",
            candidate={
                "name": "孙八",
                "newIds": ["sch_legacy"],
                "existingCandidates": [],
                "_graphSpace": "dev2",
                "_nodeLabel": "Scholar",
                "_resolution": {
                    "policyVersion": "script-pending-gray-v1",
                    "scoreDecision": "gray",
                },
            },
            object_id="sch_legacy",
            object_name="孙八",
            template_id="T_LINK",
            graph_space="dev2",
        )
        with pytest.raises(ApplicationError) as ei:
            await write_records(
                _relation_request(
                    [{"id": "e1", "fromId": "sch_legacy", "toId": "paper_1", "props": {}}]
                )
            )
        assert _app_error_type(ei) == "BLOCKED_BY_LEGACY_CASE"
        assert graph.writes == []  # 不「计数后继续」


# ---------------------------------------------------------------------------
# execute_transform 双流形状：pendingMode=resolve 不再 activity 内强制建案
# ---------------------------------------------------------------------------

PEND_SCRIPT = """
import json


def transform(payload):
    rows = payload.get("rows") or []
    return {
        "entities": [{"id": "n_" + str(r["id"]), "props": {"name": r["name"]}} for r in rows],
        "pendingReview": [
            {
                "kind": "entity",
                "nodeLabel": "Person",
                "objectId": "pending_1",
                "objectName": "陈九",
                "candidate": {"name": "陈九", "props": {"name": "陈九"}},
                "sourceTable": "dwd_patent",
                "sourceRecordId": "9:inventors:0",
            }
        ],
    }
"""


def _transform_request(script_path, **overrides):
    request = {
        "scriptPath": str(script_path),
        "functionName": "transform",
        "source": {"database": "gkx", "table": "dwd_patent"},
        "kind": "entity",
        "timeoutSeconds": 30,
        "selectors": {},
        "definitionId": "schema-extract-pending",
        "stepId": "source:bind-1#main",
        "ctxStepId": "source:bind-1#main",
        "batchIdx": 0,
        "chunkIdx": 0,
        "rows": [{"id": "1", "name": "甲"}],
    }
    request.update(overrides)
    return request


class TestExecuteTransformDualStream:
    @pytest.mark.asyncio
    async def test_resolve_mode_inline_returns_pending_without_forced_case(
        self, review_service, pipeline_env, monkeypatch, tmp_path
    ):
        from service.temporal_workflows import execute_transform

        def _no_forced_review(*args, **kwargs):  # pragma: no cover - 断言不被调用
            raise AssertionError("pendingMode=resolve 不允许 activity 内强制建案")

        monkeypatch.setattr("service.temporal_workflows._enqueue_pending_review", _no_forced_review)
        script = tmp_path / "transform.py"
        script.write_text(PEND_SCRIPT, encoding="utf-8")
        out = await execute_transform(_transform_request(script, pendingMode="resolve"))
        assert out["entities"] == [{"id": "n_1", "props": {"name": "甲"}}]
        assert [i["objectId"] for i in out["pendingReview"]] == ["pending_1"]
        assert _cases(review_service) == []  # 双流：不由 activity 建案

    @pytest.mark.asyncio
    async def test_resolve_mode_s3_archives_pending_key(
        self, review_service, pipeline_env, monkeypatch, fake_s3, tmp_path
    ):
        from service.temporal_workflows import execute_transform

        script = tmp_path / "transform.py"
        script.write_text(PEND_SCRIPT, encoding="utf-8")
        rows_key = store.put_extract_payload_json(
            "source:bind-1#main", 0, "rows-00", [{"id": "1", "name": "甲"}]
        )
        out = await execute_transform(
            _transform_request(script, pendingMode="resolve", rowsKey=rows_key, rows=None)
        )
        assert "pendingKey" in out and out["pendingCount"] == 1
        assert "pendingReview" not in out  # 中转路径不内联挂起清单
        archived = fake_s3.dumped(out["pendingKey"])
        assert [i["objectId"] for i in archived] == ["pending_1"]
        assert _cases(review_service) == []

    @pytest.mark.asyncio
    async def test_legacy_mode_still_enqueues_forced_review(
        self, review_service, pipeline_env, monkeypatch, tmp_path
    ):
        from service import temporal_workflows as tw
        from service.temporal_workflows import execute_transform

        script = tmp_path / "transform.py"
        script.write_text(PEND_SCRIPT, encoding="utf-8")
        calls: list = []
        monkeypatch.setattr(
            tw, "_enqueue_pending_review", lambda req, pending, attempt: calls.append(pending)
        )
        out = await execute_transform(_transform_request(script))
        assert "pendingReview" not in out  # v1：activity 内消化，不随返回值上抛
        assert calls and calls[0][0]["objectId"] == "pending_1"


# ---------------------------------------------------------------------------
# 二次复审回归（R2-b）：已确认人工裁决贯穿到写前守卫最后一步
# ---------------------------------------------------------------------------


def _review_actor():
    from service.manual_review_domain import ReviewIdentity

    return ReviewIdentity("u", "u", frozenset({"reviewer"}), frozenset({"graph"}), "o", "e")


def _resolve_create(review_service, case_id):
    """直审 create（_apply_link_verdict 打桩为无图写成功 → application APPLIED）。"""
    orig = ManualReviewService._apply_link_verdict
    ManualReviewService._apply_link_verdict = (  # type: ignore[method-assign]
        lambda self, c, r: {"applied": True, "vid": r.get("targetEntityId") or c.object_id}
    )
    try:
        review_service.submit(
            case_id, 1, "entity-confirm", {"entityVerdict": "create"}, "r2b 回归", _review_actor()
        )
    finally:
        ManualReviewService._apply_link_verdict = orig  # type: ignore[method-assign]


def _write_entity_request(records, **overrides):
    request = {
        "kind": "entity",
        "name": "Scholar",
        "graph": {"space": "dev2"},
        "sourceTable": "dwd.dwd_scholar",
        "stepId": "source:bind-1#main",
        "batchIdx": 0,
        "chunkIdx": 0,
        "records": records,
        "decisionPolicy": decision_policy(),
    }
    request.update(overrides)
    return request


class TestPrewriteGuardPriorR2b:
    """R2-b：写前守卫（默认开启）从可信事件身份+耐久应用标记重新确认——
    已应用 create 幂等写入不被重评分阻断；待裁决案/旧 reject 同口径处置。"""

    @pytest.mark.asyncio
    async def test_applied_create_survives_resolve_then_write_records_with_default_guard(
        self, review_service, monkeypatch
    ):
        # 写前守卫保持开启（只关与本案无关的 Redis 锁与近邻路），不靠关守卫通过
        monkeypatch.setenv("ENTITY_DISAMBIGUATION_MILVUS_RECALL", "0")
        monkeypatch.setenv("ENTITY_DISAMBIGUATION_NAME_LOCK", "0")
        monkeypatch.setenv("ENTITY_WRITE_VID_LOCK_ENABLED", "0")

        from service.manual_review_production import sha
        from service.temporal_workflows import (
            _gray_ingress_material,
            resolve_entity_batch,
            write_records,
        )

        record = {
            "id": "sch_new",
            "sourceRecordId": "row-1",
            "props": {"name": "张三", "org": "A"},
        }
        material, _, _ = _gray_ingress_material(
            step_id="source:bind-1#main", record=record, graph_space="dev2", name_tag="Scholar"
        )
        case_id = review_service.create_direct_case(
            task_id="T",
            execution_id="E",
            step_id="source:bind-1#main",
            kind="entity",
            candidate={
                "name": "张三",
                "newIds": ["sch_new"],
                "existingCandidates": [{"vid": "sch_9", "name": "张三", "score": 0.7}],
                "_incoming": {
                    "vid": "sch_new",
                    "props": {"name": "张三", "org": "A"},
                    "sourceTable": "dwd.dwd_scholar",
                },
                "_pendingRelations": [],
                "_graphSpace": "dev2",
                "_nodeLabel": "Scholar",
                "_resolution": {
                    "policyVersion": "gray-gate-v2",
                    "scoreDecision": "gray",
                    "effectiveDisposition": "withhold_pending_review",
                },
            },
            object_id="sch_new",
            object_name="张三",
            node_label="Scholar",
            reason="r2b",
            confidence=0.7,
            template_id="T_LINK",
            graph_space="dev2",
        )["reviewId"]
        with review_service.sf() as s:
            s.get(ReviewCase, case_id).dedupe_key = sha(material)
            s.commit()
        _resolve_create(review_service, case_id)  # 人工 create + APPLIED

        # 守卫召回命中同名且属性一致的既有候选（重评分 1.0=merge）：已确认
        # create 豁免重评分、幂等写入，不得再抛 DEFERRED_MERGE_BLOCKED
        graph = use_graph(
            monkeypatch,
            FakeGraph(
                recall={"Scholar": [{"vid": "sch_9", "props": {"name": "张三", "org": "A"}}]}
            ),
        )
        resolved = await resolve_entity_batch(_resolve_request([dict(record)]))
        assert resolved["keptAsNew"] == 1
        out = await write_records(_write_entity_request(resolved["records"]))
        assert out["written"] == 1
        assert out["guardWithheld"] == 0
        assert out.get("guardPriorDropped", 0) == 0
        assert graph.writes and '"sch_new"' in graph.writes[0]

    @pytest.mark.asyncio
    async def test_open_case_opened_between_resolve_and_write_withholds_at_guard(
        self, review_service, monkeypatch
    ):
        # 并行批次交错：resolve 时无案判 new → 写前另一 worker 同事件建案 →
        # 守卫前置裁决并入既有案（guardWithheld），不重复写图
        monkeypatch.setenv("ENTITY_DISAMBIGUATION_MILVUS_RECALL", "0")
        monkeypatch.setenv("ENTITY_DISAMBIGUATION_NAME_LOCK", "0")
        monkeypatch.setenv("ENTITY_WRITE_VID_LOCK_ENABLED", "0")

        from service.temporal_workflows import (
            _gray_ingress_material,
            resolve_entity_batch,
            write_records,
        )

        record = {
            "id": "sch_new",
            "sourceRecordId": "row-1",
            "props": {"name": "张三", "org": "A", "city": "Y", "email": "F"},
        }
        graph = use_graph(monkeypatch, FakeGraph(recall={"Scholar": []}))  # resolve 时无候选
        resolved = await resolve_entity_batch(_resolve_request([dict(record)]))
        assert resolved["new"] == 1
        material, _, _ = _gray_ingress_material(
            step_id="source:bind-1#main", record=record, graph_space="dev2", name_tag="Scholar"
        )
        review_service.create_direct_case(
            task_id="T",
            execution_id="E",
            step_id="source:bind-1#main",
            kind="entity",
            candidate={
                "name": "张三",
                "newIds": ["sch_new"],
                "existingCandidates": [],
                "_incoming": {
                    "vid": "sch_new",
                    "props": {"name": "张三", "org": "A"},
                    "sourceTable": "dwd.dwd_scholar",
                },
                "_pendingRelations": [],
                "_graphSpace": "dev2",
                "_nodeLabel": "Scholar",
                "_resolution": {
                    "policyVersion": "gray-gate-v2",
                    "scoreDecision": "gray",
                    "effectiveDisposition": "withhold_pending_review",
                },
            },
            object_id="sch_new",
            object_name="张三",
            node_label="Scholar",
            reason="r2b",
            confidence=0.7,
            template_id="T_LINK",
            graph_space="dev2",
            dedupe_material=material,
        )
        out = await write_records(_write_entity_request(resolved["records"]))
        assert out["written"] == 0
        assert out["guardWithheld"] == 1
        assert graph.writes == []

    @pytest.mark.asyncio
    async def test_reject_landed_between_resolve_and_write_drops_at_guard(
        self, review_service, monkeypatch
    ):
        # resolve 判 new 后、写前同事件案已 reject → 守卫按 priorVerdict 剔除
        monkeypatch.setenv("ENTITY_DISAMBIGUATION_MILVUS_RECALL", "0")
        monkeypatch.setenv("ENTITY_DISAMBIGUATION_NAME_LOCK", "0")
        monkeypatch.setenv("ENTITY_WRITE_VID_LOCK_ENABLED", "0")

        from service.temporal_workflows import (
            _gray_ingress_material,
            resolve_entity_batch,
            write_records,
        )

        record = {
            "id": "sch_new",
            "sourceRecordId": "row-1",
            "props": {"name": "张三", "org": "A", "city": "Y", "email": "F"},
        }
        graph = use_graph(monkeypatch, FakeGraph(recall={"Scholar": []}))
        resolved = await resolve_entity_batch(_resolve_request([dict(record)]))
        assert resolved["new"] == 1
        material, _, _ = _gray_ingress_material(
            step_id="source:bind-1#main", record=record, graph_space="dev2", name_tag="Scholar"
        )
        case_id = review_service.create_direct_case(
            task_id="T",
            execution_id="E",
            step_id="source:bind-1#main",
            kind="entity",
            candidate={
                "name": "张三",
                "newIds": ["sch_new"],
                "existingCandidates": [],
                "_incoming": {
                    "vid": "sch_new",
                    "props": {"name": "张三", "org": "A"},
                    "sourceTable": "dwd.dwd_scholar",
                },
                "_pendingRelations": [],
                "_graphSpace": "dev2",
                "_nodeLabel": "Scholar",
                "_resolution": {
                    "policyVersion": "gray-gate-v2",
                    "scoreDecision": "gray",
                    "effectiveDisposition": "withhold_pending_review",
                },
            },
            object_id="sch_new",
            object_name="张三",
            node_label="Scholar",
            reason="r2b",
            confidence=0.7,
            template_id="T_LINK",
            graph_space="dev2",
            dedupe_material=material,
        )["reviewId"]
        review_service.submit(
            case_id, 1, "reject-candidate", {"entityVerdict": "reject"}, "r2b 回归", _review_actor()
        )
        out = await write_records(_write_entity_request(resolved["records"]))
        assert out["written"] == 0
        assert out["guardPriorDropped"] == 1
        assert graph.writes == []


# ---------------------------------------------------------------------------
# 二次复审回归（R4-b）：声明事件版本全链透传（pending / 主流 / S3 两形状）
# ---------------------------------------------------------------------------


class TestPendingDeclaredEventVersionR4b:
    """R4-b：pending 重建 record 透传 sourceEventVersion——声明版本变化=新事件，
    纯摄取时间变化=同事件；跨 chunk 与 S3/内联一致。"""

    def _gray_graph(self, monkeypatch):
        return use_graph(
            monkeypatch,
            FakeGraph(
                recall={
                    "Person": [
                        {
                            "vid": "p9",
                            "props": {"name": "王五", "org": "A", "city": "X", "email": "E"},
                        }
                    ]
                }
            ),
        )

    @pytest.mark.asyncio
    async def test_declared_version_change_opens_new_case_after_reject(
        self, review_service, pipeline_env, monkeypatch
    ):
        from service.temporal_workflows import resolve_pending_entities

        schema_catalog(monkeypatch, "Person")
        self._gray_graph(monkeypatch)
        item = _pending_item("王五", props={"name": "王五", "org": "A", "city": "Y", "email": "F"})
        item["sourceEventVersion"] = "business-version-1"
        first = await resolve_pending_entities(_pending_request([dict(item)]))
        assert first["grayCases"] == 1
        case_id, _ = _cases(review_service)[0]
        review_service.submit(
            case_id, 1, "reject-candidate", {"entityVerdict": "reject"}, "r4b 回归", _review_actor()
        )
        # 同源行业务版本 v1→v2：新事件——旧 reject 不得吞掉重新判定
        item["sourceEventVersion"] = "business-version-2"
        second = await resolve_pending_entities(_pending_request([dict(item)]))
        assert second["grayCases"] == 1
        assert len(_cases(review_service)) == 2

    @pytest.mark.asyncio
    async def test_ingest_time_change_with_same_declared_version_keeps_same_case(
        self, review_service, pipeline_env, monkeypatch
    ):
        from service.temporal_workflows import resolve_pending_entities

        schema_catalog(monkeypatch, "Person")
        self._gray_graph(monkeypatch)
        base = {"name": "王五", "org": "A", "city": "Y", "email": "F"}
        item = _pending_item("王五", props=dict(base, ingest_time="2026-10-21 09:00:00"))
        item["sourceEventVersion"] = "business-version-1"
        first = await resolve_pending_entities(_pending_request([dict(item)]))
        assert first["grayCases"] == 1
        # 声明版本不变、仅摄取时间变化：同事件 → 并入既有案，不建新案
        item2 = _pending_item("王五", props=dict(base, ingest_time="2026-10-21 11:30:00"))
        item2["sourceEventVersion"] = "business-version-1"
        second = await resolve_pending_entities(_pending_request([dict(item2)]))
        assert second["grayCases"] == 1
        assert len(_cases(review_service)) == 1

    @pytest.mark.asyncio
    async def test_cross_chunk_and_s3_shape_hit_same_case(
        self, review_service, pipeline_env, monkeypatch, fake_s3
    ):
        from service.temporal_workflows import resolve_pending_entities

        schema_catalog(monkeypatch, "Person")
        self._gray_graph(monkeypatch)
        item = _pending_item("王五", props={"name": "王五", "org": "A", "city": "Y", "email": "F"})
        item["sourceEventVersion"] = "business-version-1"
        # chunk 0 建案
        await resolve_pending_entities(_pending_request([dict(item)], chunkIdx=0))
        assert len(_cases(review_service)) == 1
        # 跨 chunk（chunkIdx=3）重放：同事件 → 命中同案
        await resolve_pending_entities(_pending_request([dict(item)], chunkIdx=3))
        assert len(_cases(review_service)) == 1
        # S3 形状（pendingKey）与内联一致：同键命中同案
        key = store.put_extract_payload_json("source:bind-1#main", 0, "pending-r4b", [dict(item)])
        request = _pending_request([], pendingKey=key)
        request.pop("pending")
        await resolve_pending_entities(request)
        assert len(_cases(review_service)) == 1


class TestMainStreamDeclaredEventVersionR4b:
    """R4-b：主流（resolve_entity_batch）声明版本透传，与 pending 双流同键。"""

    @pytest.mark.asyncio
    async def test_declared_version_change_new_case_and_s3_shape_same_identity(
        self, review_service, pipeline_env, monkeypatch, fake_s3
    ):
        from service.temporal_workflows import resolve_entity_batch

        use_graph(
            monkeypatch,
            FakeGraph(
                recall={
                    "Scholar": [
                        {
                            "vid": "sch_9",
                            "props": {"name": "张三", "org": "A", "city": "X", "email": "E"},
                        }
                    ]
                }
            ),
        )
        base = {"name": "张三", "org": "A", "city": "Y", "email": "F"}
        record = {
            "id": "sch_new",
            "sourceRecordId": "row-1",
            "sourceEventVersion": "business-version-1",
            "props": dict(base, ingest_time="2026-10-21 09:00:00"),
        }
        first = await resolve_entity_batch(_resolve_request([dict(record)]))
        assert first["withheld"] == 1
        # 摄取时间变化（声明版本不变）：同事件 → 并入既有案
        replay = dict(record, props=dict(base, ingest_time="2026-10-21 11:30:00"))
        second = await resolve_entity_batch(_resolve_request([dict(replay)]))
        assert second["withheld"] == 1
        assert len(_cases(review_service)) == 1
        # 声明版本变化：新事件 → 新案
        bumped = dict(record, sourceEventVersion="business-version-2")
        third = await resolve_entity_batch(_resolve_request([dict(bumped)]))
        assert third["withheld"] == 1
        assert len(_cases(review_service)) == 2
        # S3 形状（recordsKey）与内联一致：同键命中同案
        key = store.put_extract_payload_json("source:bind-1#main", 0, "records-r4b", [dict(replay)])
        request = _resolve_request([], recordsKey=key)
        request.pop("records")
        fourth = await resolve_entity_batch(request)
        assert fourth["withheld"] == 1
        assert len(_cases(review_service)) == 2
