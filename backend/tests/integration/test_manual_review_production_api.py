from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from biz.dependencies.review_identity import get_review_identity
from db_model.base import Base
from service.manual_review_domain import ReviewIdentity
from service.manual_review_production import ManualReviewService


def identity(uid="reviewer-1", roles=("reviewer",)):
    return ReviewIdentity(uid, uid, frozenset(roles), frozenset({"talent"}), "org", "api-test")


@pytest.fixture
def production_api(monkeypatch):
    from biz.handler import manual_review as handler
    from main import app

    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    service = ManualReviewService(sessionmaker(engine, expire_on_commit=False))
    monkeypatch.setattr(handler, "production_service", service)
    app.dependency_overrides[get_review_identity] = lambda: identity()
    yield app, service
    app.dependency_overrides.pop(get_review_identity, None)


def _link_kwargs(**overrides):
    """同名冲突 T_LINK 建案参数（建案走 service 层 create_direct_case）。"""
    value = dict(
        task_id="TASK-API",
        execution_id="EXEC-API",
        step_id="align",
        kind="entity",
        candidate={
            "scholar_id": "S-API",
            "name_zh": "测试专家",
            "existingCandidates": [{"id": "E-1"}],
        },
        object_id="S-API",
        reason="同名冲突待人工裁决",
        confidence=0.9,
        domain="talent",
        template_id="T_LINK",
    )
    value.update(overrides)
    return value


@pytest.mark.anyio
async def test_http_queue_claim_draft_submit(async_client, production_api):
    _, service = production_api
    created = service.create_direct_case(**_link_kwargs())
    case_id = created["reviewId"]
    queue = (
        await async_client.get(
            "/api/v1/manual-reviews/production/queue", params={"queue": "unclaimed"}
        )
    ).json()["data"]
    assert queue["total"] == 1
    assert queue["items"][0]["id"] == case_id
    claimed = (
        await async_client.post(
            f"/api/v1/manual-reviews/production/{case_id}/claim",
            json={"version": 1},  # 新建 case version=1（建案响应不含 version）
        )
    ).json()["data"]
    drafted = (
        await async_client.put(
            f"/api/v1/manual-reviews/production/{case_id}/draft",
            json={"version": claimed["version"], "payload": {"entityVerdict": "create"}},
        )
    ).json()["data"]
    submitted = (
        await async_client.post(
            f"/api/v1/manual-reviews/production/{case_id}/submit",
            json={
                "version": drafted["version"],
                "actionId": "entity-confirm",
                "result": {"entityVerdict": "create"},
                "note": "已核验",
            },
        )
    ).json()["data"]
    # 无移交通道：submit 只记录决议，直接落 RESOLVED
    assert submitted["status"] == "RESOLVED"


@pytest.mark.anyio
async def test_http_p0_requires_second_approver(async_client, production_api):
    app, service = production_api
    # confidence < 0.7 → P0，submit 进四方签核
    created = service.create_direct_case(**_link_kwargs(confidence=0.4, task_id="TASK-P0"))
    case_id = created["reviewId"]
    claimed = (
        await async_client.post(
            f"/api/v1/manual-reviews/production/{case_id}/claim",
            json={"version": 1},  # 新建 case version=1（建案响应不含 version）
        )
    ).json()["data"]
    submitted = (
        await async_client.post(
            f"/api/v1/manual-reviews/production/{case_id}/submit",
            json={
                "version": claimed["version"],
                "actionId": "entity-confirm",
                "result": {"entityVerdict": "merge", "targetEntityId": "E-1"},
            },
        )
    ).json()["data"]
    assert submitted["status"] == "PENDING_APPROVAL"
    app.dependency_overrides[get_review_identity] = lambda: identity("approver-2", ("approver",))
    approved = (
        await async_client.post(
            f"/api/v1/manual-reviews/production/{case_id}/approve",
            json={"version": submitted["version"], "note": "批准"},
        )
    ).json()["data"]
    assert approved["status"] == "RESOLVED"
