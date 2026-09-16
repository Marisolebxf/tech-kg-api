"""间接关系标注接口测试：sqlite 内存库覆盖 MySQL 会话。"""

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from biz.handler.expert_indirect_relation import router as expert_indirect_relation_router
from db_model.base import Base
from db_model.indirect_relation_annotation import IndirectRelationAnnotation
from infra.mysql import get_session

ANNOTATIONS_URL = "/api/v1/kg-construction/expert-indirect-relations/annotations"


@pytest.fixture
async def annotation_api() -> tuple[AsyncClient, sessionmaker[Session]]:
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
    app.include_router(expert_indirect_relation_router, prefix="/api/v1")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, factory


async def test_list_annotations_returns_empty_when_none_saved(
    annotation_api: tuple[AsyncClient, sessionmaker[Session]],
) -> None:
    client, _ = annotation_api
    response = await client.get(ANNOTATIONS_URL, params={"edges": "person_a:person_b"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    assert payload["data"]["items"] == []


async def test_upsert_annotation_insert_then_update(
    annotation_api: tuple[AsyncClient, sessionmaker[Session]],
) -> None:
    client, factory = annotation_api
    created = await client.post(
        ANNOTATIONS_URL,
        json={
            "sourceVid": "person_a",
            "targetVid": "person_b",
            "annotation": "重点合作对象",
        },
    )
    assert created.status_code == 200
    assert created.json()["data"]["annotation"] == "重点合作对象"

    # 再次保存同一条边：upsert 只更新标注，不新增行。
    updated = await client.post(
        ANNOTATIONS_URL,
        json={
            "sourceVid": "person_a",
            "targetVid": "person_b",
            "annotation": "已线下核实",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["annotation"] == "已线下核实"

    with factory() as session:
        rows = list(session.scalars(select(IndirectRelationAnnotation)))
        assert len(rows) == 1
        assert rows[0].annotation == "已线下核实"
        assert rows[0].create_time is not None
        assert rows[0].update_time is not None


async def test_upsert_and_list_normalize_edge_direction(
    annotation_api: tuple[AsyncClient, sessionmaker[Session]],
) -> None:
    client, _ = annotation_api
    # 反向写入（target 在前）也应命中同一行。
    saved = await client.post(
        ANNOTATIONS_URL,
        json={
            "sourceVid": "person_z",
            "targetVid": "person_a",
            "annotation": "方向归一",
        },
    )
    assert saved.status_code == 200
    assert saved.json()["data"]["sourceVid"] == "person_a"
    assert saved.json()["data"]["targetVid"] == "person_z"

    listed = await client.get(ANNOTATIONS_URL, params={"edges": "person_z:person_a"})
    assert listed.status_code == 200
    items = listed.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["annotation"] == "方向归一"


async def test_list_annotations_only_returns_saved_edges(
    annotation_api: tuple[AsyncClient, sessionmaker[Session]],
) -> None:
    client, _ = annotation_api
    await client.post(
        ANNOTATIONS_URL,
        json={"sourceVid": "person_a", "targetVid": "person_b", "annotation": "有标注"},
    )
    response = await client.get(
        ANNOTATIONS_URL,
        params={"edges": "person_a:person_b,person_c:person_d"},
    )
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["annotation"] == "有标注"


async def test_list_annotations_rejects_malformed_edge(
    annotation_api: tuple[AsyncClient, sessionmaker[Session]],
) -> None:
    client, _ = annotation_api
    response = await client.get(ANNOTATIONS_URL, params={"edges": "person_a"})
    assert response.status_code == 422


async def test_upsert_annotation_rejects_abnormal_chars(
    annotation_api: tuple[AsyncClient, sessionmaker[Session]],
) -> None:
    client, _ = annotation_api
    response = await client.post(
        ANNOTATIONS_URL,
        json={"sourceVid": "person_a", "targetVid": "person_b", "annotation": "重点!"},
    )
    assert response.status_code == 422


async def test_upsert_annotation_allows_empty_to_clear(
    annotation_api: tuple[AsyncClient, sessionmaker[Session]],
) -> None:
    client, _ = annotation_api
    await client.post(
        ANNOTATIONS_URL,
        json={"sourceVid": "person_a", "targetVid": "person_b", "annotation": "待清除"},
    )
    cleared = await client.post(
        ANNOTATIONS_URL,
        json={"sourceVid": "person_a", "targetVid": "person_b", "annotation": ""},
    )
    assert cleared.status_code == 200
    assert cleared.json()["data"]["annotation"] == ""
