"""实体检索 service 单测：文本组装 / browse 分页 / reindex / 混合检索 / 状态读取。"""

from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from db_model.entity_search import EntitySearchState
from service.entity_search import (
    COLLECTION_NAME,
    EntitySearchError,
    EntitySearchService,
    compose_entity_text,
    extract_display_properties,
    extract_entity_name,
)


class FakeNode:
    def __init__(self, node_id: str, props: dict[str, Any]) -> None:
        self.id = node_id
        self.labels = []
        self.properties = props


class FakePagedResult:
    def __init__(self, items: list[FakeNode]) -> None:
        self.items = items
        self.total = len(items)


class FakeGraph:
    def __init__(
        self,
        labels: list[str],
        nodes: dict[str, list[FakeNode]],
        counts: dict[str, int] | None = None,
    ) -> None:
        self._labels = labels
        self._nodes = nodes
        self._counts = counts if counts is not None else {k: len(v) for k, v in nodes.items()}

    def labels(self) -> list[str]:
        return list(self._labels)

    def node_count(self, label: str | None = None) -> int:
        return self._counts.get(label or "", 0)

    def get_nodes_by_label(
        self, label: str, *, limit: int = 100, offset: int = 0
    ) -> FakePagedResult:
        items = self._nodes.get(label, [])
        return FakePagedResult(items[offset : offset + limit])


class FakeMilvusClient:
    def __init__(self) -> None:
        self.collections: dict[str, list[dict[str, Any]]] = {}
        self.deleted: list[str] = []

    def has_collection(self, name: str) -> bool:
        return name in self.collections

    def drop_collection(self, name: str) -> None:
        self.collections.pop(name, None)

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
        self.collections[collection_name] = []
        self.created = collection_name  # noqa: A003

    def delete(self, collection_name: str, filter: str = "") -> None:  # noqa: A002
        self.deleted.append(filter)

    def upsert(self, collection_name: str, data: list[dict[str, Any]]):
        self.collections[collection_name].extend(data)

    def flush(self, collection_name: str):
        pass

    def load_collection(self, collection_name: str):
        pass


class FakeEmbeddingClient:
    def __init__(self) -> None:
        self.embedded: list[str] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.embedded.extend(texts)
        return [[float(len(text)), 1.0, 0.5] for text in texts]

    def embed_one(self, text: str) -> list[float]:
        self.embedded.append(text)
        return [float(len(text)), 1.0, 0.5]


@pytest.fixture
def state_session(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENTITY_SEARCH_EMBEDDING_DIM", "3")  # 与 FakeEmbeddingClient 维度一致
    # 单测用 sqlite 会话：跳过对真实控制库的建表检查
    monkeypatch.setattr("service.entity_search._state_table_checked", True)
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    EntitySearchState.metadata.create_all(engine, tables=[EntitySearchState.__table__])
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_extract_entity_name_candidates() -> None:
    assert extract_entity_name({"name": "张三"}, "v1") == "张三"
    assert extract_entity_name({"title": "论文A"}, "v1") == "论文A"
    assert extract_entity_name({"other": "x"}, "fallback-vid") == "fallback-vid"
    assert extract_entity_name({"name": "  ", "name_zh": "中文名"}, "v1") == "中文名"


def test_extract_display_properties_filters_and_truncates() -> None:
    props = {
        "id": "E-1",
        "name": "张三",
        "tags": ["a", "b"],  # 非标量 → 剔除
        "none": None,
        "empty": "",
        "long": "x" * 1024,
    }
    display = extract_display_properties(props)
    assert display["id"] == "E-1"
    assert "tags" not in display and "none" not in display and "empty" not in display
    assert len(display["long"]) == 513  # 512 + …


def test_compose_entity_text() -> None:
    text = compose_entity_text("张三", "Expert", {"id": "E-1", "org": "中科院"})
    assert "张三" in text and "Expert" in text and "id E-1" in text and "org 中科院" in text


def test_browse_single_type_pagination(state_session, monkeypatch) -> None:
    graph = FakeGraph(
        ["Expert"],
        {
            "Expert": [
                FakeNode("expert_c", {"id": "E-3", "name": "王五"}),
                FakeNode("expert_a", {"id": "E-1", "name": "张三"}),
                FakeNode("expert_b", {"id": "E-2", "name": "李四"}),
            ]
        },
    )
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr("service.entity_search._default_space", lambda: "dev2")
    monkeypatch.setattr("service.entity_search._node_count_cache", {})

    service = EntitySearchService(state_session)
    result = service.browse(entity_type="Expert", limit=2, offset=0)
    assert result["mode"] == "browse"
    assert result["total"] == 3
    # 分页边界按图返回序，页内按 vid 排序展示
    assert [item["vid"] for item in result["items"]] == ["expert_a", "expert_c"]
    result = service.browse(entity_type="Expert", limit=2, offset=2)
    assert [item["vid"] for item in result["items"]] == ["expert_b"]


def test_browse_cross_type_window_fetches_only_needed_labels(state_session, monkeypatch) -> None:
    graph = FakeGraph(
        ["A", "B", "C"],
        {
            "A": [FakeNode("a_1", {"id": "1", "name": "A1"})],
            "B": [
                FakeNode("b_2", {"id": "2", "name": "B2"}),
                FakeNode("b_1", {"id": "3", "name": "B1"}),
            ],
            "C": [FakeNode("c_1", {"id": "4", "name": "C1"})],
        },
    )
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr("service.entity_search._default_space", lambda: "dev2")
    monkeypatch.setattr("service.entity_search._node_count_cache", {})

    service = EntitySearchService(state_session)
    # 全局顺序：A(1) B(2) C(1) → a_1, b_2, b_1, c_1
    # 第 2 页（每页 2）：窗口 [2,4) 只落在标签 B 的第 2 条 + 标签 C
    result = service.browse(limit=2, offset=2)
    assert result["total"] == 4
    assert [item["vid"] for item in result["items"]] == ["b_1", "c_1"]
    # 超出总数 → 空页
    result = service.browse(limit=2, offset=4)
    assert result["items"] == []


def test_browse_unknown_type(state_session, monkeypatch) -> None:
    graph = FakeGraph(["Expert"], {})
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    service = EntitySearchService(state_session)
    with pytest.raises(EntitySearchError, match="不存在实体类型"):
        service.browse(entity_type="Nope")


def test_reindex_builds_collection_and_state(
    state_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph = FakeGraph(
        ["Expert", "Paper"],
        {
            "Expert": [FakeNode("expert_1", {"id": "E-1", "name": "张三", "org": "中科院"})],
            "Paper": [
                FakeNode("paper_1", {"id": "P-1", "title": "深度学习综述"}),
                FakeNode("paper_2", {"id": "P-2", "title": "知识图谱构建"}),
            ],
        },
    )
    milvus = FakeMilvusClient()
    embedding = FakeEmbeddingClient()
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr("service.entity_search.get_milvus_client", lambda: milvus)
    monkeypatch.setattr("service.entity_search._embedding_client", lambda: embedding)
    monkeypatch.setattr("service.entity_search._default_space", lambda: "dev2")

    service = EntitySearchService(state_session)
    result = service.reindex()

    assert result["entityCount"] == 3
    assert result["typeCounts"] == {"Expert": 1, "Paper": 2}
    assert result["graphSpace"] == "dev2"
    assert COLLECTION_NAME in milvus.collections
    assert milvus.deleted == ['graph_space == "dev2"']  # 按空间覆盖旧数据
    rows = milvus.collections[COLLECTION_NAME]
    assert len(rows) == 3
    expert_row = next(row for row in rows if row["entity_type"] == "Expert")
    assert expert_row["name"] == "张三"
    assert expert_row["entity_id"] == "E-1"
    assert expert_row["graph_space"] == "dev2"
    assert json.loads(expert_row["properties"])["org"] == "中科院"
    assert len(expert_row["dense_vector"]) == 3
    assert expert_row["sparse_vector"]  # BM25 已编码

    # 状态行持久化 → types/status 可读
    types = service.types()
    assert types == [
        {"name": "Paper", "count": 2},
        {"name": "Expert", "count": 1},
    ]
    status = service.status()
    assert status["indexed"] is True
    assert status["entityCount"] == 3
    assert status["bm25Ready"] is True
    assert status["graphSpace"] == "dev2"


def test_reindex_unknown_entity_type_raises(state_session, monkeypatch) -> None:
    graph = FakeGraph(["Expert"], {})
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    service = EntitySearchService(state_session)
    with pytest.raises(EntitySearchError, match="不存在这些实体类型"):
        service.reindex(entity_types=["Nope"])


def test_reindex_embedding_failure_keeps_collection(
    state_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph = FakeGraph(["Expert"], {"Expert": [FakeNode("expert_1", {"id": "E-1", "name": "张三"})]})
    milvus = FakeMilvusClient()

    class BrokenEmbedding:
        def embed(self, texts):
            return None

    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr("service.entity_search.get_milvus_client", lambda: milvus)
    monkeypatch.setattr("service.entity_search._embedding_client", lambda: BrokenEmbedding())
    monkeypatch.setattr("service.entity_search._default_space", lambda: "dev2")

    service = EntitySearchService(state_session)
    with pytest.raises(EntitySearchError, match="embedding 服务调用失败"):
        service.reindex()
    assert COLLECTION_NAME not in milvus.collections


def test_search_hybrid_with_type_filter(state_session, monkeypatch: pytest.MonkeyPatch) -> None:
    milvus = FakeMilvusClient()
    milvus.collections[COLLECTION_NAME] = []

    def fake_hybrid_search(self, client, *, dense_vector, sparse_vector, expr, limit):
        assert dense_vector is not None
        assert sparse_vector  # BM25 状态在 reindex 里写入
        assert expr == 'graph_space == "dev2" and entity_type == "Expert"'
        return [
            {
                "distance": 0.9,
                "fields": {
                    "vid": "expert_1",
                    "entity_id": "E-1",
                    "name": "张三",
                    "entity_type": "Expert",
                    "properties": json.dumps({"org": "中科院"}, ensure_ascii=False),
                },
            }
        ]

    embedding = FakeEmbeddingClient()
    monkeypatch.setattr("service.entity_search.get_milvus_client", lambda: milvus)
    monkeypatch.setattr("service.entity_search._embedding_client", lambda: embedding)
    monkeypatch.setattr(EntitySearchService, "_hybrid_search", fake_hybrid_search)

    # 先 reindex 写 BM25 状态
    graph = FakeGraph(["Expert"], {"Expert": [FakeNode("expert_1", {"id": "E-1", "name": "张三"})]})
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr("service.entity_search._default_space", lambda: "dev2")
    service = EntitySearchService(state_session)
    service.reindex()

    result = service.search(keyword="张三", entity_type="Expert", limit=20, offset=10)
    assert result["mode"] == "hybrid"
    assert result["offset"] == 10
    assert result["returned"] == 0  # 窗口切片：offset 10 超出命中数

    result = service.search(keyword="张三", entity_type="Expert", limit=20, offset=0)
    assert result["returned"] == 1
    item = result["items"][0]
    assert item["name"] == "张三"
    assert item["properties"] == {"org": "中科院"}
    assert item["entityType"] == "Expert"
    assert result["graphSpace"] == "dev2"


def test_search_requires_keyword(state_session) -> None:
    service = EntitySearchService(state_session)
    with pytest.raises(EntitySearchError, match="关键词不能为空"):
        service.search(keyword="   ")


def test_search_without_collection_raises(state_session, monkeypatch) -> None:
    milvus = FakeMilvusClient()

    class NoEmbed:
        def embed_one(self, text):
            return [0.1]

    monkeypatch.setattr("service.entity_search.get_milvus_client", lambda: milvus)
    monkeypatch.setattr("service.entity_search._embedding_client", lambda: NoEmbed())
    monkeypatch.setattr("service.entity_search._default_space", lambda: "dev2")
    service = EntitySearchService(state_session)
    with pytest.raises(EntitySearchError, match="尚未构建实体索引"):
        service.search(keyword="x")


def test_status_empty_state(state_session, monkeypatch) -> None:
    milvus = FakeMilvusClient()
    monkeypatch.setattr("service.entity_search.get_milvus_client", lambda: milvus)
    monkeypatch.setattr("service.entity_search._default_space", lambda: "dev2")
    service = EntitySearchService(state_session)
    status = service.status()
    assert status["indexed"] is False
    assert status["types"] == []
    assert status["bm25Ready"] is False
    assert service.types() == []
