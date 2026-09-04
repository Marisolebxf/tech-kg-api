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


@pytest.mark.anyio
async def test_http_create_queue_claim_draft_submit(async_client, production_api):
    body = {
        "sourceTaskId": "TASK-API",
        "nodeId": "quality",
        "objectId": "OBJ-API",
        "objectType": "论文",
        "objectName": "测试论文",
        "errorType": "标题缺失",
        "domain": "talent",
        "phase": "数据处理",
    }
    created = (await async_client.post("/api/v1/manual-reviews/internal/cases", json=body)).json()[
        "data"
    ]
    queue = (
        await async_client.get(
            "/api/v1/manual-reviews/production/queue", params={"queue": "unclaimed"}
        )
    ).json()["data"]
    assert queue["total"] == 1
    assert queue["items"][0]["id"] == created["id"]
    claimed = (
        await async_client.post(
            f"/api/v1/manual-reviews/production/{created['id']}/claim",
            json={"version": created["version"]},
        )
    ).json()["data"]
    drafted = (
        await async_client.put(
            f"/api/v1/manual-reviews/production/{created['id']}/draft",
            json={"version": claimed["version"], "payload": {"titleZh": "修正标题"}},
        )
    ).json()["data"]
    submitted = (
        await async_client.post(
            f"/api/v1/manual-reviews/production/{created['id']}/submit",
            json={
                "version": drafted["version"],
                "actionId": "save-fill-rerun",
                "result": {"titleZh": "修正标题"},
                "note": "已核验",
            },
        )
    ).json()["data"]
    assert submitted["status"] == "APPLYING"


@pytest.mark.anyio
async def test_http_p0_requires_second_approver(async_client, production_api):
    app, service = production_api
    body = {
        "sourceTaskId": "TASK-P0",
        "nodeId": "schema",
        "objectId": "OBJ-P0",
        "objectType": "企业",
        "objectName": "企业记录",
        "errorType": "Schema 字段映射失败",
        "templateId": "T_MAP",
        "domain": "talent",
        "phase": "图谱构建",
    }
    created = (await async_client.post("/api/v1/manual-reviews/internal/cases", json=body)).json()[
        "data"
    ]
    claimed = (
        await async_client.post(
            f"/api/v1/manual-reviews/production/{created['id']}/claim",
            json={"version": created["version"]},
        )
    ).json()["data"]
    submitted = (
        await async_client.post(
            f"/api/v1/manual-reviews/production/{created['id']}/submit",
            json={
                "version": claimed["version"],
                "actionId": "save-map-rerun",
                "result": {"mappings": [{"source": "a", "target": "b"}]},
            },
        )
    ).json()["data"]
    assert submitted["status"] == "PENDING_APPROVAL"
    app.dependency_overrides[get_review_identity] = lambda: identity("approver-2", ("approver",))
    approved = (
        await async_client.post(
            f"/api/v1/manual-reviews/production/{created['id']}/approve",
            json={"version": submitted["version"], "note": "批准"},
        )
    ).json()["data"]
    assert approved["status"] == "APPLYING"
