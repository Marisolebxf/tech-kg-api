"""实体检索 service 单测：文本组装 / browse 分页 / reindex / 混合检索 / 状态读取。"""

from __future__ import annotations

import json
from types import SimpleNamespace
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
    def __init__(self, items: list[FakeNode], total: int | None = None) -> None:
        self.items = items
        self.total = len(items) if total is None else total


class FakeGraph:
    def __init__(
        self,
        labels: list[str],
        nodes: dict[str, list[FakeNode]],
        counts: dict[str, int] | None = None,
    ) -> None:
        self._labels = labels
        self._nodes = nodes
        for label, items in nodes.items():
            for node in items:
                node.labels = [label]
        self._counts = counts if counts is not None else {k: len(v) for k, v in nodes.items()}

    def labels(self) -> list[str]:
        return list(self._labels)

    def get_node(self, node_id: str):
        return next(
            (node for nodes in self._nodes.values() for node in nodes if node.id == node_id), None
        )

    def list_indexes(self, label=None):
        return []

    def node_count(self, label: str | None = None) -> int:
        return self._counts.get(label or "", 0)

    def get_nodes_by_label(
        self, label: str, *, limit: int = 100, offset: int = 0
    ) -> FakePagedResult:
        items = self._nodes.get(label, [])
        return FakePagedResult(items[offset : offset + limit], total=len(items))


class FakeMilvusClient:
    def __init__(self) -> None:
        self.collections: dict[str, list[dict[str, Any]]] = {}
        self.deleted: list[str] = []

    def has_collection(self, name: str) -> bool:
        return name in self.collections

    def drop_collection(self, name: str) -> None:
        self.collections.pop(name, None)

    def describe_collection(self, name: str) -> dict[str, Any]:
        return {"fields": [{"name": "document_id"}, {"name": "graph_space"}]}

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
        rows = self.collections.get(collection_name, [])
        if 'graph_space == "' in filter:
            space = filter.split('graph_space == "', 1)[1].split('"', 1)[0]
            self.collections[collection_name] = [
                row for row in rows if row.get("graph_space") != space
            ]

    def upsert(self, collection_name: str, data: list[dict[str, Any]]):
        rows = self.collections[collection_name]
        by_id = {row["document_id"]: row for row in rows}
        by_id.update({row["document_id"]: row for row in data})
        self.collections[collection_name] = list(by_id.values())

    def flush(self, collection_name: str):
        pass

    def load_collection(self, collection_name: str):
        pass

    def query(
        self,
        collection_name: str,
        filter: str = "",  # noqa: A002
        output_fields: list[str] | None = None,
        limit: int = 10,
    ):
        rows = self.collections.get(collection_name, [])
        if 'graph_space == "' in filter:
            space = filter.split('graph_space == "', 1)[1].split('"', 1)[0]
            rows = [row for row in rows if row.get("graph_space") == space]
        return rows[:limit]


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
    assert extract_entity_name({"project_name": "项目甲"}, "v1") == "项目甲"
    assert extract_entity_name({"patent_title": "专利乙"}, "v1") == "专利乙"


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


def test_browse_single_type_reuses_page_total_without_node_count(
    state_session, monkeypatch
) -> None:
    graph = FakeGraph(
        ["Expert"],
        {
            "Expert": [
                FakeNode("expert_1", {"name": "张三"}),
                FakeNode("expert_2", {"name": "李四"}),
            ]
        },
    )

    def fail_node_count(label=None):
        raise AssertionError("单类型浏览不应再额外调用 node_count")

    graph.node_count = fail_node_count
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr("service.entity_search._default_space", lambda: "dev2")

    result = EntitySearchService(state_session).browse(entity_type="Expert", limit=1, offset=1)

    assert result["total"] == 2
    assert [item["vid"] for item in result["items"]] == ["expert_2"]


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


def test_browse_cross_type_uses_complete_state_counts(state_session, monkeypatch) -> None:
    graph = FakeGraph(
        ["A", "B", "C"],
        {
            "A": [FakeNode("a_1", {"name": "A1"})],
            "B": [
                FakeNode("b_2", {"name": "B2"}),
                FakeNode("b_1", {"name": "B1"}),
            ],
            "C": [FakeNode("c_1", {"name": "C1"})],
        },
    )

    def fail_node_count(label=None):
        raise AssertionError("完整统计快照存在时不应调用 node_count")

    graph.node_count = fail_node_count
    state_session.add(
        EntitySearchState(
            graph_space="dev2",
            entity_count=4,
            type_counts=json.dumps({"A": 1, "B": 2, "C": 1}),
        )
    )
    state_session.commit()
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr("service.entity_search._default_space", lambda: "dev2")

    result = EntitySearchService(state_session).browse(limit=2, offset=2)

    assert result["total"] == 4
    assert [item["vid"] for item in result["items"]] == ["b_1", "c_1"]


def test_browse_cross_type_incomplete_state_falls_back_to_live_counts(
    state_session, monkeypatch
) -> None:
    graph = FakeGraph(
        ["A", "B"],
        {
            "A": [FakeNode("a_1", {"name": "A1"})],
            "B": [FakeNode("b_1", {"name": "B1"})],
        },
    )
    calls: list[str | None] = []
    original_node_count = graph.node_count

    def track_node_count(label=None):
        calls.append(label)
        return original_node_count(label)

    graph.node_count = track_node_count
    state_session.add(
        EntitySearchState(
            graph_space="dev2",
            entity_count=1,
            type_counts=json.dumps({"A": 1}),
        )
    )
    state_session.commit()
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr("service.entity_search._default_space", lambda: "dev2")
    monkeypatch.setattr("service.entity_search._node_count_cache", {})

    result = EntitySearchService(state_session).browse(limit=10, offset=0)

    assert result["total"] == 2
    assert calls == ["A", "B"]


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
    assert expert_row["document_id"] == "dev2::expert_1"
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


def test_reindex_entity_type_hint_still_builds_complete_bm25_snapshot(
    state_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """兼容的 entity_types 参数不能删除同空间其他类型或生成局部 BM25 词表。"""
    graph = FakeGraph(
        ["Expert", "Paper"],
        {
            "Expert": [FakeNode("expert_1", {"name": "张三", "org": "中科院"})],
            "Paper": [FakeNode("paper_1", {"title": "知识图谱", "source": "期刊"})],
        },
    )
    milvus = FakeMilvusClient()
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr("service.entity_search.get_milvus_client", lambda: milvus)
    monkeypatch.setattr("service.entity_search._embedding_client", FakeEmbeddingClient)

    result = EntitySearchService(state_session).reindex(space="dev2", entity_types=["Expert"])

    assert result["typeCounts"] == {"Expert": 1, "Paper": 1}
    assert {row["entity_type"] for row in milvus.collections[COLLECTION_NAME]} == {
        "Expert",
        "Paper",
    }


def test_reindex_same_vid_in_two_spaces_keeps_both_documents(
    state_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """共享集合主键包含图空间，跨空间相同 VID 不得相互覆盖。"""
    graphs = {
        "dev": FakeGraph(["Expert"], {"Expert": [FakeNode("same_vid", {"name": "开发空间专家"})]}),
        "dev2": FakeGraph(["Expert"], {"Expert": [FakeNode("same_vid", {"name": "测试空间专家"})]}),
    }
    milvus = FakeMilvusClient()
    monkeypatch.setattr("service.entity_search.get_space_client", graphs.__getitem__)
    monkeypatch.setattr("service.entity_search.get_milvus_client", lambda: milvus)
    monkeypatch.setattr("service.entity_search._embedding_client", FakeEmbeddingClient)

    service = EntitySearchService(state_session)
    service.reindex(space="dev")
    service.reindex(space="dev2")

    rows = milvus.collections[COLLECTION_NAME]
    assert {row["document_id"] for row in rows} == {"dev::same_vid", "dev2::same_vid"}
    assert {(row["graph_space"], row["name"]) for row in rows} == {
        ("dev", "开发空间专家"),
        ("dev2", "测试空间专家"),
    }


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


def test_search_finds_scalar_property_keyword(
    state_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """普通标量属性应进入全量 BM25 快照，并能通过属性关键词返回目标实体。"""
    graph = FakeGraph(
        ["DataSource"],
        {
            "DataSource": [
                FakeNode(
                    "ds_dwd_bid_base_out",
                    {
                        "source_table": "dwd_bid_base_out",
                        "table_cn_name": "招投标公告基础表",
                        "library": "国内机构要素库",
                    },
                )
            ]
        },
    )
    milvus = FakeMilvusClient()
    embedding = FakeEmbeddingClient()
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr("service.entity_search.get_milvus_client", lambda: milvus)
    monkeypatch.setattr("service.entity_search._embedding_client", lambda: embedding)

    service = EntitySearchService(state_session)
    service.reindex(space="dev2")
    indexed_row = milvus.collections[COLLECTION_NAME][0]
    assert "library 国内机构要素库" in indexed_row["search_text"]

    def fake_hybrid_search(self, client, *, dense_vector, sparse_vector, expr, limit):
        assert dense_vector is not None
        assert sparse_vector
        assert expr == 'graph_space == "dev2"'
        return [
            {
                "distance": 0.99,
                "fields": {
                    "vid": indexed_row["vid"],
                    "entity_id": indexed_row["entity_id"],
                    "name": indexed_row["name"],
                    "entity_type": indexed_row["entity_type"],
                    "properties": indexed_row["properties"],
                },
            }
        ]

    monkeypatch.setattr(EntitySearchService, "_hybrid_search", fake_hybrid_search)
    result = service.search(keyword="国内机构要素库", space="dev2")

    assert result["returned"] == 1
    assert result["items"][0]["vid"] == "ds_dwd_bid_base_out"
    assert result["items"][0]["properties"]["library"] == "国内机构要素库"


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
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: FakeGraph([], {}))
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


def test_search_graph_vid_works_without_milvus(state_session, monkeypatch):
    node = FakeNode("ds_dwd_bid_target_item_out", {})
    graph = FakeGraph(["DataSource"], {"DataSource": [node]})
    spaces = []

    def get_graph(space):
        spaces.append(space)
        return graph

    def no_milvus():
        pytest.fail("VID 精确命中不应连接 Milvus 或 embedding")

    monkeypatch.setattr("service.entity_search.get_space_client", get_graph)
    monkeypatch.setattr("service.entity_search.get_milvus_client", no_milvus)
    monkeypatch.setattr("service.entity_search._embedding_client", no_milvus)
    result = EntitySearchService(state_session).search(keyword=node.id, space="dev2")
    assert result["mode"] == "graph-exact"
    assert result["items"][0]["name"] == node.id
    assert result["items"][0]["entityType"] == "DataSource"
    assert spaces == ["dev2"]


def test_search_exact_indexed_name_deduplicates_before_pagination(state_session, monkeypatch):
    nodes = [
        FakeNode("v2", {"name": "同名", "id": "同名"}),
        FakeNode("v1", {"name": "同名", "id": "同名"}),
    ]
    graph = FakeGraph(["Expert"], {"Expert": nodes})
    graph.list_indexes = lambda label: [
        SimpleNamespace(label="Expert", properties=["name"]),
        SimpleNamespace(label="Expert", properties=["id"]),
        SimpleNamespace(label="Expert", properties=["name"]),
        SimpleNamespace(label="Paper", properties=["name"]),
        SimpleNamespace(label="Expert", properties=["other", "name"]),
    ]
    calls = []

    def find_nodes(labels, properties, *, limit, offset):
        calls.append((labels, properties, limit, offset))
        return FakePagedResult(nodes)

    graph.find_nodes = find_nodes
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    service = EntitySearchService(state_session)
    pages = [
        service.search(keyword="同名", space="dev2", entity_type="Expert", limit=1, offset=i)
        for i in range(3)
    ]
    assert [[item["vid"] for item in page["items"]] for page in pages] == [["v1"], ["v2"], []]
    assert [page["total"] for page in pages] == [2, 2, 2]
    assert len(calls) == 6  # 每次只查 name/id 首列索引；重复索引及其他类型排除
    assert all(call[0] == ["Expert"] and call[2:] == (500, 0) for call in calls)


def test_search_vid_respects_type_filter(state_session, monkeypatch):
    graph = FakeGraph(["Paper"], {"Paper": [FakeNode("same-id", {"name": "论文"})]})
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr("service.entity_search.get_milvus_client", FakeMilvusClient)
    with pytest.raises(EntitySearchError, match="尚未构建实体索引"):
        EntitySearchService(state_session).search(
            keyword="same-id", space="dev2", entity_type="Expert"
        )


def test_search_exact_id_survives_index_metadata_failure(state_session, monkeypatch):
    graph = FakeGraph(["Expert"], {"Expert": [FakeNode("E-1", {"name": "姓名"})]})

    def failed_indexes(label):
        raise RuntimeError("metadata unavailable")

    graph.list_indexes = failed_indexes
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    result = EntitySearchService(state_session).search(keyword="E-1", space="dev2")
    assert result["items"][0]["vid"] == "E-1"


def test_search_exact_matches_survive_individual_index_failure(state_session, monkeypatch):
    graph = FakeGraph(["Expert"], {"Expert": [FakeNode("E-1", {"name": "姓名"})]})
    graph.list_indexes = lambda label: [
        SimpleNamespace(label="Expert", properties=["id"]),
        SimpleNamespace(label="Expert", properties=["name"]),
    ]

    def find_nodes(labels, properties, *, limit, offset):
        if "id" in properties:
            raise RuntimeError("one index unavailable")
        return FakePagedResult([FakeNode("E-2", {"name": "E-1"})])

    graph.find_nodes = find_nodes
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    result = EntitySearchService(state_session).search(keyword="E-1", space="dev2")
    assert [item["vid"] for item in result["items"]] == ["E-1", "E-2"]
    assert result["total"] == 2


def test_search_failed_exact_query_does_not_report_no_matches(state_session, monkeypatch):
    graph = FakeGraph([], {})
    graph.list_indexes = lambda label: [SimpleNamespace(label="Expert", properties=["name"])]

    def find_nodes(*args, **kwargs):
        raise RuntimeError("index unavailable")

    graph.find_nodes = find_nodes
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr(EntitySearchService, "_search_index", lambda self, **kwargs: {"items": []})
    with pytest.raises(EntitySearchError, match="图库精确检索暂不可用"):
        EntitySearchService(state_session).search(keyword="姓名", space="dev2")


def test_status_marks_stale_state_when_space_missing_in_milvus(state_session, monkeypatch):
    milvus = FakeMilvusClient()
    milvus.collections[COLLECTION_NAME] = [
        {
            "vid": "other-1",
            "graph_space": "gaoxing_test",
            "entity_type": "Program",
        }
    ]
    state_session.add(
        EntitySearchState(
            graph_space="dev2",
            entity_count=4,
            document_count=4,
            vocabulary='{"x":0}',
            document_frequency='{"x":4}',
            type_counts='{"E2EBigWidget":4}',
            embedding_model="moka-ai/m3e-small",
        )
    )
    state_session.commit()
    monkeypatch.setattr("service.entity_search.get_milvus_client", lambda: milvus)
    monkeypatch.setattr("service.entity_search._default_space", lambda: "dev2")

    service = EntitySearchService(state_session)
    status = service.status()

    assert status["indexed"] is False
    assert status["actualDataAvailable"] is False
    assert status["stateStale"] is True
    assert status["entityCount"] == 0
    assert status["recordedEntityCount"] == 4
    assert status["typeCounts"] == {}
    assert status["recordedTypeCounts"] == {"E2EBigWidget": 4}
    assert status["bm25Ready"] is False
    assert service.types() == []


def test_status_marks_milvus_unreachable_as_explicit_degradation(state_session, monkeypatch):
    state_session.add(EntitySearchState(graph_space="dev2", entity_count=4))
    state_session.commit()

    def unavailable():
        raise RuntimeError("connection refused")

    monkeypatch.setattr("service.entity_search.get_milvus_client", unavailable)
    monkeypatch.setattr("service.entity_search._default_space", lambda: "dev2")

    status = EntitySearchService(state_session).status()

    assert status["milvusReachable"] is False
    assert status["actualDataAvailable"] is False
    assert status["indexed"] is False
    assert status["entityCount"] == 0
    assert status["stateStale"] is True


def test_search_milvus_unreachable_reports_exact_query_degradation(state_session, monkeypatch):
    state_session.add(EntitySearchState(graph_space="dev2", entity_count=4))
    state_session.commit()
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: FakeGraph([], {}))

    def unavailable():
        raise RuntimeError("connection refused")

    monkeypatch.setattr("service.entity_search.get_milvus_client", unavailable)

    with pytest.raises(EntitySearchError, match="已降级为.*精确查询"):
        EntitySearchService(state_session).search(keyword="不存在", space="dev2")


def test_search_stale_milvus_state_keeps_graph_exact_fallback(
    state_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph = FakeGraph(
        ["DataSource"],
        {"DataSource": [FakeNode("ds_dwd_bid_target_item_out", {})]},
    )
    milvus = FakeMilvusClient()
    milvus.collections[COLLECTION_NAME] = [
        {"vid": "other-1", "graph_space": "gaoxing_test", "entity_type": "Program"}
    ]
    state_session.add(
        EntitySearchState(
            graph_space="dev2",
            entity_count=4,
            document_count=4,
            vocabulary='{"x":0}',
            document_frequency='{"x":4}',
            type_counts='{"E2EBigWidget":4}',
            embedding_model="moka-ai/m3e-small",
        )
    )
    state_session.commit()
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr("service.entity_search.get_milvus_client", lambda: milvus)

    service = EntitySearchService(state_session)
    exact = service.search(keyword="ds_dwd_bid_target_item_out", space="dev2")

    assert exact["mode"] == "graph-exact"
    assert exact["returned"] == 1
    assert exact["items"][0]["entityType"] == "DataSource"

    with pytest.raises(EntitySearchError, match="索引状态已过期"):
        service.search(keyword="不存在的语义关键词", space="dev2")
