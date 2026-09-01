"""实体检索 API 集成测试（mock milvus / embedding / graph）。"""

from __future__ import annotations

import json
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from biz.dependencies.auth import require_platform_actor
from db_model.entity_search import EntitySearchState
from infra.workflow_mysql import get_workflow_session
from main import app
from service.platform_access import PlatformActor


class FakeNode:
    def __init__(self, node_id: str, props: dict[str, Any]) -> None:
        self.id = node_id
        self.labels = []
        self.properties = props


class FakeGraph:
    def labels(self) -> list[str]:
        return ["Expert"]

    def node_count(self, label: str | None = None) -> int:
        return 1

    def get_nodes_by_label(self, label: str, *, limit: int = 100, offset: int = 0):
        items = (
            [FakeNode("expert_1", {"id": "E-1", "name": "张三", "org": "中科院"})]
            if offset == 0
            else []
        )

        class Result:
            def __init__(self, rows):
                self.items = rows
                self.total = len(rows)

        return Result(items)


class FakeMilvus:
    def __init__(self) -> None:
        self.exists = False

    def has_collection(self, name: str) -> bool:
        return self.exists

    def drop_collection(self, name: str) -> None:
        pass

    def describe_collection(self, name: str) -> dict[str, Any]:
        return {"fields": [{"name": "graph_space"}]}

    def create_schema(self, **kwargs):
        class Schema:
            def add_field(self, *args, **kw):
                pass

        return Schema()

    def prepare_index_params(self):
        class IndexParams:
            def add_index(self, *args, **kw):
                pass

        return IndexParams()

    def create_collection(self, collection_name: str, **kwargs):
        self.exists = True

    def delete(self, collection_name: str, filter: str = "") -> None:  # noqa: A002
        pass

    def upsert(self, collection_name: str, data: list):
        pass

    def flush(self, collection_name: str):
        pass

    def load_collection(self, collection_name: str):
        pass


class FakeEmbedding:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), 1.0, 0.5] for text in texts]

    def embed_one(self, text: str) -> list[float]:
        return [float(len(text)), 1.0, 0.5]


@pytest.fixture
def entity_search_api(monkeypatch: pytest.MonkeyPatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    EntitySearchState.metadata.create_all(engine, tables=[EntitySearchState.__table__])

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_workflow_session] = override_session
    monkeypatch.setenv("ENTITY_SEARCH_EMBEDDING_DIM", "3")
    # 测试用 sqlite 会话：跳过对真实控制库的建表检查
    monkeypatch.setattr("service.entity_search._state_table_checked", True)

    # 默认 mock：无集合（未建索引）
    monkeypatch.setattr("service.entity_search.get_milvus_client", lambda: FakeMilvus())
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: FakeGraph())
    monkeypatch.setattr("service.entity_search._default_space", lambda: "dev2")
    monkeypatch.setattr("service.entity_search._node_count_cache", {})

    def set_actor(user_id: str, is_admin: bool) -> None:
        actor = PlatformActor(
            user_id=user_id,
            username=user_id,
            display_name=user_id,
            email=f"{user_id}@test",
            is_admin=is_admin,
        )
        app.dependency_overrides[require_platform_actor] = lambda: actor

    set_actor("user-a", False)
    yield engine, set_actor, monkeypatch
    app.dependency_overrides.pop(get_workflow_session, None)
    app.dependency_overrides.pop(require_platform_actor, None)
    engine.dispose()


@pytest.mark.asyncio
async def test_browse_default_view(entity_search_api) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/entity-search/entities")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["mode"] == "browse"
        assert data["total"] == 1
        assert data["limit"] == 10  # 默认每页 10
        item = data["items"][0]
        assert item["name"] == "张三"
        assert item["entityType"] == "Expert"
        assert item["properties"]["org"] == "中科院"
        assert item["score"] is None

        # 类型过滤
        filtered = await client.get(
            "/api/v1/entity-search/entities",
            params={"entityType": "Expert", "limit": 5, "offset": 0},
        )
        assert filtered.status_code == 200
        assert filtered.json()["data"]["items"][0]["vid"] == "expert_1"

        # 未知类型 → 400
        missing = await client.get("/api/v1/entity-search/entities", params={"entityType": "Nope"})
        assert missing.status_code == 400


@pytest.mark.asyncio
async def test_types_and_status_empty_state(entity_search_api) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        types = await client.get("/api/v1/entity-search/types")
        assert types.status_code == 200
        assert types.json()["data"] == {"items": []}

        status = await client.get("/api/v1/entity-search/index-status")
        assert status.status_code == 200
        data = status.json()["data"]
        assert data["indexed"] is False
        assert data["bm25Ready"] is False
        assert data["graphSpace"] == "dev2"


@pytest.mark.asyncio
async def test_search_validates_keyword(entity_search_api) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/entity-search/search",
            json={"keyword": "", "limit": 20, "offset": 0},
        )
        # 全局 validation handler：HTTP 200 + code=422
        assert response.status_code == 200
        assert response.json()["code"] == 422


@pytest.mark.asyncio
async def test_search_without_index_returns_400(entity_search_api) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/entity-search/search",
            json={"keyword": "张三"},
        )
        assert response.status_code == 400
        assert "尚未构建实体索引" in response.json()["detail"]


@pytest.mark.asyncio
async def test_reindex_requires_admin(entity_search_api) -> None:
    _, set_actor, _ = entity_search_api
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        set_actor("user-a", False)
        forbidden = await client.post("/api/v1/entity-search/reindex", json={})
        assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_reindex_and_search_full_flow(entity_search_api) -> None:
    _, set_actor, monkeypatch = entity_search_api

    milvus = FakeMilvus()
    monkeypatch.setattr("service.entity_search.get_milvus_client", lambda: milvus)
    monkeypatch.setattr("service.entity_search._embedding_client", lambda: FakeEmbedding())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        set_actor("admin-1", True)
        reindexed = await client.post("/api/v1/entity-search/reindex", json={})
        assert reindexed.status_code == 200
        assert reindexed.json()["data"]["entityCount"] == 1

        types = await client.get("/api/v1/entity-search/types")
        assert types.json()["data"]["items"] == [{"name": "Expert", "count": 1}]

        status = await client.get("/api/v1/entity-search/index-status")
        assert status.json()["data"]["indexed"] is True

        # search：mock _hybrid_search 返回一条命中
        def fake_hybrid_search(self, client_, *, dense_vector, sparse_vector, expr, limit):
            assert expr == 'graph_space == "dev2" and entity_type == "Expert"'
            return [
                {
                    "distance": 0.88,
                    "fields": {
                        "vid": "expert_1",
                        "entity_id": "E-1",
                        "name": "张三",
                        "entity_type": "Expert",
                        "properties": json.dumps({"org": "中科院"}, ensure_ascii=False),
                    },
                }
            ]

        from service.entity_search import EntitySearchService

        monkeypatch.setattr(EntitySearchService, "_hybrid_search", fake_hybrid_search)
        searched = await client.post(
            "/api/v1/entity-search/search",
            json={"keyword": "张三", "entityType": "Expert", "limit": 20, "offset": 0},
        )
        assert searched.status_code == 200
        data = searched.json()["data"]
        assert data["mode"] == "hybrid"
        assert data["returned"] == 1
        assert data["items"][0]["name"] == "张三"
        assert data["items"][0]["properties"] == {"org": "中科院"}
        assert data["graphSpace"] == "dev2"

        # 指定其他图空间搜索：无该空间的索引状态 → 400
        other_space = await client.post(
            "/api/v1/entity-search/search",
            json={"keyword": "张三", "space": "other"},
        )
        assert other_space.status_code == 400
        assert "other" in other_space.json()["detail"]
