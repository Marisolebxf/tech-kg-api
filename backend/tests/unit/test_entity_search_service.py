"""实体检索 service 单测：文本组装 / browse 分页 / reindex / 混合检索 / 状态读取。"""

from __future__ import annotations

import json
import os
import re
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from db_model.entity_search import EntitySearchState
from infra.graph_db.exceptions import GraphRequestError
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
        self.dropped: list[str] = []
        self.schema_fields: list[dict[str, Any]] = []
        # 可注入的集合描述（默认视为现行 schema、无维度信息）
        self.describe_fields: list[dict[str, Any]] | None = None

    def has_collection(self, name: str) -> bool:
        return name in self.collections

    def drop_collection(self, name: str) -> None:
        self.collections.pop(name, None)
        self.dropped.append(name)

    def describe_collection(self, name: str) -> dict[str, Any]:
        if self.describe_fields is not None:
            return {"fields": self.describe_fields}
        return {"fields": [{"name": "document_id"}, {"name": "graph_space"}]}

    def create_schema(self, **kwargs):
        client = self

        class Schema:
            def add_field(self, *args, **kw):
                client.schema_fields.append({"name": args[0] if args else None, **kw})

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


@pytest.fixture(autouse=True)
def _hermetic_embedding_config(monkeypatch: pytest.MonkeyPatch):
    """固定 embedding 配置解析：单测不触达配置管理 DB，也不依赖宿主环境变量。

    维度跟随 ENTITY_SEARCH_EMBEDDING_DIM（state_session 设为 3，与 FakeEmbeddingClient
    返回的 3 维向量一致）；个别用例可再次 monkeypatch 覆盖为 None / 抛未配置。
    """
    monkeypatch.setattr(
        "service.entity_search._resolve_embedding_config",
        lambda: {
            "base_url": "http://embedding.test",
            "model": "m3e-test",
            "api_key": "test-key",
            "dim": int(os.environ.get("ENTITY_SEARCH_EMBEDDING_DIM", "3")),
            "config_id": None,
        },
    )


def test_extract_entity_name_candidates() -> None:
    assert extract_entity_name({"name": "张三"}, "v1") == "张三"
    assert extract_entity_name({"title": "论文A"}, "v1") == "论文A"
    assert extract_entity_name({"other": "x"}, "fallback-vid") == "fallback-vid"
    assert extract_entity_name({"name": "  ", "name_zh": "中文名"}, "v1") == "中文名"
    assert extract_entity_name({"project_name": "项目甲"}, "v1") == "项目甲"
    assert extract_entity_name({"patent_title": "专利乙"}, "v1") == "专利乙"


def test_extract_display_properties_serializes_complex_values_and_truncates() -> None:
    props = {
        "id": "E-1",
        "name": "张三",
        "tags": ["a", "b"],
        "none": None,
        "empty": "",
        "long": "x" * 1024,
    }
    display = extract_display_properties(props)
    assert display["id"] == "E-1"
    assert display["tags"] == '["a","b"]'
    assert "none" not in display and "empty" not in display
    assert len(display["long"]) == 513  # 512 + …


def test_compose_entity_text() -> None:
    text = compose_entity_text("张三", "Expert", {"id": "E-1", "org": "中科院"})
    assert "张三" in text and "Expert" in text and "id E-1" in text and "org 中科院" in text


def test_compose_entity_text_flattens_json_and_collection_properties() -> None:
    text = compose_entity_text(
        "专利A",
        "Patent",
        {
            "keywords": ["人工智能", {"zhName": "知识图谱"}],
            "classifications": '[{"code":"G06F","name":"数据处理"}]',
        },
    )

    assert "keywords 人工智能 zhName 知识图谱" in text
    assert "classifications code G06F name 数据处理" in text


def test_compose_entity_text_keeps_long_value_tail_and_late_property() -> None:
    props = {f"field_{index}": "值" * 300 for index in range(40)}
    props["abstract"] = "开头" + "x" * 3000 + "尾部目标词"
    props["last_field"] = "国内机构要素库"

    text = compose_entity_text("实体A", "DataSource", props)

    assert "尾部目标词" in text
    assert "last_field 国内机构要素库" in text


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


def test_reindex_streams_graph_and_embedding_in_bounded_batches(
    state_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph = FakeGraph(
        ["Expert"],
        {"Expert": [FakeNode(f"expert_{index}", {"name": f"专家{index}"}) for index in range(5)]},
    )
    graph_reads = 0
    original_get_nodes = graph.get_nodes_by_label

    def counted_get_nodes(label, *, limit=100, offset=0):
        nonlocal graph_reads
        graph_reads += 1
        return original_get_nodes(label, limit=limit, offset=offset)

    graph.get_nodes_by_label = counted_get_nodes
    milvus = FakeMilvusClient()

    class BoundedEmbedding:
        def __init__(self) -> None:
            self.batch_sizes: list[int] = []

        def embed(self, texts):
            self.batch_sizes.append(len(texts))
            return [[1.0, 0.5, 0.25] for _ in texts]

    embedding = BoundedEmbedding()
    monkeypatch.setattr("service.entity_search.EMBED_BATCH_SIZE", 2)
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr("service.entity_search.get_milvus_client", lambda: milvus)
    monkeypatch.setattr("service.entity_search._embedding_client", lambda: embedding)

    result = EntitySearchService(state_session).reindex(space="dev2")

    assert result["entityCount"] == 5
    assert embedding.batch_sizes == [2, 2, 1]
    assert graph_reads == 2  # BM25 统计一遍，流式写入一遍
    assert len(milvus.collections[COLLECTION_NAME]) == 5


class LookupGraph(FakeGraph):
    """execute_query 可用：有索引标签走 LOOKUP 分页，无索引标签回退 REST。"""

    def __init__(self, labels, nodes, lookup_labels):
        super().__init__(labels, nodes)
        self._lookup_labels = set(lookup_labels)
        self.rest_reads: list[str] = []
        self.lookup_reads: list[str] = []

    def execute_query(self, query: str):
        label = query.split("`")[1]
        if label not in self._lookup_labels:
            raise GraphRequestError(f"no index on {label}", status_code=500)
        match = re.search(r"LIMIT (\d+)(?: OFFSET (\d+))?", query)
        assert match is not None
        limit = int(match.group(1))
        offset = int(match.group(2) or 0)
        page = self._nodes.get(label, [])[offset : offset + limit]
        self.lookup_reads.append(label)
        return SimpleNamespace(
            records=[
                {"v": {"id": node.id, "labels": node.labels, "properties": node.properties}}
                for node in page
            ]
        )

    def get_nodes_by_label(self, label: str, *, limit: int = 100, offset: int = 0):
        self.rest_reads.append(label)
        return super().get_nodes_by_label(label, limit=limit, offset=offset)


def test_reindex_prefers_lookup_pagination_for_indexed_labels(
    state_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph = LookupGraph(
        ["Expert", "Paper"],
        {
            "Expert": [
                FakeNode("expert_1", {"id": "E-1", "name": "张三"}),
                FakeNode("expert_2", {"id": "E-2", "name": "李四"}),
            ],
            "Paper": [FakeNode("paper_1", {"id": "P-1", "title": "深度学习综述"})],
        },
        lookup_labels={"Expert"},
    )
    milvus = FakeMilvusClient()
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr("service.entity_search.get_milvus_client", lambda: milvus)
    monkeypatch.setattr("service.entity_search._embedding_client", FakeEmbeddingClient)
    monkeypatch.setattr("service.entity_search._default_space", lambda: "dev2")

    result = EntitySearchService(state_session).reindex()

    assert result["entityCount"] == 3
    assert result["typeCounts"] == {"Expert": 2, "Paper": 1}
    assert result["skippedLabels"] == []
    # 有索引标签两次遍历全走 LOOKUP；REST 只服务无索引标签
    assert set(graph.lookup_reads) == {"Expert"}
    assert set(graph.rest_reads) == {"Paper"}
    assert len(milvus.collections[COLLECTION_NAME]) == 3
    expert_row = next(
        row for row in milvus.collections[COLLECTION_NAME] if row["vid"] == "expert_1"
    )
    assert expert_row["name"] == "张三" and expert_row["entity_id"] == "E-1"


def test_reindex_skips_big_label_when_lookup_and_rest_both_fail(
    state_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph = LookupGraph(
        ["Expert", "Paper"],
        {
            "Expert": [FakeNode("expert_1", {"id": "E-1", "name": "张三"})],
            "Paper": [FakeNode("paper_1", {"id": "P-1", "title": "深度学习综述"})],
        },
        lookup_labels={"Expert"},
    )

    def broken_rest(label, *, limit=100, offset=0):
        if label == "Paper":  # 大标签 REST 分页超时（MATCH+SKIP 全量物化）
            raise GraphRequestError("read timeout", status_code=504)
        return LookupGraph.get_nodes_by_label(graph, label, limit=limit, offset=offset)

    graph.get_nodes_by_label = broken_rest
    milvus = FakeMilvusClient()
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr("service.entity_search.get_milvus_client", lambda: milvus)
    monkeypatch.setattr("service.entity_search._embedding_client", FakeEmbeddingClient)
    monkeypatch.setattr("service.entity_search._default_space", lambda: "dev2")

    service = EntitySearchService(state_session)
    result = service.reindex()

    # Paper 无图索引且 REST 拉不动：跳过但不让整次重建失败
    assert result["entityCount"] == 1
    assert result["typeCounts"] == {"Expert": 1}
    assert result["skippedLabels"] == ["Paper"]
    rows = milvus.collections[COLLECTION_NAME]
    assert len(rows) == 1 and rows[0]["vid"] == "expert_1"
    assert service.types() == [{"name": "Expert", "count": 1}]
    assert graph.lookup_reads == ["Expert"] * 4  # 两遍各一次探活 + 一次分页；Paper 第二遍不再重试


def test_reindex_clips_embedding_input_to_service_caps(
    state_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """m3e 服务限制单条 ≤16000 字符、单批 ≤64：超限 422 拒绝整批，重建首批评分即中断。"""
    from service.entity_search import EMBED_BATCH_SIZE, EMBED_TEXT_MAX_CHARS

    graph = FakeGraph(
        ["Expert"],
        {
            "Expert": [
                # 20 个长 ASCII 属性：单属性 2048B 上限截不断，拼起来 3.2 万字符
                # ——按 32KB 字节语料上限可入库，但超出 m3e 的 16000 字符上限
                FakeNode("expert_1", {"name": "张三", **{f"f{i}": "a" * 3000 for i in range(20)}}),
                FakeNode("expert_2", {"name": "李四"}),
            ]
        },
    )
    batch_sizes: list[int] = []
    text_lengths: list[int] = []

    class RecordingEmbedding:
        def embed(self, texts):
            batch_sizes.append(len(texts))
            text_lengths.extend(len(text) for text in texts)
            return [[1.0, 0.5, 0.25] for _ in texts]

        def embed_one(self, text):
            return [1.0, 0.5, 0.25]

    milvus = FakeMilvusClient()
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr("service.entity_search.get_milvus_client", lambda: milvus)
    monkeypatch.setattr("service.entity_search._embedding_client", RecordingEmbedding)

    result = EntitySearchService(state_session).reindex()

    assert result["entityCount"] == 2
    assert max(batch_sizes) <= EMBED_BATCH_SIZE
    assert max(text_lengths) <= EMBED_TEXT_MAX_CHARS
    # 存储与 BM25 语料仍保留完整长文本，只裁 embedding 输入
    long_row = next(row for row in milvus.collections[COLLECTION_NAME] if row["vid"] == "expert_1")
    assert len(long_row["search_text"]) > EMBED_TEXT_MAX_CHARS


def test_reindex_clips_varchar_fields_by_utf8_bytes(
    state_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Milvus VARCHAR max_length 按 UTF-8 字节计：2048 个中文字符 = 6144 字节会被整批拒绝。"""
    graph = FakeGraph(
        ["Expert"],
        {
            "Expert": [
                FakeNode("expert_1", {"name": "长" * 3000, "id": "号" * 300}),
                FakeNode("expert_2", {"name": "李四"}),
            ]
        },
    )
    milvus = FakeMilvusClient()
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr("service.entity_search.get_milvus_client", lambda: milvus)
    monkeypatch.setattr("service.entity_search._embedding_client", FakeEmbeddingClient)
    monkeypatch.setattr("service.entity_search._default_space", lambda: "dev2")

    result = EntitySearchService(state_session).reindex()

    assert result["entityCount"] == 2  # 超长字段不再让整批 upsert 失败
    long_row = next(row for row in milvus.collections[COLLECTION_NAME] if row["vid"] == "expert_1")
    assert len(long_row["name"].encode("utf-8")) <= 2048
    assert len(long_row["entity_id"].encode("utf-8")) <= 256


def test_reindex_skips_overlong_vid(state_session, monkeypatch: pytest.MonkeyPatch) -> None:
    """VID 超过 Milvus vid 字段 128 字节上限的垃圾顶点跳过，不阻断重建。"""
    graph = FakeGraph(
        ["Expert"],
        {
            "Expert": [
                FakeNode("v" * 200, {"name": "超长VID"}),
                FakeNode("expert_1", {"name": "张三"}),
            ]
        },
    )
    milvus = FakeMilvusClient()
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr("service.entity_search.get_milvus_client", lambda: milvus)
    monkeypatch.setattr("service.entity_search._embedding_client", FakeEmbeddingClient)

    result = EntitySearchService(state_session).reindex(space="dev2")

    assert result["entityCount"] == 1
    assert [row["vid"] for row in milvus.collections[COLLECTION_NAME]] == ["expert_1"]


def test_reindex_skips_label_when_lookup_fails_midway(
    state_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """长任务中途 LOOKUP 瞬时失败按标签降级跳过，其余标签照常完成。"""

    class FlakyLookupGraph(LookupGraph):
        def execute_query(self, query: str):
            if "OFFSET 2000" in query:  # 第二页起图服务抖动
                raise GraphRequestError("read timeout", status_code=504)
            return super().execute_query(query)

    graph = FlakyLookupGraph(
        ["Expert", "Scholar"],
        {
            # 超过一页（2000/页），第二页触发抖动
            "Expert": [FakeNode(f"expert_{i}", {"name": f"专家{i}"}) for i in range(2001)],
            "Scholar": [FakeNode("scholar_1", {"name": "学者一"})],
        },
        lookup_labels={"Expert", "Scholar"},
    )
    milvus = FakeMilvusClient()
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr("service.entity_search.get_milvus_client", lambda: milvus)
    monkeypatch.setattr("service.entity_search._embedding_client", FakeEmbeddingClient)
    monkeypatch.setattr("service.entity_search._default_space", lambda: "dev2")

    result = EntitySearchService(state_session).reindex()

    assert result["entityCount"] == 1  # 只有 Scholar 完成
    assert result["skippedLabels"] == ["Expert"]
    assert [row["vid"] for row in milvus.collections[COLLECTION_NAME]] == ["scholar_1"]


def test_reindex_aborts_when_all_labels_unreadable(
    state_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """图服务整体不可读（全部标签 LOOKUP/REST 均失败）≠ 空空间：中止重建并保留旧索引。

    2026-09-21 实测：共享图过载时所有标签按超时跳过，重建继续走「空间无实体」
    分支清空 Milvus 旧行并落 entityCount=0 的 state——一次图抖动毁掉整个检索。
    """
    graph = LookupGraph(
        ["Expert", "Paper"],
        {
            "Expert": [FakeNode("expert_1", {"id": "E-1", "name": "张三"})],
            "Paper": [FakeNode("paper_1", {"id": "P-1", "title": "深度学习综述"})],
        },
        lookup_labels=set(),  # 无一标签可 LOOKUP（探活必失败）
    )

    def dead_rest(label, *, limit=100, offset=0):
        raise GraphRequestError("read timeout", status_code=504)

    graph.get_nodes_by_label = dead_rest
    milvus = FakeMilvusClient()
    # 既有索引行 + 既有 state 快照：中止时必须原样保留
    milvus.collections[COLLECTION_NAME] = [
        {"document_id": "dev2::expert_1", "vid": "expert_1", "graph_space": "dev2"}
    ]
    state_session.add(
        EntitySearchState(
            graph_space="dev2",
            vocabulary='{"张": 0}',
            document_frequency='{"张": 1}',
            document_count=1,
            entity_count=1,
            type_counts='{"Expert": 1}',
            embedding_model="moka-ai/m3e-small",
        )
    )
    state_session.commit()
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr("service.entity_search.get_milvus_client", lambda: milvus)
    monkeypatch.setattr("service.entity_search._embedding_client", FakeEmbeddingClient)
    monkeypatch.setattr("service.entity_search._default_space", lambda: "dev2")

    service = EntitySearchService(state_session)
    with pytest.raises(EntitySearchError, match="图服务当前不可读"):
        service.reindex()

    # 旧行未清、无新写入；state 快照未被空结果覆盖
    assert milvus.deleted == []
    assert [row["vid"] for row in milvus.collections[COLLECTION_NAME]] == ["expert_1"]
    assert service.status()["entityCount"] == 1


def test_reindex_aborts_when_second_pass_loses_everything(
    state_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """首遍读到语料、第二遍全灭（图中途退化）≠ 空空间：中止并保留旧索引。

    2026-09-21 实测：首遍只有字母序靠前的小标签成功（document_count>0 过掉
    首遍守卫），organization_base 中途失败触发图退化，第二遍连小标签也读不
    回来 → written=0 → 走「空空间」分支清空索引。
    """

    class DegradingGraph(LookupGraph):
        """前两次查询（首遍探活+分页）成功，之后图服务退化全部失败。"""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.budget = 2  # 首遍：1 次探活 + 1 页

        def execute_query(self, query):
            if self.budget <= 0:
                raise GraphRequestError("read timeout", status_code=504)
            self.budget -= 1
            return super().execute_query(query)

        def get_nodes_by_label(self, label, *, limit=100, offset=0):
            raise GraphRequestError("read timeout", status_code=504)

    graph = DegradingGraph(
        ["Expert"],
        {"Expert": [FakeNode("expert_1", {"id": "E-1", "name": "张三"})]},
        lookup_labels={"Expert"},
    )
    milvus = FakeMilvusClient()
    milvus.collections[COLLECTION_NAME] = [
        {"document_id": "dev2::expert_1", "vid": "expert_1", "graph_space": "dev2"}
    ]
    state_session.add(
        EntitySearchState(
            graph_space="dev2",
            vocabulary='{"张": 0}',
            document_frequency='{"张": 1}',
            document_count=1,
            entity_count=1,
            type_counts='{"Expert": 1}',
            embedding_model="moka-ai/m3e-small",
        )
    )
    state_session.commit()
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr("service.entity_search.get_milvus_client", lambda: milvus)
    monkeypatch.setattr("service.entity_search._embedding_client", FakeEmbeddingClient)
    monkeypatch.setattr("service.entity_search._default_space", lambda: "dev2")

    service = EntitySearchService(state_session)
    with pytest.raises(EntitySearchError, match="第二遍"):
        service.reindex()

    # written=0 时绝不走「空空间」清空：旧索引与旧快照原样保留
    assert milvus.deleted == []
    assert [row["vid"] for row in milvus.collections[COLLECTION_NAME]] == ["expert_1"]
    assert service.status()["entityCount"] == 1


def test_reindex_defers_rest_fallback_labels_until_lookup_labels_done(
    state_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """无索引标签的 REST 兜底排在全部 LOOKUP 标签之后。

    REST 的 MATCH+SKIP 全量扫描会打满共享图（网关服务端还会重试超时查询），
    混排会让排在后面的 LOOKUP 标签也排队超时，放大成整次重建全跳过。
    APaper 字母序在 Expert 之前：若混排，Expert 的读取会被 APaper 拖累。
    """

    class SequencedGraph(LookupGraph):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.read_order: list[tuple[str, str]] = []

        def execute_query(self, query):
            label = query.split("`")[1]
            self.read_order.append((label, "lookup"))
            return super().execute_query(query)

        def get_nodes_by_label(self, label, *, limit=100, offset=0):
            self.read_order.append((label, "rest"))
            return super().get_nodes_by_label(label, limit=limit, offset=offset)

    graph = SequencedGraph(
        ["APaper", "Expert"],
        {
            "APaper": [FakeNode("ap_1", {"id": "A-1", "title": "无索引标签"})],
            "Expert": [FakeNode("expert_1", {"id": "E-1", "name": "张三"})],
        },
        lookup_labels={"Expert"},
    )
    milvus = FakeMilvusClient()
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr("service.entity_search.get_milvus_client", lambda: milvus)
    monkeypatch.setattr("service.entity_search._embedding_client", FakeEmbeddingClient)
    monkeypatch.setattr("service.entity_search._default_space", lambda: "dev2")

    EntitySearchService(state_session).reindex()

    # 第一遍里 Expert（LOOKUP）的所有读取都发生在 APaper（REST）之前
    first_rest = next(i for i, (_, how) in enumerate(graph.read_order) if how == "rest")
    expert_reads = [i for i, (label, _) in enumerate(graph.read_order) if label == "Expert"]
    assert expert_reads, "Expert 应有 LOOKUP 读取"
    assert max(expert_reads[:2]) < first_rest, "LOOKUP 标签应先于 REST 兜底标签读取"


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


def test_reindex_late_embedding_failure_removes_partial_snapshot(
    state_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph = FakeGraph(
        ["Expert"],
        {"Expert": [FakeNode(f"expert_{index}", {"name": f"专家{index}"}) for index in range(3)]},
    )
    milvus = FakeMilvusClient()

    class FailOnSecondBatch:
        calls = 0

        def embed(self, texts):
            self.calls += 1
            if self.calls == 2:
                return None
            return [[1.0, 0.5, 0.25] for _ in texts]

    monkeypatch.setattr("service.entity_search.EMBED_BATCH_SIZE", 2)
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr("service.entity_search.get_milvus_client", lambda: milvus)
    monkeypatch.setattr("service.entity_search._embedding_client", FailOnSecondBatch)

    with pytest.raises(EntitySearchError, match="embedding 服务调用失败"):
        EntitySearchService(state_session).reindex(space="dev2")

    assert milvus.collections[COLLECTION_NAME] == []


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


def test_reindex_complex_property_has_real_bm25_dimension(
    state_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph = FakeGraph(
        ["Patent"],
        {
            "Patent": [
                FakeNode(
                    "patent_1",
                    {
                        "title": "测试专利",
                        "keywords": ["人工智能", {"zhName": "知识图谱"}],
                    },
                )
            ]
        },
    )
    milvus = FakeMilvusClient()
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr("service.entity_search.get_milvus_client", lambda: milvus)
    monkeypatch.setattr("service.entity_search._embedding_client", FakeEmbeddingClient)

    EntitySearchService(state_session).reindex(space="dev2")

    state = state_session.get(EntitySearchState, "dev2")
    vocabulary = json.loads(state.vocabulary)
    query_dimensions = {
        vocabulary[token] for token in ("知识图谱", "知识", "图谱") if token in vocabulary
    }
    row = milvus.collections[COLLECTION_NAME][0]
    assert query_dimensions
    assert query_dimensions & set(row["sparse_vector"])
    assert "知识图谱" in row["search_text"]


def test_reindex_infers_dim_when_config_dim_unset(
    state_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """配置未声明维度时以首个成功响应推断，集合按推断维度创建。"""
    monkeypatch.setattr(
        "service.entity_search._resolve_embedding_config",
        lambda: {
            "base_url": "http://embedding.test",
            "model": "m3e-test",
            "api_key": "test-key",
            "dim": None,
            "config_id": "EMB-1",
        },
    )
    graph = FakeGraph(["Expert"], {"Expert": [FakeNode("expert_1", {"id": "E-1", "name": "张三"})]})
    milvus = FakeMilvusClient()
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr("service.entity_search.get_milvus_client", lambda: milvus)
    monkeypatch.setattr("service.entity_search._embedding_client", lambda: FakeEmbeddingClient())

    result = EntitySearchService(state_session).reindex(space="dev2")

    dense = next(field for field in milvus.schema_fields if field.get("name") == "dense_vector")
    assert dense["dim"] == 3  # FakeEmbeddingClient 返回 3 维
    assert result["embeddingModel"] == "m3e-test"
    assert result["embeddingConfigId"] == "EMB-1"


def test_reindex_recreates_collection_when_dim_changes(
    state_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """换 embedding 配置导致维度变化时整体丢弃重建集合（单集合只能存一种维度）。"""
    graph = FakeGraph(["Expert"], {"Expert": [FakeNode("expert_1", {"id": "E-1", "name": "张三"})]})
    milvus = FakeMilvusClient()
    milvus.collections[COLLECTION_NAME] = []  # 模拟既有集合
    milvus.describe_fields = [
        {"name": "document_id"},
        {"name": "graph_space"},
        {"name": "dense_vector", "params": {"dim": 999}},
    ]
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr("service.entity_search.get_milvus_client", lambda: milvus)
    monkeypatch.setattr("service.entity_search._embedding_client", lambda: FakeEmbeddingClient())

    EntitySearchService(state_session).reindex(space="dev2")

    assert milvus.dropped == [COLLECTION_NAME]
    dense = next(field for field in milvus.schema_fields if field.get("name") == "dense_vector")
    assert dense["dim"] == 3


def test_reindex_without_embedding_config_raises(
    state_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """完全未配置时重建给出明确指引；查询端客户端为 None 走 BM25 降级而非报错。"""

    def _unconfigured():
        raise EntitySearchError("未配置 embedding 服务：请在「配置管理」设置默认 embedding 配置")

    graph = FakeGraph(["Expert"], {"Expert": [FakeNode("expert_1", {"id": "E-1", "name": "张三"})]})
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr("service.entity_search._resolve_embedding_config", _unconfigured)

    with pytest.raises(EntitySearchError, match="未配置 embedding"):
        EntitySearchService(state_session).reindex(space="dev2")

    assert EntitySearchService(state_session).status()["currentEmbeddingModel"] is None


def test_search_sparse_only_when_embedding_unconfigured(
    state_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """embedding 完全未配置时检索降级单路 BM25，不再因空客户端崩溃。"""
    graph = FakeGraph(["Expert"], {"Expert": [FakeNode("expert_1", {"id": "E-1", "name": "张三"})]})
    milvus = FakeMilvusClient()
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr("service.entity_search.get_milvus_client", lambda: milvus)
    monkeypatch.setattr("service.entity_search._embedding_client", lambda: FakeEmbeddingClient())
    service = EntitySearchService(state_session)
    service.reindex(space="dev2")

    monkeypatch.setattr("service.entity_search._embedding_client", lambda: None)

    def fake_hybrid_search(self, client, *, dense_vector, sparse_vector, expr, limit):
        assert dense_vector is None
        assert sparse_vector
        return []

    monkeypatch.setattr(EntitySearchService, "_hybrid_search", fake_hybrid_search)
    result = service.search(keyword="张三", space="dev2")
    assert result["mode"] == "sparse"


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
    assert len(calls) == 9  # 每次查 3 个不同首列属性索引；重复索引及其他类型排除
    assert all(call[0] == ["Expert"] and call[2:] == (500, 0) for call in calls)


def test_search_exact_arbitrary_indexed_property_works_without_milvus(state_session, monkeypatch):
    node = FakeNode("org_1", {"name": "机构甲", "library": "国内机构要素库"})
    graph = FakeGraph(["Organization"], {"Organization": [node]})
    graph.list_indexes = lambda label: [
        SimpleNamespace(label="Organization", properties=["library"])
    ]

    def find_nodes(labels, properties, *, limit, offset):
        assert labels == ["Organization"]
        assert properties == {"library": "国内机构要素库"}
        return FakePagedResult([node])

    graph.find_nodes = find_nodes

    def no_milvus():
        pytest.fail("已建图属性索引精确命中不应访问 Milvus")

    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr("service.entity_search.get_milvus_client", no_milvus)
    result = EntitySearchService(state_session).search(keyword="国内机构要素库", space="dev2")

    assert result["mode"] == "graph-exact"
    assert result["items"][0]["vid"] == "org_1"
    assert result["items"][0]["properties"]["library"] == "国内机构要素库"


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


# ---------------------------------------------------------------------------
# upsert_entity：裁决写图后单实体增量入索引（FUNC-00813）
# ---------------------------------------------------------------------------


def _indexed_two_expert_graph() -> tuple[FakeGraph, FakeMilvusClient]:
    graph = FakeGraph(
        ["Expert"],
        {
            "Expert": [
                FakeNode("expert_1", {"id": "E-1", "name": "张三"}),
                FakeNode("expert_2", {"id": "E-2", "name": "李四"}),
            ]
        },
    )
    return graph, FakeMilvusClient()


def test_upsert_entity_new_vertex_increments_state_counts(
    state_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """create 裁决落新 vid：Milvus 幂等 upsert 一行，计数快照 +1。"""
    graph, milvus = _indexed_two_expert_graph()
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr("service.entity_search.get_milvus_client", lambda: milvus)
    monkeypatch.setattr("service.entity_search._embedding_client", FakeEmbeddingClient)
    monkeypatch.setattr("service.entity_search._default_space", lambda: "dev2")

    service = EntitySearchService(state_session)
    service.reindex()
    # 裁决 create 后图里多出的新顶点（与既有实体同名 → BM25 词表可编码）
    graph._nodes["Expert"].append(
        FakeNode("expert_3", {"id": "E-3", "name": "张三", "org": "中科院"})
    )

    result = service.upsert_entity(space="dev2", node_label="Expert", vid="expert_3", is_new=True)

    assert result == {"upserted": True, "vid": "expert_3", "entityType": "Expert"}
    row = next(r for r in milvus.collections[COLLECTION_NAME] if r["vid"] == "expert_3")
    assert row["document_id"] == "dev2::expert_3"
    assert row["entity_id"] == "E-3"
    assert row["name"] == "张三"
    assert row["entity_type"] == "Expert"
    assert row["graph_space"] == "dev2"
    assert len(row["dense_vector"]) == 3
    assert row["sparse_vector"]  # 词表内 token 已编码
    state = state_session.get(EntitySearchState, "dev2")
    assert state.entity_count == 3  # 2 → 3
    assert json.loads(state.type_counts) == {"Expert": 3}


def test_upsert_entity_merge_keeps_state_counts(
    state_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """merge 裁决覆盖已有行（幂等 upsert），计数快照不变。"""
    graph, milvus = _indexed_two_expert_graph()
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr("service.entity_search.get_milvus_client", lambda: milvus)
    monkeypatch.setattr("service.entity_search._embedding_client", FakeEmbeddingClient)

    service = EntitySearchService(state_session)
    service.reindex(space="dev2")

    result = service.upsert_entity(space="dev2", node_label="Expert", vid="expert_1", is_new=False)

    assert result["upserted"] is True
    assert len(milvus.collections[COLLECTION_NAME]) == 2  # 覆盖未新增
    state = state_session.get(EntitySearchState, "dev2")
    assert state.entity_count == 2
    assert json.loads(state.type_counts) == {"Expert": 2}


def test_upsert_entity_without_state_returns_not_built(
    state_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph, milvus = _indexed_two_expert_graph()
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr("service.entity_search.get_milvus_client", lambda: milvus)
    monkeypatch.setattr("service.entity_search._embedding_client", FakeEmbeddingClient)

    result = EntitySearchService(state_session).upsert_entity(
        space="dev2", node_label="Expert", vid="expert_1", is_new=True
    )

    assert result == {"upserted": False, "reason": "space index not built"}


def test_upsert_entity_skips_while_reindex_running(
    state_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph, milvus = _indexed_two_expert_graph()
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr("service.entity_search.get_milvus_client", lambda: milvus)
    monkeypatch.setattr("service.entity_search._embedding_client", FakeEmbeddingClient)
    monkeypatch.setattr("service.entity_search._database_reindex_running", lambda session: True)

    result = EntitySearchService(state_session).upsert_entity(
        space="dev2", node_label="Expert", vid="expert_1", is_new=True
    )

    assert result == {"upserted": False, "reason": "reindex in progress"}


def test_upsert_entity_missing_vertex_returns_not_found(
    state_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph, milvus = _indexed_two_expert_graph()
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr("service.entity_search.get_milvus_client", lambda: milvus)
    monkeypatch.setattr("service.entity_search._embedding_client", FakeEmbeddingClient)

    service = EntitySearchService(state_session)
    service.reindex(space="dev2")

    result = service.upsert_entity(space="dev2", node_label="Expert", vid="ghost", is_new=True)

    assert result == {"upserted": False, "reason": "vertex not found in graph"}


def test_upsert_entity_unknown_tokens_skip_to_avoid_empty_sparse_vector(
    state_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """文本 token 全不在全量词表（全新造词）→ 跳过，不向 Milvus 发空稀疏向量。"""
    graph, milvus = _indexed_two_expert_graph()
    graph._nodes["Expert"].append(FakeNode("expert_9", {"name": "犄旮旯"}))
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr("service.entity_search.get_milvus_client", lambda: milvus)
    monkeypatch.setattr("service.entity_search._embedding_client", FakeEmbeddingClient)
    # 词表只含「张三」：任何不含该 token 的文本都编不出稀疏向量
    state_session.add(
        EntitySearchState(
            graph_space="dev2",
            entity_count=1,
            document_count=1,
            vocabulary=json.dumps({"张三": 0}),
            document_frequency=json.dumps({"张三": 1}),
            average_document_length=10.0,
            k1=1.5,
            b=0.75,
            type_counts='{"Expert":1}',
        )
    )
    state_session.commit()

    result = EntitySearchService(state_session).upsert_entity(
        space="dev2", node_label="Expert", vid="expert_9", is_new=True
    )

    assert result == {"upserted": False, "reason": "empty sparse vector"}
    assert milvus.collections == {}  # 未发生任何 Milvus 写入


def test_upsert_entity_embedding_failure_degrades(
    state_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph, milvus = _indexed_two_expert_graph()
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr("service.entity_search.get_milvus_client", lambda: milvus)
    monkeypatch.setattr("service.entity_search._embedding_client", FakeEmbeddingClient)

    service = EntitySearchService(state_session)
    service.reindex(space="dev2")

    class BrokenEmbedding:
        def embed(self, texts):
            return None

    monkeypatch.setattr("service.entity_search._embedding_client", lambda: BrokenEmbedding())
    result = service.upsert_entity(space="dev2", node_label="Expert", vid="expert_1", is_new=True)

    assert result == {"upserted": False, "reason": "embedding failed"}


def test_upsert_entity_milvus_error_degrades(
    state_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    graph, milvus = _indexed_two_expert_graph()
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr("service.entity_search.get_milvus_client", lambda: milvus)
    monkeypatch.setattr("service.entity_search._embedding_client", FakeEmbeddingClient)

    service = EntitySearchService(state_session)
    service.reindex(space="dev2")

    class BrokenMilvus(FakeMilvusClient):
        def upsert(self, collection_name, data):
            raise RuntimeError("milvus down")

    broken = BrokenMilvus()
    broken.collections = milvus.collections  # 复用 reindex 建好的集合，走到 upsert 才炸
    monkeypatch.setattr("service.entity_search.get_milvus_client", lambda: broken)
    result = service.upsert_entity(space="dev2", node_label="Expert", vid="expert_1", is_new=True)

    assert result["upserted"] is False
    assert result["reason"].startswith("milvus error:")
    state = state_session.get(EntitySearchState, "dev2")
    assert state.entity_count == 2  # 写入失败不 bump 计数
