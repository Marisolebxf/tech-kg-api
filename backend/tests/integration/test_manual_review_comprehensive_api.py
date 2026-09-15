"""人工处理模块补充集成测试：公共端点故障/边界场景。

graph-build 移交通道（内部入口 / correction / outbox / 回调）删除后，
建案一律走 service 层 ``create_direct_case``（三个产活模板共用）：
- 三模板各自的动态详情 displaySchema
- 拒绝终态端到端
- 队列筛选（category / statusGroup / kind / keyword）与 404
- 附件类型拒绝
"""

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
def review_api(monkeypatch):
    from biz.handler import manual_review as handler
    from main import app

    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    service = ManualReviewService(sessionmaker(engine, expire_on_commit=False))
    monkeypatch.setattr(handler, "production_service", service)
    app.dependency_overrides[get_review_identity] = identity
    yield app, service
    app.dependency_overrides.pop(get_review_identity, None)


# 三产活模板 ↔ step ↔ displaySchema 首段类型
TEMPLATE_MATRIX = [
    ("align", "T_LINK", "entity-comparison"),
    ("seed", "T_DIRECT", "candidate-detail"),
    ("extract", "T_EXTRACT_FAIL", "record-error"),
]


def _kwargs(step, template, **overrides):
    value = dict(
        task_id=f"TASK-{template}",
        execution_id="EXEC-1",
        step_id=step,
        kind="entity",
        candidate={"scholar_id": f"S-{template}", "name_zh": "测试专家"},
        object_id=f"S-{template}",
        reason="需要人工审核",
        confidence=0.9,
        domain="talent",
        template_id=template,
    )
    value.update(overrides)
    return value


def set_identity(review_api, uid, roles):
    review_api[0].dependency_overrides[get_review_identity] = lambda: identity(uid, roles)


async def _claim_submit(async_client, review_id, version, action, result):
    claimed = (
        await async_client.post(
            f"/api/v1/manual-reviews/production/{review_id}/claim", json={"version": version}
        )
    ).json()["data"]
    return (
        await async_client.post(
            f"/api/v1/manual-reviews/production/{review_id}/submit",
            json={
                "version": claimed["version"],
                "actionId": action,
                "result": result,
                "note": "已核验",
            },
        )
    ).json()["data"]


# --------------------------------------------------------------------------- #
# 1. 三模板动态详情 displaySchema
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("step,template,section_type", TEMPLATE_MATRIX)
@pytest.mark.anyio
async def test_each_template_renders_correct_display_schema(
    async_client, review_api, step, template, section_type
):
    _, service = review_api
    created = service.create_direct_case(**_kwargs(step, template))
    detail = (
        await async_client.get(f"/api/v1/manual-reviews/production/{created['reviewId']}")
    ).json()["data"]
    sections = detail["template"]["displaySchema"]["sections"]
    assert sections[0]["type"] == section_type
    # resultSchema 与 allowedActions 稳定下发
    assert "resultSchema" in detail["template"]
    assert detail["consequence"]["rerunStepId"] == step


# --------------------------------------------------------------------------- #
# 2. 拒绝终态端到端（P0 四方签核后 reject）
# --------------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_reject_terminates_review(async_client, review_api):
    _, service = review_api
    created = service.create_direct_case(**_kwargs("align", "T_LINK", confidence=0.4))
    rid = created["reviewId"]
    submitted = await _claim_submit(
        async_client,
        rid,
        1,  # 新建 case version=1（建案响应不含 version）
        "entity-confirm",
        {"entityVerdict": "merge", "targetEntityId": "E-1"},
    )
    assert submitted["status"] == "PENDING_APPROVAL"
    set_identity(review_api, "approver-2", ("approver",))
    rejected = (
        await async_client.post(
            f"/api/v1/manual-reviews/production/{rid}/reject",
            json={"version": submitted["version"], "note": "拒绝"},
        )
    ).json()["data"]
    assert rejected["status"] == "REJECTED"
    # 终态后不可再领取
    set_identity(review_api, "reviewer-1", ("reviewer",))
    again = await async_client.post(
        f"/api/v1/manual-reviews/production/{rid}/claim", json={"version": rejected["version"]}
    )
    assert again.status_code == 409


# --------------------------------------------------------------------------- #
# 3. 队列筛选：category / statusGroup / kind / keyword / 404
# --------------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_queue_filters(async_client, review_api):
    _, service = review_api
    link = service.create_direct_case(**_kwargs("align", "T_LINK"))
    extract = service.create_direct_case(**_kwargs("extract", "T_EXTRACT_FAIL"))
    direct = service.create_direct_case(**_kwargs("seed", "T_DIRECT", kind="relation"))
    _ = direct

    async def q(**params):
        return (
            await async_client.get("/api/v1/manual-reviews/production/queue", params=params)
        ).json()["data"]

    # category A = T_DIRECT/T_LINK；C = T_EXTRACT_FAIL
    a_items = {x["id"] for x in (await q(category="A"))["items"]}
    c_items = {x["id"] for x in (await q(category="C"))["items"]}
    assert link["reviewId"] in a_items
    assert extract["reviewId"] not in a_items
    assert extract["reviewId"] in c_items
    # 不传 category = 全部
    assert (await q())["total"] >= 3
    # kind：T_LINK 兜底实体；relation 只看 object_type
    entity_ids = {x["id"] for x in (await q(kind="entity"))["items"]}
    relation_ids = {x["id"] for x in (await q(kind="relation"))["items"]}
    assert link["reviewId"] in entity_ids
    assert extract["reviewId"] in entity_ids
    assert direct["reviewId"] in relation_ids
    # keyword 命中对象名 / 处理实例 ID
    assert (await q(keyword="测试专家"))["total"] >= 3
    assert (await q(keyword=link["reviewId"]))["total"] == 1
    # statusGroup：pending（非终态）
    assert (await q(statusGroup="pending"))["total"] >= 3


@pytest.mark.anyio
async def test_unknown_case_returns_404(async_client, review_api):
    res = await async_client.get("/api/v1/manual-reviews/production/MR-404")
    assert res.status_code == 404


# --------------------------------------------------------------------------- #
# 4. 附件类型拒绝
# --------------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_evidence_rejects_disallowed_content_type(async_client, review_api):
    _, service = review_api
    created = service.create_direct_case(**_kwargs("align", "T_LINK"))
    await async_client.post(
        f"/api/v1/manual-reviews/production/{created['reviewId']}/claim", json={"version": 1}
    )
    res = await async_client.post(
        f"/api/v1/manual-reviews/production/{created['reviewId']}/evidence/upload-url",
        json={
            "fileName": "evil.exe",
            "contentType": "application/x-msdownload",
            "sizeBytes": 100,
            "sha256": "a" * 64,
        },
    )
    assert res.status_code == 422
