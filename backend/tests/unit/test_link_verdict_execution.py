"""T_LINK 裁决执行器单测：merge/create 真实写图 / 候选注入拒绝 / 空值保护 /
待定关系补写 / OPEN 直审（含 P0，提交即执行） / 存量写后 case 兼容 /
关系端点扣留与改写。"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db_model.base import Base
from service.manual_review_domain import ReviewIdentity, ReviewValidationError
from service.manual_review_production import ManualReviewService


def actor(uid="reviewer-1", roles=("reviewer",)):
    return ReviewIdentity(uid, uid, frozenset(roles), frozenset({"talent"}), "org", "req-1")


def _make_service():
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return ManualReviewService(sessionmaker(engine, expire_on_commit=False))


class FakeGraph:
    """假图客户端：DESCRIBE 返回空 schema（_coerce_to_schema 走原样透传分支）。"""

    def __init__(self):
        self.writes: list[str] = []
        self.edges: list[tuple[str, str, str, dict]] = []

    def connect(self):
        pass

    def close(self):
        pass

    def execute_write(self, stmt):
        self.writes.append(stmt)

    def create_edge(self, frm, to, edge_type, props):
        self.edges.append((frm, to, edge_type, props))

    def execute_query(self, q):
        class _Result:
            records = []

        return _Result()


@pytest.fixture
def service():
    return _make_service()


@pytest.fixture
def graph(monkeypatch):
    fake = FakeGraph()
    monkeypatch.setattr(ManualReviewService, "_graph_client_for", lambda self, snapshot: fake)
    return fake


def gray_case_kwargs(**overrides):
    """写前扣留 T_LINK 建案参数（confidence 0.9 → P1，单人裁决即执行）。"""
    value = dict(
        task_id="TASK-1",
        execution_id="EXEC-1",
        step_id="align",
        kind="entity",
        candidate={
            "name": "示例研究院",
            "newIds": ["org_new_1"],
            "existingCandidates": [{"vid": "org_9", "name": "示例研究院", "score": 0.8}],
            "_incoming": {
                "vid": "org_new_1",
                "props": {"name": "示例研究院", "province": "北京", "memo": None},
                "sourceTable": "db.org_table",
            },
            "_pendingRelations": [],
            "_graphSpace": "dev2",
        },
        object_id="org_new_1",
        object_name="示例研究院",
        node_label="Organization",
        reason="消歧得分 0.80 落入灰区",
        confidence=0.9,
        domain="talent",
        template_id="T_LINK",
    )
    value.update(overrides)
    return value


def opened(service, **overrides):
    """直审模式：建案即 OPEN，get_case 取 id/version 后直接提交（无需领取）。"""
    case = service.create_direct_case(**gray_case_kwargs(**overrides))
    detail = service.get_case(case["reviewId"], actor())
    return detail["id"], detail["version"]


def test_merge_writes_withheld_vertex_to_target_and_flushes_pending(service, graph):
    case = service.create_direct_case(
        **gray_case_kwargs(
            candidate={
                **gray_case_kwargs()["candidate"],
                "_pendingRelations": [
                    {
                        "edgeType": "EMPLOYED_BY",
                        "fromId": "org_new_1",
                        "toId": "person_1",
                        "props": {"role": "engineer"},
                    }
                ],
            }
        )
    )
    detail = service.get_case(case["reviewId"], actor())
    out = service.submit(
        detail["id"],
        detail["version"],
        "entity-confirm",
        {"entityVerdict": "merge", "targetEntityId": "org_9"},
        "",
        actor(),
    )
    assert out["status"] == "RESOLVED"
    assert len(graph.writes) == 1
    assert 'VALUES "org_9"' in graph.writes[0]
    assert "province" in graph.writes[0]
    # 空值列不写＝不覆盖目标已有值
    assert "memo" not in graph.writes[0]
    # 待定关系按改写端点补写（预留 vid → 目标 vid）
    assert graph.edges == [("org_9", "person_1", "EMPLOYED_BY", {"role": "engineer"})]


def test_create_writes_to_reserved_vid(service, graph):
    case_id, version = opened(service)
    out = service.submit(
        case_id, version, "entity-confirm", {"entityVerdict": "create"}, "", actor()
    )
    assert out["status"] == "RESOLVED"
    assert 'VALUES "org_new_1"' in graph.writes[0]
    assert graph.edges == []


def test_merge_target_outside_candidates_rejected_then_retry_succeeds(service, graph):
    case_id, version = opened(service)
    with pytest.raises(ReviewValidationError):
        service.submit(
            case_id,
            version,
            "entity-confirm",
            {"entityVerdict": "merge", "targetEntityId": "org_evil"},
            "",
            actor(),
        )
    # 异常即回滚（未提交事务）：状态与版本未变，重新提交有效目标即成功
    assert graph.writes == []
    out = service.submit(
        case_id,
        version,
        "entity-confirm",
        {"entityVerdict": "merge", "targetEntityId": "org_9"},
        "",
        actor(),
    )
    assert out["status"] == "RESOLVED"


def test_legacy_post_write_case_records_verdict_without_writing(service, graph):
    case = service.create_direct_case(
        **gray_case_kwargs(
            candidate={
                "name": "存量实体",
                "newIds": ["a", "b"],
                "existingCandidates": [{"vid": "c", "name": "存量实体"}],
            }
        )
    )
    detail = service.get_case(case["reviewId"], actor())
    out = service.submit(
        detail["id"],
        detail["version"],
        "entity-confirm",
        {"entityVerdict": "merge", "targetEntityId": "c"},
        "",
        actor(),
    )
    assert out["status"] == "RESOLVED"
    assert graph.writes == []  # 存量写后 case：实体已在图，仅记录决议


def test_reject_candidate_writes_nothing(service, graph):
    case_id, version = opened(service)
    out = service.submit(
        case_id, version, "reject-candidate", {"entityVerdict": "reject"}, "", actor()
    )
    assert out["status"] == "RESOLVED"
    assert graph.writes == []
    assert graph.edges == []


def test_p0_link_case_executes_at_submit_without_approval(service, graph):
    # 直审模式：P0（confidence 0.5）同样提交即执行，不再走四方签核
    case = service.create_direct_case(**gray_case_kwargs(confidence=0.5))
    detail = service.get_case(case["reviewId"], actor())
    out = service.submit(
        detail["id"],
        detail["version"],
        "entity-confirm",
        {"entityVerdict": "merge", "targetEntityId": "org_9"},
        "",
        actor(),
    )
    assert out["status"] == "RESOLVED"
    assert 'VALUES "org_9"' in graph.writes[0]


def test_park_edges_on_open_case_then_rewrite_after_merge(service, graph):
    case = service.create_direct_case(**gray_case_kwargs())
    # OPEN（未领取）也是未决：端点命中即暂存，其余照写
    out = service.park_or_rewrite_edges(
        "EMPLOYED_BY",
        [
            {"fromId": "person_1", "toId": "org_new_1", "props": {"role": "eng"}},
            {"fromId": "person_2", "toId": "org_other", "props": {}},
        ],
    )
    assert out["parked"] == 1
    assert out["dropped"] == 0
    assert [r["fromId"] for r in out["records"]] == ["person_2"]
    # 重跑同批：按边类型+端点去重，不重复暂存
    again = service.park_or_rewrite_edges(
        "EMPLOYED_BY", [{"fromId": "person_1", "toId": "org_new_1", "props": {"role": "eng"}}]
    )
    assert again["parked"] == 1
    # 裁决 merge 后：暂存边已随裁决补写；迟到的新边端点改写为目标实体
    detail = service.get_case(case["reviewId"], actor())
    service.submit(
        detail["id"],
        detail["version"],
        "entity-confirm",
        {"entityVerdict": "merge", "targetEntityId": "org_9"},
        "",
        actor(),
    )
    assert ("person_1", "org_9", "EMPLOYED_BY", {"role": "eng"}) in graph.edges
    late = service.park_or_rewrite_edges(
        "EMPLOYED_BY", [{"fromId": "person_3", "toId": "org_new_1", "props": {}}]
    )
    assert late["records"] == [{"fromId": "person_3", "toId": "org_9", "props": {}}]


def test_park_drops_edges_to_rejected_endpoint(service, graph):
    case_id, version = opened(service)
    service.submit(case_id, version, "reject-candidate", {"entityVerdict": "reject"}, "", actor())
    out = service.park_or_rewrite_edges(
        "EMPLOYED_BY", [{"fromId": "person_1", "toId": "org_new_1", "props": {}}]
    )
    assert out == {"records": [], "parked": 0, "dropped": 1}


class SchemaGraph(FakeGraph):
    """DESCRIBE 返回平台 DDL 风格 schema（NOT NULL 审计列存在）。"""

    def __init__(self):
        super().__init__()
        self.tag_fields = ("name", "province", "create_time", "update_time", "source_table")
        self.edge_fields = ("role", "create_time", "update_time", "source_table")

    def execute_query(self, q):
        fields = self.edge_fields if "DESCRIBE EDGE" in q else self.tag_fields

        class _Result:
            records = [{"Field": f, "Type": "string", "Null": "NO"} for f in fields]

        return _Result()


def test_parked_edge_write_injects_not_null_audit_columns(service, monkeypatch):
    """平台 DDL 给边注入 NOT NULL create_time/update_time（无默认值）：暂存边
    属性缺这些列时补写会被 Nebula 拒（400 not nullable）——按边 schema 补缺省。"""
    fake = SchemaGraph()
    monkeypatch.setattr(ManualReviewService, "_graph_client_for", lambda self, snapshot: fake)
    case = service.create_direct_case(
        **gray_case_kwargs(
            candidate={
                **gray_case_kwargs()["candidate"],
                "_pendingRelations": [
                    {
                        "edgeType": "EMPLOYED_BY",
                        "fromId": "org_new_1",
                        "toId": "person_1",
                        "props": {"role": "engineer", "source_table": "db.org"},
                    }
                ],
            }
        )
    )
    detail = service.get_case(case["reviewId"], actor())
    out = service.submit(
        detail["id"],
        detail["version"],
        "entity-confirm",
        {"entityVerdict": "merge", "targetEntityId": "org_9"},
        "",
        actor(),
    )
    assert out["status"] == "RESOLVED"
    ((frm, to, etype, props),) = fake.edges
    assert (frm, to, etype) == ("org_9", "person_1", "EMPLOYED_BY")
    # NOT NULL 审计列缺省即补（空串也是补了值，Nebula 不再 400）
    assert props["create_time"]
    assert props["update_time"]
    # 业务列与原溯源值保留，不被覆盖
    assert props["role"] == "engineer"
    assert props["source_table"] == "db.org"
