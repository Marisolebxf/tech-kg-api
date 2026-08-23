from collections.abc import Generator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from biz.dependencies.auth import require_platform_actor, require_platform_admin
from biz.handler.correction import router as correction_router
from db_model.base import Base
from infra.mysql import get_session
from service.correction import process_due_sync_tasks
from service.platform_access import PlatformActor


def _admin() -> PlatformActor:
    return PlatformActor(
        user_id="admin-1",
        username="admin",
        display_name="测试管理员",
        email="admin@techkg.test",
        is_admin=True,
    )


@pytest.fixture
async def correction_api() -> tuple[AsyncClient, sessionmaker[Session]]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session() -> Generator[Session, None, None]:
        with factory() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    app = FastAPI()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[require_platform_actor] = _admin
    app.dependency_overrides[require_platform_admin] = _admin
    app.include_router(correction_router, prefix="/api/v1")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, factory


async def test_correction_crud_and_projection_sync_api(
    correction_api: tuple[AsyncClient, sessionmaker[Session]],
) -> None:
    client, factory = correction_api
    created = await client.post(
        "/api/v1/corrections",
        json={
            "target_type": "expert",
            "operation": "delete",
            "target_id": "person-api-test",
            "title": "删除无效专家记录",
            "reason": "该记录已确认无效",
            "before_data": {"name_zh": "测试专家"},
            "after_data": {},
        },
    )
    assert created.status_code == 201
    correction_id = created.json()["data"]["id"]

    listed = await client.get("/api/v1/corrections", params={"scope": "all"})
    detailed = await client.get(f"/api/v1/corrections/{correction_id}")
    updated = await client.patch(
        f"/api/v1/corrections/{correction_id}",
        json={"reason": "已经二次核验，确认记录无效"},
    )
    reviewed = await client.post(
        f"/api/v1/corrections/{correction_id}/review",
        json={"decision": "approve", "note": "审核通过"},
    )

    assert listed.json()["data"]["total"] == 1
    assert detailed.json()["data"]["operation"] == "delete"
    assert updated.json()["data"]["version"] == 2
    assert reviewed.json()["data"]["status"] == "PENDING_SYNC"

    with factory() as session:
        assert process_due_sync_tasks(session, sync_mode="projection") == 1
        session.commit()

    completed = await client.get(f"/api/v1/corrections/{correction_id}")
    data = completed.json()["data"]
    assert data["status"] == "COMPLETED"
    assert data["sync"]["mysqlStatus"] == "SUCCEEDED"
    assert data["sync"]["graphStatus"] == "SKIPPED"
    assert [item["action"] for item in data["history"]] == [
        "SUBMIT",
        "EDIT",
        "APPROVE",
        "SYNC_SUCCEEDED",
    ]


async def test_pending_correction_can_be_cancelled_through_delete_api(
    correction_api: tuple[AsyncClient, sessionmaker[Session]],
) -> None:
    client, _ = correction_api
    created = await client.post(
        "/api/v1/corrections",
        json={
            "target_type": "organization",
            "operation": "update",
            "target_id": "org-api-test",
            "title": "修正机构名称",
            "reason": "机构官网已更名",
            "before_data": {"name_cn": "旧名称"},
            "after_data": {"name_cn": "新名称"},
        },
    )
    correction_id = created.json()["data"]["id"]

    cancelled = await client.delete(f"/api/v1/corrections/{correction_id}")

    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["status"] == "CANCELLED"
    assert [item["action"] for item in cancelled.json()["data"]["history"]] == [
        "SUBMIT",
        "CANCEL",
    ]
