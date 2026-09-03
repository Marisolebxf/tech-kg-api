from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db_model.base import Base
from db_model.manual_review import ReviewCorrection, ReviewOutbox
from service.manual_review_domain import (
    ReviewConflictError,
    ReviewForbiddenError,
    ReviewIdentity,
    ReviewValidationError,
)
from service.manual_review_production import ManualReviewService


def actor(uid="reviewer-1", roles=("reviewer",)):
    return ReviewIdentity(uid, uid, frozenset(roles), frozenset({"talent"}), "org", "req-1")


@pytest.fixture
def service():
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return ManualReviewService(sessionmaker(engine, expire_on_commit=False))


def payload(**overrides):
    value = {
        "sourceTaskId": "TASK-1",
        "nodeId": "quality",
        "objectId": "OBJ-1",
        "objectType": "论文",
        "objectName": "真实对象",
        "errorType": "标题缺失",
        "domain": "talent",
        "phase": "数据处理",
        "input": {"title": ""},
        "candidate": {},
    }
    value.update(overrides)
    return value


def claimed(service, p=None):
    case = service.create_case(p or payload(), actor())
    return service.claim(case["id"], case["version"], actor())


def test_create_is_idempotent(service):
    first = service.create_case(payload(), actor())
    second = service.create_case(payload(), actor())
    assert first['id'] == second['id']
    assert second['duplicate'] is True


def test_atomic_claim_and_optimistic_lock(service):
    case = service.create_case(payload(), actor())
    service.claim(case["id"], 1, actor())
    with pytest.raises(ReviewConflictError):
        service.claim(case["id"], 1, actor("reviewer-2"))


def test_template_action_is_server_validated(service):
    case = claimed(service)
    with pytest.raises(ReviewValidationError):
        service.submit(case["id"], case["version"], "force-pass", {}, "", actor())


def test_ordinary_decision_creates_correction_and_outbox(service):
    case = claimed(service)
    case = service.draft(case["id"], case["version"], {"titleZh": "修正标题"}, actor())
    case = service.submit(
        case["id"],
        case["version"],
        "save-fill-rerun",
        {"titleZh": "修正标题"},
        "证据已核验",
        actor(),
    )
    assert case["status"] == "APPLYING"
    with service.sf() as session:
        assert (
            session.scalar(select(ReviewCorrection).where(ReviewCorrection.case_id == case["id"]))
            is not None
        )
        assert (
            session.scalar(
                select(ReviewOutbox).where(
                    ReviewOutbox.case_id == case["id"],
                    ReviewOutbox.event_type == "RESUME_REQUESTED",
                )
            )
            is not None
        )


def test_p0_requires_different_approver(service):
    case = claimed(
        service,
        payload(
            errorType="Schema 字段映射失败", nodeId="schema", templateId="T_MAP", phase="图谱构建"
        ),
    )
    case = service.submit(
        case["id"],
        case["version"],
        "save-map-rerun",
        {"mappings": [{"source": "a", "target": "b"}]},
        "",
        actor(),
    )
    assert case["status"] == "PENDING_APPROVAL"
    with pytest.raises(ReviewForbiddenError):
        service.approve(case["id"], case["version"], True, "", actor("reviewer-1", ("approver",)))
    approved = service.approve(
        case["id"], case["version"], True, "", actor("approver-2", ("approver",))
    )
    assert approved["status"] == "APPLYING"


def test_stale_draft_does_not_overwrite(service):
    case = claimed(service)
    service.draft(case["id"], case["version"], {"titleZh": "v1"}, actor())
    with pytest.raises(ReviewConflictError):
        service.draft(case["id"], case["version"], {"titleZh": "stale"}, actor())
