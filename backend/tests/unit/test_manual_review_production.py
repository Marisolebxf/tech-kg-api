"""人工审核核心生命周期单测：建案幂等 / 领取乐观锁 / 裁决记录 / 四方签核 / 直判写图。

建案入口是 ``create_direct_case``（kg.custom.steps / 同名冲突 / 抽取失败共用）；
graph-build 移交通道（内部入口 / correction / outbox）已删除，submit 只记录决议。
"""

from __future__ import annotations

import itertools
import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db_model.base import Base
from db_model.manual_review import ReviewCase
from service.manual_review_domain import (
    ReviewConflictError,
    ReviewIdentity,
    ReviewValidationError,
)
from service.manual_review_production import ManualReviewService


def actor(uid="reviewer-1", roles=("reviewer",)):
    return ReviewIdentity(uid, uid, frozenset(roles), frozenset({"talent"}), "org", "req-1")


def _make_service():
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return ManualReviewService(sessionmaker(engine, expire_on_commit=False))


@pytest.fixture
def service():
    return _make_service()


def link_case_kwargs(**overrides):
    """同名冲突 T_LINK 建案参数（confidence 决定 P0/P1）。"""
    value = dict(
        task_id="TASK-1",
        execution_id="EXEC-1",
        step_id="align",
        kind="entity",
        candidate={"scholar_id": "S-1", "name_zh": "张三", "existingCandidates": [{"id": "E-1"}]},
        object_id="S-1",
        reason="同名冲突待人工裁决",
        confidence=0.9,
        domain="talent",
        template_id="T_LINK",
    )
    value.update(overrides)
    return value


def claimed(service, **overrides):
    case = service.create_direct_case(**link_case_kwargs(**overrides))
    return service.claim(
        case["reviewId"], 1, actor()
    )  # 新建 case version=1（建案响应不含 version）


def test_create_is_idempotent(service):
    first = service.create_direct_case(**link_case_kwargs())
    second = service.create_direct_case(**link_case_kwargs())
    assert first["reviewId"] == second["reviewId"]
    assert second["duplicate"] is True


def test_atomic_claim_and_optimistic_lock(service):
    case = service.create_direct_case(**link_case_kwargs())
    service.claim(case["reviewId"], 1, actor())
    with pytest.raises(ReviewConflictError):
        service.claim(case["reviewId"], 1, actor("reviewer-2"))


def test_template_action_is_server_validated(service):
    case = claimed(service)
    with pytest.raises(ReviewValidationError):
        service.submit(case["id"], case["version"], "force-pass", {}, "", actor())


def test_submit_directly_from_open_without_claim(service):
    # 直审模式：建案即 OPEN，无需领取直接提交即执行
    created = service.create_direct_case(**link_case_kwargs())
    detail = service.get_case(created["reviewId"], actor())
    out = service.submit(
        detail["id"],
        detail["version"],
        "entity-confirm",
        {"entityVerdict": "create"},
        "打开即裁，无需领取",
        actor(),
    )
    assert out["status"] == "RESOLVED"
    # OPEN 直审时 assignee 记为提交人（历史可追溯，队列不再显示待领取）
    assert out["assigneeId"] == actor().user_id


def test_ordinary_decision_records_verdict_and_resolves(service):
    case = claimed(service)
    case = service.draft(case["id"], case["version"], {"entityVerdict": "create"}, actor())
    case = service.submit(
        case["id"],
        case["version"],
        "entity-confirm",
        {"entityVerdict": "create"},
        "已核验，判定为新建实体",
        actor(),
    )
    # 只记录决议：无外部移交通道，submit 直接落 RESOLVED
    assert case["status"] == "RESOLVED"
    assert case["consequence"]["writeTarget"]


def test_p0_executes_at_submit_without_approval(service):
    # 直审模式：confidence < 0.7 → P0 同样提交即执行，无四方签核
    case = claimed(service, confidence=0.4)
    case = service.submit(
        case["id"],
        case["version"],
        "entity-confirm",
        {"entityVerdict": "merge", "targetEntityId": "E-1"},
        "",
        actor(),
    )
    assert case["status"] == "RESOLVED"


def test_stale_draft_does_not_overwrite(service):
    case = claimed(service)
    service.draft(case["id"], case["version"], {"entityVerdict": "create"}, actor())
    with pytest.raises(ReviewConflictError):
        service.draft(case["id"], case["version"], {"entityVerdict": "merge"}, actor())


# ------------------------------------------------------------------
# T_DIRECT 直判写图（accept 走 nGQL INSERT VERTEX / create_edge）
# ------------------------------------------------------------------


class FakeGraph:
    def __init__(self, fields):
        self.fields = fields
        self.merged: list[tuple[list[str], dict, dict]] = []
        self.edges: list[tuple[str, str, str, dict]] = []
        self.writes: list[str] = []

    def execute_query(self, ngql):
        return {"records": [{"Field": f} for f in self.fields]}

    def execute_write(self, ngql):
        self.writes.append(ngql)
        return {"records": []}

    def merge_node(self, labels, key, props):
        self.merged.append((labels, key, props))

    def create_edge(self, from_id, to_id, edge_type, props):
        self.edges.append((from_id, to_id, edge_type, props))


def _reviewer():
    return ReviewIdentity(
        "r1", "r1", frozenset({"reviewer"}), frozenset({"*"}), "org", "req-direct"
    )


def _direct_case(svc, monkeypatch, **overrides):
    graph = FakeGraph(["scholar_id", "name_zh", "name_en"])
    monkeypatch.setattr("infra.graph_db.get_trs_graph_client", lambda: graph)
    kwargs = dict(
        task_id="TASK-1",
        execution_id="EXEC-1",
        step_id="extract",
        kind="entity",
        candidate={"scholar_id": "S-1", "name_zh": "张三", "name_en": "Zhang San"},
        object_id="S-1",
        node_label="Scholar",
        reason="low confidence",
        confidence=0.4,
    )
    kwargs.update(overrides)
    created = svc.create_direct_case(**kwargs)
    return created["reviewId"], graph


def test_direct_decide_accept_with_modified_candidate_writes_corrected_fields(monkeypatch):
    svc = _make_service()
    case_id, graph = _direct_case(svc, monkeypatch)
    identity = _reviewer()
    result = svc.direct_decide(
        case_id,
        1,
        True,
        "字段修正",
        identity,
        candidate={"scholar_id": "S-1", "name_zh": "李四", "org": "清华"},
    )
    assert result["status"] == "RESOLVED"
    assert graph.writes, "实体直写走 nGQL INSERT VERTEX"
    stmt = graph.writes[0]
    assert stmt.startswith("INSERT VERTEX Scholar(")  # label 以快照为准
    assert '"S-1":' in stmt  # 写图 vid 固定取 object_id
    assert '"李四"' in stmt  # 修正后的字段值
    # org 不在 schema 且无 extra_json，被 _coerce_to_schema 丢弃
    assert "org" not in stmt
    assert '"S-1"' in stmt  # scholar_id


def test_direct_decide_candidate_meta_fields_ignored(monkeypatch):
    svc = _make_service()
    case_id, graph = _direct_case(svc, monkeypatch)
    svc.direct_decide(
        case_id,
        1,
        True,
        "",
        _reviewer(),
        candidate={
            "scholar_id": "S-1",
            "name_zh": "李四",
            "_nodeLabel": "Paper",
            "_fromId": "EVIL",
        },
    )
    assert graph.writes, "实体直写走 nGQL INSERT VERTEX"
    assert graph.writes[0].startswith(
        "INSERT VERTEX Scholar("
    )  # 元字段以快照为准（Scholar），传入 _nodeLabel=Paper 被忽略


def test_direct_decide_empty_or_underscore_only_candidate_rejected(monkeypatch):
    svc = _make_service()
    case_id, _ = _direct_case(svc, monkeypatch)
    with pytest.raises(ReviewValidationError, match="不能为空"):
        svc.direct_decide(case_id, 1, True, "", _reviewer(), candidate={"_nodeLabel": "Paper"})


def test_direct_decide_reject_with_candidate_rejected(monkeypatch):
    svc = _make_service()
    case_id, graph = _direct_case(svc, monkeypatch)
    with pytest.raises(ReviewValidationError, match="驳回"):
        svc.direct_decide(case_id, 1, False, "", _reviewer(), candidate={"name_zh": "李四"})
    assert graph.merged == []


def test_direct_decide_audit_records_modified_fields(monkeypatch):
    svc = _make_service()
    case_id, _ = _direct_case(svc, monkeypatch)
    svc.direct_decide(
        case_id,
        1,
        True,
        "修正",
        _reviewer(),
        candidate={"scholar_id": "S-1", "name_zh": "李四", "title": "教授"},
    )
    entries = svc.logs(case_id, _reviewer())
    accept = [e for e in entries if e["eventType"] == "DIRECT_ACCEPTED"][-1]
    detail = accept["detail"]
    assert detail["candidateModified"] is True
    assert detail["modifiedFields"]["added"] == ["title"]
    assert detail["modifiedFields"]["changed"] == ["name_zh"]
    assert detail["modifiedFields"]["removed"] == ["name_en"]
    assert detail["originalCandidateSha256"]


def test_delete_open_case_removes_cascade(service):
    # 物理删除未处理 case：case 与草稿/审计一并删除，详情查不到
    # （先领取再存草稿：OPEN 未领取的 case 不允许写草稿——直审模式既有门控）
    detail = claimed(service)
    detail = service.draft(detail["id"], detail["version"], {"note": "占位草稿"}, actor())
    admin = actor("admin-1", ("review_admin",))
    out = service.delete_case(detail["id"], admin)
    assert out == {"id": detail["id"], "deleted": True}
    with pytest.raises(KeyError):
        service.get_case(detail["id"], admin)


def test_delete_rejects_terminal_case(service):
    # 已处理的记录保留作历史，不给删
    case = claimed(service)
    case = service.submit(
        case["id"], case["version"], "entity-confirm", {"entityVerdict": "create"}, "", actor()
    )
    admin = actor("admin-1", ("review_admin",))
    with pytest.raises(ReviewConflictError):
        service.delete_case(case["id"], admin)


def test_delete_requires_review_admin(service):
    # 物理删除仅 review_admin（普通审核员禁止）
    from service.manual_review_domain import ReviewForbiddenError

    created = service.create_direct_case(**link_case_kwargs())
    with pytest.raises(ReviewForbiddenError):
        service.delete_case(created["reviewId"], actor())


def test_queue_rows_expose_execution_and_workflow_id(service):
    # 图谱构建ID：队列行带产生该 case 的执行 id / workflow id
    service.create_direct_case(**link_case_kwargs())
    page = service.list_cases({"category": "A"}, actor("r", ("reviewer",)))
    row = page["items"][0]
    assert row["executionId"] == "EXEC-1"
    assert row["workflowId"] is None or isinstance(row["workflowId"], str)


def test_queue_filters_by_graph_space(service):
    # 队列跟随全局图空间选择：graph_space 只看该空间；不传=跨空间全量（含 NULL 空间存量案）
    service.create_direct_case(**link_case_kwargs(graph_space="dev2"))
    service.create_direct_case(
        **link_case_kwargs(
            task_id="TASK-2",
            execution_id="EXEC-2",
            object_id="S-2",
            candidate={
                "scholar_id": "S-2",
                "name_zh": "李四",
                "existingCandidates": [{"id": "E-1"}],
            },
            reason="同名冲突待人工裁决（第二条）",
            graph_space="gaoxing_test",
        )
    )
    service.create_direct_case(
        **link_case_kwargs(
            task_id="TASK-3",
            execution_id="EXEC-3",
            object_id="S-3",
            candidate={
                "scholar_id": "S-3",
                "name_zh": "王五",
                "existingCandidates": [{"id": "E-1"}],
            },
            reason="同名冲突待人工裁决（第三条）",
        )
    )
    reviewer = actor("r", ("reviewer",))
    only = service.list_cases({"graph_space": "dev2"}, reviewer)
    assert only["total"] == 1
    assert only["items"][0]["graphSpace"] == "dev2"
    # 没有案的空间 → 空队列（页面切到该空间即空列表）
    assert service.list_cases({"graph_space": "dev"}, reviewer)["total"] == 0
    everything = service.list_cases({}, reviewer)
    assert everything["total"] == 3


def test_queue_rows_expose_job_id(service, monkeypatch):
    # 来源记录跳任务详情：快照 jobId（建案写入）优先，存量案靠 EXEC→job 批量解析兜底
    import service.manual_review_production as mrp

    resolved: list[list[str]] = []

    def fake_resolve(ids):
        resolved.append([i for i in ids if i])
        return {"EXEC-9": "job-legacy"}

    monkeypatch.setattr(mrp, "resolve_job_ids", fake_resolve)
    service.create_direct_case(**link_case_kwargs(extra_snapshot={"jobId": "job-snap"}))
    service.create_direct_case(
        **link_case_kwargs(
            execution_id="EXEC-9",
            object_id="S-9",
            candidate={
                "scholar_id": "S-9",
                "name_zh": "李四",
                "existingCandidates": [{"id": "E-1"}],
            },
            reason="同名冲突待人工裁决（第二条）",
        )
    )
    page = service.list_cases({"category": "A"}, actor("r", ("reviewer",)))
    by_exec = {row["executionId"]: row for row in page["items"]}
    assert by_exec["EXEC-1"]["jobId"] == "job-snap"
    assert by_exec["EXEC-9"]["jobId"] == "job-legacy"
    # 一次列表查询只做一次批量解析，入参为本页执行 ID 集合
    assert resolved == [["EXEC-1", "EXEC-9"]]


def test_queue_keyword_matches_source_record_info(service, monkeypatch):
    # 失败重跑搜索栏按「来源记录」信息搜索：来源表 + 快照里的 jobId / 抽取执行
    # executionId（此前只搜案号/对象/记录 id，搜来源记录列展示的 jobId 与 EXEC 一律空）
    import service.manual_review_production as mrp

    # 控制面反解走单测桩：这里只验证快照直搜，兜底路径见下一条用例
    monkeypatch.setattr(mrp, "resolve_execution_ids_by_job_keyword", lambda kw: [])
    _make_extract_fail_case(service, domain="talent")  # EXEC-1 / job-1 / db.widgets#w3
    reviewer = actor("r", ("reviewer",))
    assert service.list_cases({"category": "C", "keyword": "job-1"}, reviewer)["total"] == 1
    assert service.list_cases({"category": "C", "keyword": "EXEC-1"}, reviewer)["total"] == 1
    assert service.list_cases({"category": "C", "keyword": "db.widgets"}, reviewer)["total"] == 1
    assert service.list_cases({"category": "C", "keyword": "job-404"}, reviewer)["total"] == 0


def test_queue_keyword_matches_legacy_job_via_control_db(service, monkeypatch):
    # 存量案快照没写 jobId（来源记录列靠控制面 EXEC→job 解析展示）：
    # 搜该 jobId 时按 job→执行反解回快照匹配，搜展示值能命中
    import service.manual_review_production as mrp

    service.create_direct_case(
        task_id="TASK-E9",
        execution_id="EXEC-9",
        step_id="extract",
        kind="entity",
        candidate={"recordId": "w9", "error": "ValueError: POISON", "schemaKey": "widget"},
        object_id="w9",
        object_name="db.widgets#w9",
        reason="记录解析失败: ValueError: POISON",
        template_id="T_EXTRACT_FAIL",
        workflow_type="kg.schema.extract",
        domain="talent",
        source_table="db.widgets",
        source_record_id="w9",
        extra_snapshot={"schemaId": "s1", "schemaKey": "widget", "attempt": 1},  # 无 jobId
    )
    monkeypatch.setattr(
        mrp,
        "resolve_execution_ids_by_job_keyword",
        lambda kw: ["EXEC-9"] if kw == "job-legacy" else [],
    )
    reviewer = actor("r", ("reviewer",))
    assert service.list_cases({"category": "C", "keyword": "job-legacy"}, reviewer)["total"] == 1


def test_detail_includes_resolved_job_id(service, monkeypatch):
    # 详情页「所属任务」：无快照 jobId 的存量 case 由 detail 单条解析补齐
    import service.manual_review_production as mrp

    monkeypatch.setattr(mrp, "resolve_job_ids", lambda ids: {"EXEC-1": "job-x"})
    created = service.create_direct_case(**link_case_kwargs())
    d = service.get_case(created["reviewId"], actor())
    assert d["jobId"] == "job-x"


def test_resolve_job_ids_swallows_control_plane_failure(monkeypatch):
    # 控制面库不可达：吞异常返回空映射，不拖垮审核队列
    import sys
    import types

    import service.manual_review_production as mrp

    fake_module = types.ModuleType("service.workflow_repository")

    def boom(ids):
        raise RuntimeError("control-plane down")

    fake_module.repository = types.SimpleNamespace(job_ids_by_execution_ids=boom)
    monkeypatch.setitem(sys.modules, "service.workflow_repository", fake_module)
    assert mrp.resolve_job_ids(["EXEC-1"]) == {}
    assert mrp.resolve_job_ids([]) == {}
    assert mrp.resolve_job_ids([None, ""]) == {}


def test_job_ids_by_execution_ids_batch():
    # EXEC→jobId 批量解析（控制面 sqlite 注入；host 无控制面 MySQL 时跳过）
    try:
        from service.workflow_repository import WorkflowRepository as Repo
    except Exception:
        pytest.skip("workflow_repository 单例 import 需控制面 MySQL，仅容器内验证")

    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    repo = Repo(engine=engine)
    base = {
        "definitionId": "schema:paper",
        "workflowId": "wf",
        "runId": None,
        "status": "COMPLETED",
        "startedAt": "2026-09-17 10:00:00",
    }
    repo.save_execution({**base, "id": "E1", "workflowId": "wf-1", "jobId": "job-a"})
    repo.save_execution({**base, "id": "E2", "workflowId": "wf-2", "jobId": "job-b"})
    repo.save_execution({**base, "id": "E3", "workflowId": "wf-3"})  # 无 jobId 的行剔除
    assert repo.job_ids_by_execution_ids(["E1", "E2", "E3", "E4", None, ""]) == {
        "E1": "job-a",
        "E2": "job-b",
    }
    assert repo.job_ids_by_execution_ids([]) == {}


def test_resolve_execution_ids_by_job_keyword_swallows_control_plane_failure(monkeypatch):
    # 控制面库不可达：吞异常返回空列表，搜索退化为快照直搜，不拖垮队列
    import sys
    import types

    import service.manual_review_production as mrp

    fake_module = types.ModuleType("service.workflow_repository")

    def boom(keyword):
        raise RuntimeError("control-plane down")

    fake_module.repository = types.SimpleNamespace(execution_ids_by_job_keyword=boom)
    monkeypatch.setitem(sys.modules, "service.workflow_repository", fake_module)
    assert mrp.resolve_execution_ids_by_job_keyword("job-1") == []


def test_execution_ids_by_job_keyword_matches_partial_job_id(monkeypatch):
    # jobId 关键词（含部分匹配）反查执行 ID：按「来源记录」jobId 搜存量案的兜底通道
    # （host 无控制面 MySQL 时跳过）。save_execution/查询走模块级 workflow_session_scope
    # （全局控制面）——注入 sqlite 会话作用域隔离，否则容器内会读写共享控制库，
    # LIKE 还会命中真实执行（job-f33128bafbec 在 dev2 有真实执行记录）
    try:
        import service.workflow_repository as wr
    except Exception:
        pytest.skip("workflow_repository 单例 import 需控制面 MySQL，仅容器内验证")
    from contextlib import contextmanager

    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    wr.Base.metadata.create_all(engine)
    sf = sessionmaker(engine, expire_on_commit=False)

    @contextmanager
    def sqlite_scope():
        session = sf()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr(wr, "workflow_session_scope", sqlite_scope)
    repo = wr.WorkflowRepository(engine=engine)
    base = {
        "definitionId": "schema:paper",
        "workflowId": "wf",
        "runId": None,
        "status": "COMPLETED",
        "startedAt": "2026-09-17 10:00:00",
    }
    repo.save_execution({**base, "id": "E1", "workflowId": "wf-1", "jobId": "job-f33128bafbec"})
    repo.save_execution({**base, "id": "E2", "workflowId": "wf-2", "jobId": "job-f33128bafbec"})
    repo.save_execution({**base, "id": "E3", "workflowId": "wf-3", "jobId": "job-other"})
    repo.save_execution({**base, "id": "E4", "workflowId": "wf-4"})  # 无 jobId 的行不参与
    # 部分关键词命中同一 job 的全部执行（前端搜索框粘半截 jobId 是常态）
    assert set(repo.execution_ids_by_job_keyword("f33128")) == {"E1", "E2"}
    assert repo.execution_ids_by_job_keyword("job-other") == ["E3"]
    assert repo.execution_ids_by_job_keyword("job-404") == []


# ----------------------------------------------------------------------
# T_EXTRACT_FAIL 重跑仍失败：attempt+1 新 case 必须真的建出来
# （candidate 不带 attempt 时去重键与原案相同，新 case 被静默吞掉）
# ----------------------------------------------------------------------


def _make_extract_fail_case(
    service, *, attempt=1, execution_id="EXEC-1", domain="graph", record_id="w3"
):
    """模拟 record_extract_failures activity 建案（attempt 记在 input_snapshot）。"""
    resp = service.create_direct_case(
        task_id="TASK-E1",
        execution_id=execution_id,
        step_id="extract",
        kind="entity",
        candidate={"recordId": record_id, "error": "ValueError: POISON", "schemaKey": "widget"},
        object_id=record_id,
        object_name=f"db.widgets#{record_id}",
        node_label="E2EWidget",
        reason="记录解析失败: ValueError: POISON",
        template_id="T_EXTRACT_FAIL",
        workflow_type="kg.schema.extract",
        domain=domain,
        source_table="db.widgets",
        source_record_id=record_id,
        extra_snapshot={
            "schemaId": "s1",
            "schemaKey": "widget",
            "sourceBindingId": "b1",
            "jobId": "job-1",
            "attempt": attempt,
        },
    )
    return resp["reviewId"]


def _refail_once(service, case_id, rerun_execution_id):
    """一轮重跑仍失败：标记 RERUNNING → 回写（与 resolve_failure_cases activity 同参）。"""
    service.mark_extract_rerun([case_id])
    return service.resolve_extract_rerun(
        rerun_case_ids=[case_id],
        failed_records=[{"sourceBindingId": "b1", "recordId": "w3", "error": "ValueError: POISON"}],
        rerun_execution_id=rerun_execution_id,
        task_id="TASK-E1",
        kind="entity",
        name="E2EWidget",
    )


def test_extract_rerun_refail_recreates_next_attempt_case(service):
    case1 = _make_extract_fail_case(service)
    result = _refail_once(service, case1, "EXEC-R1")
    assert result == {"resolved": 1, "refailed": 1, "recreated": 1}

    with service.sf() as s:
        row1 = s.scalar(select(ReviewCase).where(ReviewCase.id == case1))
        assert row1.status == "RESOLVED"  # 原案被取代
        reopened = s.scalars(
            select(ReviewCase).where(
                ReviewCase.source_record_id == "w3", ReviewCase.status == "OPEN"
            )
        ).all()
    assert len(reopened) == 1, "仍失败记录必须以新 case 回到待处理队列"
    snap = json.loads(reopened[0].input_snapshot)
    assert snap["attempt"] == 2
    assert snap["executionId"] == "EXEC-R1"
    assert snap["rerunOfExecutionId"] == "EXEC-1"


def test_extract_rerun_refail_chain_each_attempt_distinct(service):
    # 连续两轮重跑都失败 → attempt 2 / 3 各一条 case，不互相去重吞案
    case1 = _make_extract_fail_case(service)
    _refail_once(service, case1, "EXEC-R1")
    with service.sf() as s:
        case2 = s.scalar(
            select(ReviewCase.id).where(
                ReviewCase.source_record_id == "w3", ReviewCase.status == "OPEN"
            )
        )
    result = _refail_once(service, case2, "EXEC-R2")
    assert result["recreated"] == 1

    with service.sf() as s:
        rows = s.scalars(select(ReviewCase).where(ReviewCase.source_record_id == "w3")).all()
    attempts = sorted(json.loads(c.input_snapshot)["attempt"] for c in rows)
    assert attempts == [1, 2, 3]
    open_rows = [c for c in rows if c.status == "OPEN"]
    assert len(open_rows) == 1
    assert json.loads(open_rows[0].input_snapshot)["attempt"] == 3


# ----------------------------------------------------------------------
# T_EXTRACT_FAIL 只读口径（2026-10-10）：「已完成」以执行概要成功为准——
# 重跑执行非成功终态（异常/失败/终止）或记录缺失的案不归类已完成，
# 显示「重跑失败」且可一直重跑；只有 COMPLETED 才维持已完成（只读）。
# ----------------------------------------------------------------------


_RID = itertools.count()


def _bound_extract_fail_case(service, *, status, rerun_execution_id="EXEC-R9"):
    """造一台已绑定重跑执行的 T_EXTRACT_FAIL 案（模拟 mark/attach/resolve 后形态）。

    record_id 逐台唯一：建案按 task/step/record/candidate 去重，同 record 的
    重复建案会命中同一条案（状态互相覆盖），多案断言就失真了。
    """
    case_id = _make_extract_fail_case(service, record_id=f"w{next(_RID)}")
    with service.sf() as s:
        c = s.scalar(select(ReviewCase).where(ReviewCase.id == case_id))
        snapshot = json.loads(c.input_snapshot)
        snapshot["rerunExecutionId"] = rerun_execution_id
        c.input_snapshot = json.dumps(snapshot)
        c.status = status
        s.commit()
    return case_id


def _patch_execution_statuses(monkeypatch, mapping):
    """钉住控制面执行状态映射（None=控制面不可达）。"""
    monkeypatch.setattr(
        "service.manual_review_production.resolve_execution_statuses",
        lambda ids: mapping,
    )


def _admin():
    return ReviewIdentity(
        "admin", "admin", frozenset({"review_admin"}), frozenset({"*"}), "org", "req"
    )


@pytest.mark.parametrize(
    "exec_status,expected",
    [
        ("COMPLETED", "RESOLVED"),
        ("ABNORMAL", "RERUN_FAILED"),
        ("FAILED", "RERUN_FAILED"),
        ("CANCELED", "RERUN_FAILED"),
        ("TIMED_OUT", "RERUN_FAILED"),
        (None, "RERUN_FAILED"),  # 执行记录已缺失（控制库被清理）
    ],
)
def test_effective_status_resolved_needs_execution_success(exec_status, expected):
    from service.manual_review_production import effective_extract_fail_status

    assert (
        effective_extract_fail_status("RESOLVED", "EXEC-R1", {"EXEC-R1": exec_status}) == expected
    )


@pytest.mark.parametrize(
    "exec_status,expected",
    [
        ("RUNNING", "RERUNNING"),
        ("FAILED", "RERUN_FAILED"),
        (None, "RERUN_FAILED"),  # 滞留重跑中（回滚失败/执行记录缺失）→ 解锁可再重跑
    ],
)
def test_effective_status_rerunning(exec_status, expected):
    from service.manual_review_production import effective_extract_fail_status

    assert (
        effective_extract_fail_status("RERUNNING", "EXEC-R1", {"EXEC-R1": exec_status}) == expected
    )


def test_effective_status_keeps_stored_when_unverifiable():
    from service.manual_review_production import effective_extract_fail_status

    # 控制面不可达（映射为 None）→ 保留库内状态，不误判
    assert effective_extract_fail_status("RESOLVED", "EXEC-R1", None) == "RESOLVED"
    assert effective_extract_fail_status("RERUNNING", "EXEC-R1", None) == "RERUNNING"
    # 未绑定重跑执行（无可核验凭证）→ 不改判
    assert effective_extract_fail_status("RESOLVED", None, {}) == "RESOLVED"


def test_queue_status_derived_from_execution_summary(service, monkeypatch):
    done = _bound_extract_fail_case(service, status="RESOLVED", rerun_execution_id="EXEC-OK")
    abnormal = _bound_extract_fail_case(service, status="RESOLVED", rerun_execution_id="EXEC-BAD")
    gone = _bound_extract_fail_case(service, status="RESOLVED", rerun_execution_id="EXEC-GONE")
    stuck = _bound_extract_fail_case(service, status="RERUNNING", rerun_execution_id="EXEC-STUCK")
    running = _bound_extract_fail_case(service, status="RERUNNING", rerun_execution_id="EXEC-RUN")
    _patch_execution_statuses(
        monkeypatch,
        {
            "EXEC-OK": "COMPLETED",
            "EXEC-BAD": "ABNORMAL",
            "EXEC-STUCK": "FAILED",
            "EXEC-RUN": "RUNNING",
        },
    )  # EXEC-GONE 故意不在映射里 = 执行记录缺失
    out = service.list_cases({"template_id": "T_EXTRACT_FAIL"}, _admin())
    statuses = {x["id"]: x["status"] for x in out["items"]}
    assert statuses[done] == "RESOLVED"
    assert statuses[abnormal] == "RERUN_FAILED"
    assert statuses[gone] == "RERUN_FAILED"
    assert statuses[stuck] == "RERUN_FAILED"
    assert statuses[running] == "RERUNNING"


def test_non_extract_templates_unaffected_by_execution_map(service, monkeypatch):
    case = claimed(service)
    case = service.submit(
        case["id"], case["version"], "entity-confirm", {"entityVerdict": "create"}, "", actor()
    )
    _patch_execution_statuses(monkeypatch, {"EXEC-1": "FAILED"})
    out = service.list_cases({"template_id": "T_LINK"}, _admin())
    assert [x["status"] for x in out["items"]] == ["RESOLVED"]


def test_rerun_gates_accept_derived_rerunnable(service, monkeypatch):
    reopened = _bound_extract_fail_case(service, status="RESOLVED", rerun_execution_id="EXEC-BAD")
    done = _bound_extract_fail_case(service, status="RESOLVED", rerun_execution_id="EXEC-OK")
    _patch_execution_statuses(monkeypatch, {"EXEC-OK": "COMPLETED", "EXEC-BAD": "ABNORMAL"})
    listed = {c["caseId"] for c in service.list_extract_fail_cases(case_ids=[reopened, done])}
    assert listed == {reopened}, "概要非成功的已完成案必须可重跑，概要成功的不可"
    assert service.mark_extract_rerun([reopened, done]) == 1
    with service.sf() as s:
        statuses = {
            c.id: c.status
            for c in s.scalars(select(ReviewCase).where(ReviewCase.id.in_([reopened, done])))
        }
    assert statuses[reopened] == "RERUNNING"
    assert statuses[done] == "RESOLVED"


def test_rerunning_with_live_execution_not_rerunnable(service, monkeypatch):
    running = _bound_extract_fail_case(service, status="RERUNNING", rerun_execution_id="EXEC-RUN")
    _patch_execution_statuses(monkeypatch, {"EXEC-RUN": "RUNNING"})
    assert service.list_extract_fail_cases(case_ids=[running]) == []
    assert service.mark_extract_rerun([running]) == 0


def test_delete_allows_derived_rerunnable_only(service, monkeypatch):
    admin = actor("admin-1", ("review_admin",))
    reopened = _bound_extract_fail_case(service, status="RESOLVED", rerun_execution_id="EXEC-BAD")
    done = _bound_extract_fail_case(service, status="RESOLVED", rerun_execution_id="EXEC-OK")
    _patch_execution_statuses(monkeypatch, {"EXEC-OK": "COMPLETED", "EXEC-BAD": "FAILED"})
    assert service.delete_case(reopened, admin) == {"id": reopened, "deleted": True}
    with pytest.raises(ReviewConflictError):
        service.delete_case(done, admin)


def test_reopened_case_round_trips_through_rerun(service, monkeypatch):
    # 重开的案走完正常闭环：仍失败（执行 ABNORMAL）→ 维持重跑失败并重建 attempt+1；
    # 再次重跑成功（执行 COMPLETED）→ 已完成站得住
    case_id = _bound_extract_fail_case(service, status="RESOLVED", rerun_execution_id="EXEC-BAD")
    with service.sf() as s:
        record_id = s.scalar(select(ReviewCase).where(ReviewCase.id == case_id)).source_record_id
    _patch_execution_statuses(monkeypatch, {"EXEC-BAD": "ABNORMAL"})
    assert service.mark_extract_rerun([case_id]) == 1
    service.attach_rerun_execution([case_id], "EXEC-NEW")
    result = service.resolve_extract_rerun(
        rerun_case_ids=[case_id],
        failed_records=[{"sourceBindingId": "b1", "recordId": record_id, "error": "仍失败"}],
        rerun_execution_id="EXEC-NEW",
        task_id="TASK-E1",
    )
    assert result["refailed"] == 1 and result["recreated"] == 1
    _patch_execution_statuses(monkeypatch, {"EXEC-NEW": "ABNORMAL"})
    items = {
        x["id"]: x["status"]
        for x in service.list_cases({"template_id": "T_EXTRACT_FAIL"}, _admin())["items"]
    }
    assert items[case_id] == "RERUN_FAILED"
    # 再来一轮：这次成功
    assert service.mark_extract_rerun([case_id]) == 1
    service.attach_rerun_execution([case_id], "EXEC-OK2")
    result = service.resolve_extract_rerun(
        rerun_case_ids=[case_id],
        failed_records=[],
        rerun_execution_id="EXEC-OK2",
        task_id="TASK-E1",
    )
    assert result["resolved"] == 1
    _patch_execution_statuses(monkeypatch, {"EXEC-OK2": "COMPLETED"})
    items = {
        x["id"]: x["status"]
        for x in service.list_cases({"template_id": "T_EXTRACT_FAIL"}, _admin())["items"]
    }
    assert items[case_id] == "RESOLVED"
