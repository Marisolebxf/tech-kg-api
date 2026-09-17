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
async def test_http_bulk_delete_requires_admin_and_preserves_a_cases(async_client, production_api):
    app, service = production_api
    extract = service.create_direct_case(
        **_link_kwargs(task_id="TASK-EXTRACT", template_id="T_EXTRACT_FAIL")
    )
    link = service.create_direct_case(**_link_kwargs())
    payload = {"caseIds": [extract["reviewId"], link["reviewId"], "MR-MISSING"]}
    endpoint = "/api/v1/manual-reviews/production/delete-cases"
    forbidden = await async_client.post(endpoint, json=payload)
    assert forbidden.status_code == 403
    app.dependency_overrides[get_review_identity] = lambda: identity("admin-1", ("review_admin",))
    deleted = await async_client.post(endpoint, json=payload)
    assert deleted.status_code == 200
    assert deleted.json()["data"] == {"deleted": 1, "skipped": 2}
    missing = await async_client.get(f"/api/v1/manual-reviews/production/{extract['reviewId']}")
    assert missing.status_code == 404
    retained = await async_client.get(f"/api/v1/manual-reviews/production/{link['reviewId']}")
    assert retained.status_code == 200


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
async def test_http_p0_submit_executes_directly(async_client, production_api):
    _, service = production_api
    # 直审模式：confidence < 0.7 → P0 同样提交即执行；审批环节（approve 端点）已移除
    created = service.create_direct_case(**_link_kwargs(confidence=0.4, task_id="TASK-P0"))
    case_id = created["reviewId"]
    submitted = (
        await async_client.post(
            f"/api/v1/manual-reviews/production/{case_id}/submit",
            json={
                "version": 1,  # 新建 case version=1（建案响应不含 version），无需领取
                "actionId": "entity-confirm",
                "result": {"entityVerdict": "merge", "targetEntityId": "E-1"},
            },
        )
    ).json()["data"]
    assert submitted["status"] == "RESOLVED"
    approve_gone = await async_client.post(
        f"/api/v1/manual-reviews/production/{case_id}/approve",
        json={"version": submitted["version"], "note": "批准"},
    )
    assert approve_gone.status_code == 404


@pytest.mark.anyio
async def test_http_delete_open_case_and_queue_exposes_execution_id(async_client, production_api):
    app, service = production_api

    def as_admin():
        return identity("admin-1", ("review_admin",))

    # 队列行带图谱构建ID（executionId）
    created = service.create_direct_case(**_link_kwargs(task_id="TASK-DEL"))
    case_id = created["reviewId"]
    queue = (
        await async_client.get("/api/v1/manual-reviews/production/queue", params={"category": "A"})
    ).json()["data"]
    row = next(r for r in queue["items"] if r["id"] == case_id)
    assert row["executionId"] == "EXEC-API"

    # DELETE 仅 review_admin：reviewer 403，admin 物理删除后详情 404
    forbidden = await async_client.delete(f"/api/v1/manual-reviews/production/{case_id}")
    assert forbidden.status_code == 403
    app.dependency_overrides[get_review_identity] = as_admin
    try:
        deleted = await async_client.delete(f"/api/v1/manual-reviews/production/{case_id}")
        assert deleted.status_code == 200
        assert deleted.json()["data"] == {"id": case_id, "deleted": True}
        detail = await async_client.get(f"/api/v1/manual-reviews/production/{case_id}")
        assert detail.status_code == 404
    finally:
        app.dependency_overrides[get_review_identity] = lambda: identity()

    # 已处理（终态）case 不给删：409
    resolved = service.create_direct_case(**_link_kwargs(task_id="TASK-DEL-2"))
    other_id = resolved["reviewId"]
    service.submit(other_id, 1, "entity-confirm", {"entityVerdict": "create"}, "", identity())
    app.dependency_overrides[get_review_identity] = as_admin
    try:
        conflict = await async_client.delete(f"/api/v1/manual-reviews/production/{other_id}")
        assert conflict.status_code == 409
    finally:
        app.dependency_overrides[get_review_identity] = lambda: identity()
