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


def test_submit_decision_returned_in_detail_for_redisplay(service):
    # 刷新回显：详情带最终决议（裁决单选不再回落默认「合并」——2026-10-15 修复）
    created = service.create_direct_case(**link_case_kwargs())
    detail = service.get_case(created["reviewId"], actor())
    assert detail["decision"] is None  # 未裁决的 case 无决议
    out = service.submit(
        detail["id"],
        detail["version"],
        "entity-confirm",
        {"entityVerdict": "create"},
        "判为新实体",
        actor(),
    )
    assert out["status"] == "RESOLVED"
    assert out["decision"]["result"]["entityVerdict"] == "create"

    again = service.get_case(detail["id"], actor())
    assert again["decision"]["actionId"] == "entity-confirm"
    assert again["decision"]["note"] == "判为新实体"
    assert again["decision"]["decidedAt"]


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


def test_direct_decide_decision_returned_in_detail(monkeypatch):
    # 直判通道同样落决议行：T_DIRECT case 刷新后裁决单选可回显
    svc = _make_service()
    case_id, _ = _direct_case(svc, monkeypatch)
    out = svc.direct_decide(case_id, 1, False, "不收录", _reviewer())
    assert out["status"] == "REJECTED"
    assert out["decision"]["actionId"] == "reject"

    detail = svc.get_case(case_id, _reviewer())
    assert detail["decision"]["result"] == {"accepted": False}
    assert detail["decision"]["note"] == "不收录"


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


def test_queue_keyword_by_execution_excludes_rerun_generation(service, monkeypatch):
    # 重跑仍失败：同一记录两代案并存（旧代 RESOLVED + attempt2 新案，后者快照带
    # rerunOfExecutionId=原执行）。按执行搜只命中该执行建的那一代——值模糊匹配
    # 会从 executionId 键出发跨过中间 JSON 落到 rerunOfExecutionId 的值上，
    # 搜任一代执行 ID 都翻倍出两代案（1077 失败记录搜出 2154 的实例）
    import service.manual_review_production as mrp

    monkeypatch.setattr(mrp, "resolve_execution_ids_by_job_keyword", lambda kw: [])
    case1 = _make_extract_fail_case(service, domain="talent")  # EXEC-1 / job-1 / w3
    _refail_once(service, case1, "EXEC-R1")  # 旧案 RESOLVED + attempt2 新案（EXEC-R1）
    reviewer = actor("r", ("reviewer",))
    assert service.list_cases({"category": "C", "keyword": "EXEC-1"}, reviewer)["total"] == 1
    assert service.list_cases({"category": "C", "keyword": "EXEC-R1"}, reviewer)["total"] == 1
    # jobId 两代相同，任务级搜索仍两代都命中（语义不变）
    assert service.list_cases({"category": "C", "keyword": "job-1"}, reviewer)["total"] == 2


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
        # MR-SYNC：案已 RESOLVED 但执行行仍 RUNNING（收尾在途/待同步）→ 如实
        # 展示「重跑中」，不误报 RERUN_FAILED（写侧门控同口径 RUNNING 禁发）
        ("RUNNING", "RERUNNING"),
        ("ABNORMAL", "RERUN_FAILED"),
        ("FAILED", "RERUN_FAILED"),
        ("CANCELED", "RERUN_FAILED"),
        ("TERMINATED", "RERUN_FAILED"),
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
    # MR-SYNC 现场形态：案已被 workflow 结尾的 resolve activity 置 RESOLVED，但
    # 执行行仍滞留 RUNNING（收尾在途）——此前被误报成 RERUN_FAILED
    settle = _bound_extract_fail_case(service, status="RESOLVED", rerun_execution_id="EXEC-SETTLE")
    _patch_execution_statuses(
        monkeypatch,
        {
            "EXEC-OK": "COMPLETED",
            "EXEC-BAD": "ABNORMAL",
            "EXEC-STUCK": "FAILED",
            "EXEC-RUN": "RUNNING",
            "EXEC-SETTLE": "RUNNING",
        },
    )  # EXEC-GONE 故意不在映射里 = 执行记录缺失
    out = service.list_cases({"template_id": "T_EXTRACT_FAIL"}, _admin())
    statuses = {x["id"]: x["status"] for x in out["items"]}
    assert statuses[done] == "RESOLVED"
    assert statuses[abnormal] == "RERUN_FAILED"
    assert statuses[gone] == "RERUN_FAILED"
    assert statuses[stuck] == "RERUN_FAILED"
    assert statuses[running] == "RERUNNING"
    assert statuses[settle] == "RERUNNING"


def test_non_extract_templates_unaffected_by_execution_map(service, monkeypatch):
    case = claimed(service)
    case = service.submit(
        case["id"], case["version"], "entity-confirm", {"entityVerdict": "create"}, "", actor()
    )
    _patch_execution_statuses(monkeypatch, {"EXEC-1": "FAILED"})
    out = service.list_cases({"template_id": "T_LINK"}, _admin())
    assert [x["status"] for x in out["items"]] == ["RESOLVED"]


# ----------------------------------------------------------------------
# 状态精确过滤与表格徽标 1:1（队列页「状态」下拉对齐）：RERUN_FAILED 不落库，
# 按执行概要圈定；RESOLVED/RERUNNING 反向剔除推导为重跑失败的案——
# 选什么状态，表格就只出什么徽标。
# ----------------------------------------------------------------------


def test_queue_filter_status_matches_derived_badge(service, monkeypatch):
    open_case = _make_extract_fail_case(service, record_id=f"w{next(_RID)}")
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

    def ids(out):
        return {x["id"] for x in out["items"]}

    # 重跑失败 = 三台推导案（异常/执行缺失/滞留重跑中），不含库内 OPEN
    rerun_failed = service.list_cases(
        {"template_id": "T_EXTRACT_FAIL", "status": "RERUN_FAILED"}, _admin()
    )
    assert ids(rerun_failed) == {abnormal, gone, stuck}
    assert rerun_failed["total"] == 3
    # 已完成 = 仅执行概要成功的 RESOLVED 案（abnormal/gone 被剔除，不冒进已完成）
    resolved = service.list_cases({"template_id": "T_EXTRACT_FAIL", "status": "RESOLVED"}, _admin())
    assert ids(resolved) == {done}
    # 重跑中 = 仅执行仍在跑的 RERUNNING 案（stuck 滞留案被剔出）
    rerunning = service.list_cases(
        {"template_id": "T_EXTRACT_FAIL", "status": "RERUNNING"}, _admin()
    )
    assert ids(rerunning) == {running}
    # 通用精确值（OPEN 等库内状态）不受推导影响
    assert ids(
        service.list_cases({"template_id": "T_EXTRACT_FAIL", "status": "OPEN"}, _admin())
    ) == {open_case}
    # 不筛状态仍是全量 6 台
    assert service.list_cases({"template_id": "T_EXTRACT_FAIL"}, _admin())["total"] == 6


def test_queue_filter_skips_derivation_when_control_plane_unreachable(service, monkeypatch):
    done = _bound_extract_fail_case(service, status="RESOLVED", rerun_execution_id="EXEC-OK")
    abnormal = _bound_extract_fail_case(service, status="RESOLVED", rerun_execution_id="EXEC-BAD")
    stuck = _bound_extract_fail_case(service, status="RERUNNING", rerun_execution_id="EXEC-STUCK")
    _patch_execution_statuses(monkeypatch, None)  # 控制面不可达

    def ids(out):
        return {x["id"] for x in out["items"]}

    # 与列表展示同款保守口径：不可核验就不推导——重跑失败筛不出（无库内值），
    # 已完成/重跑中按库内状态原样返回，不误剔除
    assert (
        service.list_cases({"template_id": "T_EXTRACT_FAIL", "status": "RERUN_FAILED"}, _admin())[
            "total"
        ]
        == 0
    )
    assert ids(
        service.list_cases({"template_id": "T_EXTRACT_FAIL", "status": "RESOLVED"}, _admin())
    ) == {done, abnormal}
    assert ids(
        service.list_cases({"template_id": "T_EXTRACT_FAIL", "status": "RERUNNING"}, _admin())
    ) == {stuck}


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


def test_fix_mojibake_repairs_latin1_and_cp1252_double_encoding():
    """图库历史乱码（UTF-8 被按 latin-1/cp1252 解码落库）读出即修，正常值零误伤。"""
    fix = ManualReviewService._fix_mojibake
    # latin-1 通道：否（e5 90 a6 全在 latin-1 范围）
    assert fix("否".encode().decode("latin-1")) == "否"
    # cp1252 通道：刘晓 的字节含 0x98/0x99/0x9a（latin-1 外，cp1252 为 ˜/™/š）
    assert fix("刘晓".encode().decode("cp1252")) == "刘晓"
    # Java 通道空洞：华 的字节含 0x8D（cp1252 未定义，当年按 latin-1 控制符落库）
    assert fix("华".encode().decode("latin-1")) == "华"
    assert (
        fix("清华大学计算机科学与技术系".encode().decode("latin-1")) == "清华大学计算机科学与技术系"
    )
    # 正常中文两种编码都还原不回含 CJK 的串（latin-1/cp1252 编码直接抛错）→ 原样
    assert fix("刘霄") == "刘霄"
    # 纯 ASCII / 空值 / 非串原样返回
    assert fix("Xiao Liu") == "Xiao Liu"
    assert fix("") == ""
    assert fix(None) is None
    assert fix(123) == 123


# ---- MR-CAND B：T_LINK 受控刷新未决候选 ----


def _refreshable_link_case(service):
    """带 _incoming/_nodeLabel 的 T_LINK 灰区案（刷新候选的最小快照形态）。"""
    created = service.create_direct_case(
        task_id="TASK-R",
        execution_id="EXEC-R",
        step_id="align",
        kind="entity",
        candidate={
            "name": "张三",
            "newIds": ["S-1"],
            "existingCandidates": [{"vid": "old-1", "name": "张三", "score": 0.7}],
            "_incoming": {"vid": "S-1", "props": {"name": "张三", "org": "中国科学院"}},
            "_pendingRelations": [],
            "_graphSpace": "dev2",
            "_nodeLabel": "Expert",
        },
        object_id="S-1",
        object_name="张三",
        node_label="Expert",
        reason="消歧灰区待人工裁决",
        confidence=0.7,
        domain="talent",
        template_id="T_LINK",
        graph_space="dev2",
    )
    return service.get_case(created["reviewId"], actor())


class _AliveGraphClient:
    """判活探查桩：所有 vid 图内存活（get_node 非 None）。"""

    def get_node(self, vid):
        return object()


class _DeadGraphClient:
    """判活探查桩：所有 vid 图内已不存在（get_node None）。"""

    def get_node(self, vid):
        return None


class _BrokenProbeClient:
    """判活探查桩：get_node 全部抛错（探查失败≠失效，保守按存活保留）。"""

    def get_node(self, vid):
        raise RuntimeError("判活探查通道不可用")


def _patch_recall(monkeypatch, recalled, calls=None, score=0.9, client=None, grouped=None):
    """假召回+打分（零图写：recall/score 均为纯函数；图客户端只被读探查）。

    ``grouped`` 直接给定召回分组 dict（跨键桶场景）；``client`` 是判活探查
    （旧候选召回不可见时的 get_node）用的图客户端桩。
    """
    import service.entity_disambiguation as ed

    def fake_recall(client, tag, names, space=None):
        if calls is not None:
            calls.append({"tag": tag, "names": list(names), "space": space})
        if grouped is not None:
            return grouped
        return {names[0]: list(recalled)} if recalled else {}

    monkeypatch.setattr(ed, "recall_candidates", fake_recall)
    monkeypatch.setattr(
        ed, "score_candidate", lambda display, iprops, cname, cprops: (score, {"nameSim": score})
    )
    # 详情富化按最小桩处理（富化只读有独立覆盖）；图客户端只在判活探查
    # （旧候选召回不可见时的 get_node）被触达——refresh 路径零图写不变
    monkeypatch.setattr(ManualReviewService, "_enrich_link_snapshot", lambda self, c, snap: snap)
    monkeypatch.setattr(
        ManualReviewService, "_graph_client_for", lambda self, snap: client if client else object()
    )


def _audit_events(service, case_id):
    from db_model.manual_review import ReviewAuditLog

    with service.sf() as s:
        rows = s.query(ReviewAuditLog).filter(ReviewAuditLog.case_id == case_id).all()
        return [r.event_type for r in rows]


def test_refresh_appends_new_candidate_and_bumps_version(service, monkeypatch):
    detail = _refreshable_link_case(service)
    _patch_recall(
        monkeypatch,
        [
            {"vid": "old-1", "name": "张三", "props": {}},
            {"vid": "fresh-2", "name": "张三丰", "props": {}},
        ],
    )
    out = service.refresh_candidates(detail["id"], detail["version"], actor())
    vids = [c["vid"] for c in out["candidate"]["existingCandidates"]]
    # 旧候选保留在原位，新候选按得分追加
    assert vids == ["old-1", "fresh-2"]
    assert out["version"] == detail["version"] + 1
    refresh = out["candidate"]["_candidateRefresh"]
    assert refresh["addedVids"] == ["fresh-2"]
    assert refresh["removedVids"] == []
    assert "CANDIDATES_REFRESHED" in _audit_events(service, detail["id"])


def test_refresh_dropping_stale_candidate_is_a_change(service, monkeypatch):
    """真失效剔除也算变更：version+1+审计，不能因「没有新增」当 no-op。

    判活口径（graph-existence-v1）：剔除的前提是召回看不见**且** get_node
    返回 None（图中确认不存在）——召回看不见单独不构成失效依据。
    """
    detail = _refreshable_link_case(service)
    # old-1 召回不可见且图内已删除（判活探查确认不存在）
    _patch_recall(monkeypatch, [], client=_DeadGraphClient())
    out = service.refresh_candidates(detail["id"], detail["version"], actor())
    assert out["candidate"]["existingCandidates"] == []
    assert out["version"] == detail["version"] + 1
    refresh = out["candidate"]["_candidateRefresh"]
    assert refresh["removedVids"] == ["old-1"]
    assert refresh["livenessPolicy"] == "graph-existence-v1"
    events = _audit_events(service, detail["id"])
    assert events.count("CANDIDATES_REFRESHED") == 1


def test_refresh_keeps_live_candidate_when_recall_invisible(service, monkeypatch):
    """误杀防护（10-21 事故形态）：召回看不见≠图中没有。

    跨列同名候选（Jian Huang 案候选分组在「黄健」）召回按名取空、Milvus
    true_zero 时，判活走 get_node——图内存活则原样保留，真 no-op：不动版本、
    不落审计、不写 _candidateRefresh（候选/属性对照/merge 目标不消失）。
    """
    detail = _refreshable_link_case(service)
    _patch_recall(monkeypatch, [], client=_AliveGraphClient())
    out = service.refresh_candidates(detail["id"], detail["version"], actor())
    assert out["candidate"]["existingCandidates"] == detail["candidate"]["existingCandidates"]
    assert out["version"] == detail["version"]
    assert "_candidateRefresh" not in out["candidate"]
    assert "CANDIDATES_REFRESHED" not in _audit_events(service, detail["id"])


def test_refresh_probe_failure_keeps_candidate_conservative(service, monkeypatch):
    """探查失败≠失效：get_node 抛错时保守按存活保留（宁可不剔除，不误杀）。

    保守保留的候选不做名称/得分刷新（未被重评分），新召回候选照常追加；
    失败计数进 _candidateRefresh.livenessProbeFailed 供观测。
    """
    detail = _refreshable_link_case(service)
    _patch_recall(
        monkeypatch,
        [{"vid": "fresh-2", "name": "张三丰", "props": {}}],
        client=_BrokenProbeClient(),
    )
    out = service.refresh_candidates(detail["id"], detail["version"], actor())
    vids = [c["vid"] for c in out["candidate"]["existingCandidates"]]
    assert vids == ["old-1", "fresh-2"]
    # old-1 条目逐字段未动（探查失败的原样保留路径，不重评分）
    assert out["candidate"]["existingCandidates"][0] == {
        "vid": "old-1",
        "name": "张三",
        "score": 0.7,
    }
    refresh = out["candidate"]["_candidateRefresh"]
    assert refresh["removedVids"] == []
    assert refresh["addedVids"] == ["fresh-2"]
    assert refresh["livenessProbeFailed"] == 1
    assert refresh["livenessPolicy"] == "graph-existence-v1"


def test_refresh_picks_up_cross_column_candidate(service, monkeypatch):
    """跨列同名候选可新增：召回按候选自身显示名分组，展平全部桶后跨键候选可见。

    修复前 refresh 只取 .get(案件显示名) 单桶——分组键与案件名不同列的
    候选（机构双语名最典型）永远进不了新增集。
    """
    detail = _refreshable_link_case(service)
    # 案件显示名=张三；召回分组只有跨键桶「黄健」（无查询名桶）
    _patch_recall(
        monkeypatch,
        [],
        grouped={"黄健": [{"vid": "cross-1", "name": "黄健", "props": {}}]},
        client=_AliveGraphClient(),
    )
    out = service.refresh_candidates(detail["id"], detail["version"], actor())
    vids = [c["vid"] for c in out["candidate"]["existingCandidates"]]
    assert vids == ["old-1", "cross-1"]
    refresh = out["candidate"]["_candidateRefresh"]
    assert refresh["addedVids"] == ["cross-1"]
    assert refresh["removedVids"] == []


def test_refresh_true_noop_keeps_version(service, monkeypatch):
    """召回结果与现快照完全一致（零新增零剔除零变化）→ 不动版本不落审计。"""
    detail = _refreshable_link_case(service)
    _patch_recall(
        monkeypatch,
        [{"vid": "old-1", "name": "张三", "props": {}}],
        score=0.7,  # 与快照 score 完全一致
    )
    out = service.refresh_candidates(detail["id"], detail["version"], actor())
    assert out["version"] == detail["version"]
    assert "CANDIDATES_REFRESHED" not in _audit_events(service, detail["id"])
    assert "_candidateRefresh" not in out["candidate"]


def test_refresh_uses_case_graph_space(service, monkeypatch):
    """召回按案件图空间+快照节点标签重跑（跨空间不串）。"""
    detail = _refreshable_link_case(service)
    calls: list[dict] = []
    _patch_recall(monkeypatch, [], calls=calls)
    service.refresh_candidates(detail["id"], detail["version"], actor())
    assert calls == [{"tag": "Expert", "names": ["张三"], "space": "dev2"}]


def test_refresh_conflict_on_stale_version(service, monkeypatch):
    """刷新/刷新（或刷新/提交）并发：后到者按 version CAS 拒绝（409 口径）。"""
    detail = _refreshable_link_case(service)
    _patch_recall(
        monkeypatch,
        [{"vid": "fresh-2", "name": "张三丰", "props": {}}],
    )
    first = service.refresh_candidates(detail["id"], detail["version"], actor())
    # 召回结果有新变化（又见新候选）才能构成第二次「变更」，此时旧版本被 CAS 拒
    _patch_recall(
        monkeypatch,
        [
            {"vid": "old-1", "name": "张三", "props": {}},
            {"vid": "fresh-3", "name": "张三省", "props": {}},
        ],
    )
    with pytest.raises(ReviewConflictError):
        service.refresh_candidates(detail["id"], detail["version"], actor())
    # 持新版本再刷即可（拿最新 version 重试；判活探查确认候选确已不在图内）
    _patch_recall(monkeypatch, [], client=_DeadGraphClient())
    second = service.refresh_candidates(first["id"], first["version"], actor())
    assert second["candidate"]["existingCandidates"] == []


def test_refresh_rejects_terminal_case(service, monkeypatch):
    detail = _refreshable_link_case(service)
    # reject-candidate 不触图写（entity-confirm/create 会走 _apply_link_verdict 写图）
    service.submit(
        detail["id"],
        detail["version"],
        "reject-candidate",
        {"entityVerdict": "reject"},
        "",
        actor(),
    )
    _patch_recall(monkeypatch, [])
    with pytest.raises(ReviewConflictError):
        service.refresh_candidates(detail["id"], detail["version"] + 5, actor())


def test_refresh_rejects_cases_without_pending_incoming(service, monkeypatch):
    """存量写后案（无 _incoming）/ 非 T_LINK 模板不支持刷新（422 口径）。"""
    created = service.create_direct_case(**link_case_kwargs())  # 无 _incoming 的 T_LINK
    detail = service.get_case(created["reviewId"], actor())
    _patch_recall(monkeypatch, [])
    with pytest.raises(ReviewValidationError):
        service.refresh_candidates(detail["id"], detail["version"], actor())
