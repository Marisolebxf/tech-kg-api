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


@pytest.mark.anyio
async def test_http_batch_delete_mixed_results(async_client, production_api):
    """批量删除：可删的删、终态/不存在/重复 id 按条跳过互不影响，聚合返回计数与原因。"""
    app, service = production_api

    def as_admin():
        return identity("admin-1", ("review_admin",))

    open_1 = service.create_direct_case(**_link_kwargs(task_id="TASK-BD-1"))["reviewId"]
    open_2 = service.create_direct_case(
        **_link_kwargs(
            task_id="TASK-BD-2",
            execution_id="EXEC-BD-2",
            object_id="S-BD-2",
            candidate={
                "scholar_id": "S-BD-2",
                "name_zh": "测试专家二号",
                "existingCandidates": [{"id": "E-1"}],
            },
        )
    )["reviewId"]
    # 终态：直审 submit 即 RESOLVED
    resolved_id = service.create_direct_case(
        **_link_kwargs(
            task_id="TASK-BD-3",
            execution_id="EXEC-BD-3",
            object_id="S-BD-3",
            candidate={
                "scholar_id": "S-BD-3",
                "name_zh": "测试专家三号",
                "existingCandidates": [{"id": "E-1"}],
            },
        )
    )["reviewId"]
    service.submit(resolved_id, 1, "entity-confirm", {"entityVerdict": "create"}, "", identity())

    app.dependency_overrides[get_review_identity] = as_admin
    try:
        res = await async_client.post(
            "/api/v1/manual-reviews/production/batch-delete",
            json={"caseIds": [open_1, "MR-404", open_2, resolved_id, open_1]},
        )
        assert res.status_code == 200
        data = res.json()["data"]
        # 重复 id 去重后按 4 条计：2 条删除 + 不存在/已处理各跳过 1 条
        assert data["requested"] == 4
        assert data["deleted"] == 2
        assert {item["id"]: item["reason"] for item in data["skipped"]} == {
            "MR-404": "人工处理任务不存在",
            resolved_id: "已处理的记录不可删除",
        }
        assert (
            await async_client.get(f"/api/v1/manual-reviews/production/{open_1}")
        ).status_code == 404
    finally:
        app.dependency_overrides[get_review_identity] = lambda: identity()


@pytest.mark.anyio
async def test_http_batch_delete_requires_review_admin_per_case(async_client, production_api):
    """批量删除无 review_admin 身份：不整批 403，逐条跳过并带回无权原因（与单删 403 口径对应）。"""
    _, service = production_api
    case_id = service.create_direct_case(**_link_kwargs(task_id="TASK-BD-403"))["reviewId"]

    # 默认 identity 只有 reviewer：单删会 403；批量路径把拒绝落到每条的 skipped 里
    res = await async_client.post(
        "/api/v1/manual-reviews/production/batch-delete",
        json={"caseIds": [case_id]},
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["deleted"] == 0
    assert [item["id"] for item in data["skipped"]] == [case_id]
    assert "无权" in data["skipped"][0]["reason"]
    # case 未被删掉
    assert (
        await async_client.get(f"/api/v1/manual-reviews/production/{case_id}")
    ).status_code == 200


@pytest.mark.anyio
async def test_http_queue_follows_graph_space_param(async_client, production_api):
    """队列跟随图空间：graphSpace 查询参数过滤 + 响应缓存按空间分键（连续查不同空间不得命中彼此缓存）。"""
    from biz.handler import manual_review as handler_module

    _, service = production_api
    handler_module._queue_cache_clear()
    try:
        service.create_direct_case(**_link_kwargs(graph_space="dev2"))
        service.create_direct_case(
            **_link_kwargs(
                task_id="TASK-API-2",
                execution_id="EXEC-API-2",
                object_id="S-API-2",
                candidate={
                    "scholar_id": "S-API-2",
                    "name_zh": "测试专家二号",
                    "existingCandidates": [{"id": "E-1"}],
                },
                reason="同名冲突待人工裁决（第二条）",
                graph_space="gaoxing_test",
            )
        )
        dev2 = (
            await async_client.get(
                "/api/v1/manual-reviews/production/queue", params={"graphSpace": "dev2"}
            )
        ).json()["data"]
        assert dev2["total"] == 1
        assert dev2["items"][0]["graphSpace"] == "dev2"
        # 紧接着查另一空间：缓存键含 graphSpace，不得串台
        gx = (
            await async_client.get(
                "/api/v1/manual-reviews/production/queue", params={"graphSpace": "gaoxing_test"}
            )
        ).json()["data"]
        assert gx["total"] == 1
        assert gx["items"][0]["graphSpace"] == "gaoxing_test"
        # 不带空间=跨空间全量（老口径兜底）
        everything = (await async_client.get("/api/v1/manual-reviews/production/queue")).json()[
            "data"
        ]
        assert everything["total"] == 2
    finally:
        handler_module._queue_cache_clear()


@pytest.mark.anyio
async def test_http_queue_block_cache_reuses_adjacent_pages(async_client, production_api):
    """翻页提速（对齐实体列表）：页请求对齐 100 条块缓存，同块相邻页不再查库。"""
    _, service = production_api
    for i in range(25):
        service.create_direct_case(
            **_link_kwargs(task_id=f"TASK-BLK-{i}", execution_id=f"EXEC-BLK-{i}")
        )
    calls = {"n": 0}
    original = service.list_cases

    def counting(f, a):
        calls["n"] += 1
        return original(f, a)

    service.list_cases = counting
    try:
        first = await async_client.get(
            "/api/v1/manual-reviews/production/queue", params={"category": "A", "pageSize": 20}
        )
        assert first.headers["x-review-queue-cache"] == "MISS"
        first_data = first.json()["data"]
        assert first_data["total"] == 25
        assert len(first_data["items"]) == 20
        assert first_data["page"] == 1
        assert calls["n"] == 1

        second = await async_client.get(
            "/api/v1/manual-reviews/production/queue",
            params={"category": "A", "pageSize": 20, "page": 2},
        )
        assert second.headers["x-review-queue-cache"] == "HIT"
        second_data = second.json()["data"]
        assert second_data["total"] == 25
        assert len(second_data["items"]) == 5
        assert second_data["page"] == 2
        # 第 1、2 页同属一个 100 条块：只有块计算那一次查库
        assert calls["n"] == 1

        # 改过滤=新块键：重新查库（MISS）
        filtered = await async_client.get(
            "/api/v1/manual-reviews/production/queue",
            params={"category": "A", "pageSize": 20, "page": 1, "status": "OPEN"},
        )
        assert filtered.headers["x-review-queue-cache"] == "MISS"
        assert calls["n"] == 2
    finally:
        service.list_cases = original
        from biz.handler import manual_review as handler_module

        handler_module._queue_cache_clear()


@pytest.mark.anyio
async def test_http_queue_page_spanning_blocks_stitches(async_client, production_api):
    """跨块的页（pageSize 整除不了 100 时）补拉下一块拼接，行序连续不丢不重。"""
    _, service = production_api
    for i in range(105):
        service.create_direct_case(
            **_link_kwargs(task_id=f"TASK-SPN-{i}", execution_id=f"EXEC-SPN-{i}")
        )
    calls = {"n": 0}
    original = service.list_cases

    def counting(f, a):
        calls["n"] += 1
        return original(f, a)

    service.list_cases = counting
    try:
        page4 = await async_client.get(
            "/api/v1/manual-reviews/production/queue",
            params={"category": "A", "pageSize": 30, "page": 4},
        )
        data = page4.json()["data"]
        assert data["total"] == 105
        # 第 4 页=第 90-104 行（105 条只剩 15 行）：横跨块边界补拉下一块拼接
        assert len(data["items"]) == 15
        assert data["page"] == 4
        # 跨块页两块各查一次
        assert calls["n"] == 2
        # 与未切片的整段顺序一致（默认排序下取 90-104 行）
        direct = original({"category": "A", "page": 4, "page_size": 30}, identity())
        assert [item["id"] for item in data["items"]] == [item["id"] for item in direct["items"]]
    finally:
        service.list_cases = original
        from biz.handler import manual_review as handler_module

        handler_module._queue_cache_clear()


@pytest.mark.anyio
async def test_http_queue_rbac_disables_cache_not_slicing(
    async_client, production_api, monkeypatch
):
    """RBAC 开启时响应缓存禁用（口径不变），但块切片/翻页行为保持正确。

    只替换 handler 模块内的 rbac_enabled 开关：域层空间解析（platform_actor
    /权限库）由 test_manual_review_business_rbac 独立覆盖，这里不依赖平台库。
    """
    _, service = production_api
    for i in range(8):
        service.create_direct_case(
            **_link_kwargs(task_id=f"TASK-RB-{i}", execution_id=f"EXEC-RB-{i}")
        )
    from biz.handler import manual_review as handler_module

    monkeypatch.setattr(handler_module, "rbac_enabled", lambda: True)
    calls = {"n": 0}
    original = service.list_cases

    def counting(f, a):
        calls["n"] += 1
        return original(f, a)

    service.list_cases = counting
    try:
        first = await async_client.get(
            "/api/v1/manual-reviews/production/queue", params={"category": "A", "pageSize": 5}
        )
        assert first.headers["x-review-queue-cache"] == "MISS"
        assert len(first.json()["data"]["items"]) == 5
        second = await async_client.get(
            "/api/v1/manual-reviews/production/queue",
            params={"category": "A", "pageSize": 5, "page": 2},
        )
        assert second.headers["x-review-queue-cache"] == "MISS"
        second_data = second.json()["data"]
        # RBAC 下不缓存：两次请求各查一次库，切片仍正确
        assert calls["n"] == 2
        assert len(second_data["items"]) == 3
        assert {item["id"] for item in first.json()["data"]["items"]}.isdisjoint(
            {item["id"] for item in second_data["items"]}
        )
    finally:
        service.list_cases = original
        handler_module._queue_cache_clear()
