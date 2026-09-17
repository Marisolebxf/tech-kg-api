"""人工审核核心生命周期单测：建案幂等 / 领取乐观锁 / 裁决记录 / 四方签核 / 直判写图。

建案入口是 ``create_direct_case``（kg.custom.steps / 同名冲突 / 抽取失败共用）；
graph-build 移交通道（内部入口 / correction / outbox）已删除，submit 只记录决议。
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db_model.base import Base
from db_model.manual_review import ReviewAuditLog, ReviewCase
from service.manual_review_domain import (
    ReviewConflictError,
    ReviewForbiddenError,
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


def test_p0_requires_different_approver(service):
    # confidence < 0.7 → P0，submit 进四方签核
    case = claimed(service, confidence=0.4)
    case = service.submit(
        case["id"],
        case["version"],
        "entity-confirm",
        {"entityVerdict": "merge", "targetEntityId": "E-1"},
        "",
        actor(),
    )
    assert case["status"] == "PENDING_APPROVAL"
    with pytest.raises(ReviewForbiddenError):
        service.approve(case["id"], case["version"], True, "", actor("reviewer-1", ("approver",)))
    approved = service.approve(
        case["id"], case["version"], True, "", actor("approver-2", ("approver",))
    )
    assert approved["status"] == "RESOLVED"


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


# ── 失败列表：队列排序 + 硬删除 ─────────────────────────────────────────────


def extract_case_kwargs(**overrides):
    """抽取失败 T_EXTRACT_FAIL 建案参数（domain 与 actor 的 talent 匹配）。"""
    value = dict(
        task_id="TASK-E",
        execution_id="EXEC-E",
        step_id="extract",
        kind="entity",
        candidate={"recordId": "R-1", "error": "boom"},
        object_id="R-1",
        reason="抽取失败",
        source_table="dwd_paper",
        source_record_id="R-1",
        domain="talent",
        template_id="T_EXTRACT_FAIL",
    )
    value.update(overrides)
    return value


def _set_case_times(service, case_id, created, updated):
    """直接拨 created_at/updated_at，制造确定性排序时序。"""
    with service.sf() as s:
        s.execute(
            update(ReviewCase)
            .where(ReviewCase.id == case_id)
            .values(created_at=created, updated_at=updated)
        )
        s.commit()


def test_queue_sort_by_updated_at(service):
    from datetime import datetime, timedelta

    base = datetime(2026, 9, 17, 12, 0, 0)
    old_case = service.create_direct_case(
        **extract_case_kwargs(
            object_id="R-OLD",
            source_record_id="R-OLD",
            candidate={"recordId": "R-OLD", "error": "boom"},
        )
    )
    new_case = service.create_direct_case(
        **extract_case_kwargs(
            object_id="R-NEW",
            source_record_id="R-NEW",
            candidate={"recordId": "R-NEW", "error": "boom"},
        )
    )
    # 创建顺序 old→new；old 创建早但更新晚，两种排序口径结果相反
    _set_case_times(service, old_case["reviewId"], base, base + timedelta(hours=1))
    _set_case_times(service, new_case["reviewId"], base + timedelta(minutes=1), base)

    def queue_ids(extra=None):
        return [
            x["id"]
            for x in service.list_cases({**{"category": "C"}, **(extra or {})}, actor())["items"]
        ]

    # 默认排序保持 风险级→创建时间升序（不传 sort）
    assert queue_ids() == [old_case["reviewId"], new_case["reviewId"]]
    # sort=updatedAt desc：更新时间新的在前
    assert queue_ids({"sort": "updatedAt", "order": "desc"}) == [
        old_case["reviewId"],
        new_case["reviewId"],
    ]
    # sort=updatedAt asc
    assert queue_ids({"sort": "updatedAt", "order": "asc"}) == [
        new_case["reviewId"],
        old_case["reviewId"],
    ]


def test_delete_cases_hard_deletes_extract_fail_only(service):
    extract = service.create_direct_case(**extract_case_kwargs())
    link = service.create_direct_case(**link_case_kwargs(domain="talent"))
    admin = actor("admin-1", ("reviewer", "review_admin"))

    result = service.delete_cases([extract["reviewId"], link["reviewId"], "MR-NOT-EXIST"], admin)
    assert result == {"deleted": 1, "skipped": 2}

    # C 类队列不再出现；A 类 case 不受影响
    remaining_c = {x["id"] for x in service.list_cases({"category": "C"}, actor())["items"]}
    assert extract["reviewId"] not in remaining_c
    all_ids = {x["id"] for x in service.list_cases({}, actor())["items"]}
    assert link["reviewId"] in all_ids
    # 审计等子记录一并清除
    with service.sf() as s:
        assert (
            s.scalars(
                select(ReviewAuditLog).where(ReviewAuditLog.case_id == extract["reviewId"])
            ).all()
            == []
        )


def test_delete_cases_requires_review_admin(service):
    extract = service.create_direct_case(**extract_case_kwargs())
    with pytest.raises(ReviewForbiddenError):
        service.delete_cases([extract["reviewId"]], actor())
