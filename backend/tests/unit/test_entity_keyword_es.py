"""实体关键词 ES 通道（infra/elasticsearch.py + service 接线）单测。

REST 层用 httpx.MockTransport 伪造 ES；service 层注入 fake store，
覆盖「ES 可用走聚合/取页、任何异常回退图直查、未同步/短词不进 ES」。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import httpx
import pytest

from infra.elasticsearch import ElasticsearchError, EntityKeywordES
from service.entity_search import EntitySearchService

# --------------------------------------------------------------------- fakes


@dataclass
class _Node:
    id: str
    properties: dict


@dataclass
class _Paged:
    items: list
    total: int


class StubGraph:
    """最小图客户端：labels() + keyword_nodes_by_label（CONTAINS 语义，按 vid 排序）。"""

    def __init__(self, labels: list[str], nodes: dict[str, list[_Node]]) -> None:
        self._labels = labels
        self._nodes = nodes
        self.keyword_calls = 0

    def labels(self) -> list[str]:
        return list(self._labels)

    def keyword_nodes_by_label(self, label, keyword, *, limit=100, offset=0, count_only=False):
        self.keyword_calls += 1
        needle = keyword.lower()
        rows = [
            node
            for node in self._nodes.get(label, [])
            if any(needle in str(v).lower() for v in [node.id, *node.properties.values()])
        ]
        rows.sort(key=lambda node: node.id)
        return _Paged([] if count_only else rows[offset : offset + limit], total=len(rows))


@dataclass
class FakeESStore:
    """service 层注入用：counts/page 可编程返回或抛错，并记录调用。"""

    ready_spaces: set[str] = field(default_factory=lambda: {"dev2"})
    fail_counts: bool = False
    fail_page: bool = False
    counts_result: dict[str, dict[str, int]] = field(default_factory=dict)
    page_items: dict[str, list[dict]] = field(default_factory=dict)
    counts_calls: list[tuple[str, str, str | None]] = field(default_factory=list)
    page_calls: list[tuple[str, str, str | None]] = field(default_factory=list)

    def ready(self, space: str) -> bool:
        return space in self.ready_spaces

    def counts(self, space: str, keyword: str, *, entity_type: str | None = None):
        self.counts_calls.append((space, keyword, entity_type))
        if self.fail_counts:
            raise ElasticsearchError("es down")
        return dict(self.counts_result.get(keyword, {}))

    def page(self, space: str, keyword: str, *, entity_type=None, limit=10, offset=0):
        self.page_calls.append((space, keyword, entity_type))
        if self.fail_page:
            raise ElasticsearchError("es down")
        rows = self.page_items.get(keyword, [])
        return rows[offset : offset + limit], len(rows)


def _wire(monkeypatch: pytest.MonkeyPatch, store: FakeESStore | None, graph: StubGraph):
    monkeypatch.setattr("service.entity_search.get_space_client", lambda space: graph)
    monkeypatch.setattr("service.entity_search._default_space", lambda: "dev2")
    monkeypatch.setattr("service.entity_search.get_entity_keyword_es", lambda: store)


def _item(vid: str, name: str, entity_type: str) -> dict:
    return {
        "vid": vid,
        "entityId": vid,
        "name": name,
        "entityType": entity_type,
        "properties": {"name": name},
        "score": None,
    }


# ------------------------------------------------------------- REST 客户端层


def _store_with(handler) -> EntityKeywordES:
    store = EntityKeywordES("http://es.test")
    store._http = httpx.Client(base_url="http://es.test", transport=httpx.MockTransport(handler))
    return store


def test_index_name_sanitizes_space_for_elasticsearch():
    assert EntityKeywordES.index_name("dev2") == "kg_entity_kw_dev2"
    assert EntityKeywordES.index_name("Dev-2") == "kg_entity_kw_dev_2"
    with pytest.raises(ElasticsearchError):
        EntityKeywordES.index_name("  ")


def test_ensure_index_puts_ngram_template_only_when_missing():
    calls: list[tuple[str, str, dict | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            calls.append((request.method, request.url.path, None))
            return httpx.Response(404)
        body = json.loads(request.content) if request.content else {}
        calls.append((request.method, request.url.path, body))
        return httpx.Response(200, json={"acknowledged": True})

    store = _store_with(handler)
    store.ensure_index("dev2")
    put = next(c for c in calls if c[0] == "PUT")
    assert put[1] == "/kg_entity_kw_dev2"
    tokenizer = put[2]["settings"]["analysis"]["tokenizer"]["kw_ngram"]
    assert tokenizer["min_gram"] == 2 and tokenizer["max_gram"] == 3
    props = put[2]["mappings"]["properties"]
    assert props["item"] == {"type": "object", "enabled": False}
    assert props["search_text"]["analyzer"] == "kw_ngram"

    # 已存在（HEAD 200）不再 PUT
    calls.clear()

    def handler_exists(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200 if request.method == "HEAD" else 500)

    _store_with(handler_exists).ensure_index("dev2")
    assert not any(c[0] == "PUT" for c in calls)


def test_upsert_writes_ndjson_with_vid_as_id_and_raises_on_item_error():
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/_bulk":
            seen["body"] = request.content.decode()
            return httpx.Response(
                200, json={"errors": False, "items": [{"index": {"status": 201}}]}
            )
        return httpx.Response(404)

    store = _store_with(handler)
    doc = {
        "vid": "v1",
        "entity_type": "Paper",
        "search_text": "v1\n标题",
        "item": _item("v1", "标题", "Paper"),
    }
    assert store.upsert("dev2", [doc]) == 1
    action, payload = seen["body"].split("\n")[0:2]
    assert json.loads(action) == {"index": {"_index": "kg_entity_kw_dev2", "_id": "v1"}}
    assert json.loads(payload)["search_text"] == "v1\n标题"

    def handler_fail(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"errors": True, "items": [{"index": {"error": {"type": "x", "reason": "bad"}}}]},
        )

    with pytest.raises(ElasticsearchError, match="bad"):
        _store_with(handler_fail).upsert("dev2", [doc])


def test_counts_and_page_request_bodies_and_parsing():
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        bodies.append({"path": request.url.path, "q": body})
        if body.get("size") == 0:
            return httpx.Response(
                200,
                json={
                    "hits": {"total": {"value": 7}},
                    "aggregations": {
                        "by_type": {
                            "buckets": [
                                {"key": "Paper", "doc_count": 5},
                                {"key": "Org", "doc_count": 2},
                            ]
                        }
                    },
                },
            )
        return httpx.Response(
            200,
            json={
                "hits": {
                    "total": {"value": 7},
                    "hits": [
                        {"_source": {"item": _item("p1", "论文一", "Paper")}},
                        {"_source": {"item": _item("p2", "论文二", "Paper")}},
                    ],
                }
            },
        )

    store = _store_with(handler)
    assert store.counts("dev2", "大学") == {"Paper": 5, "Org": 2}
    agg_req = bodies[-1]
    match_clause = agg_req["q"]["query"]["match"]["search_text"]
    assert match_clause == {"query": "大学", "operator": "and"}
    assert agg_req["q"]["track_total_hits"] is True

    items, total = store.page("dev2", "大学", entity_type="Paper", limit=2, offset=0)
    assert total == 7 and [i["vid"] for i in items] == ["p1", "p2"]
    page_req = bodies[-1]
    assert page_req["q"]["sort"] == [{"entity_type": "asc"}, {"vid": "asc"}]
    assert page_req["q"]["query"]["bool"]["filter"] == [{"term": {"entity_type": "Paper"}}]

    # entity_type 过滤同样作用于 counts
    store.counts("dev2", "大学", entity_type="Paper")
    assert bodies[-1]["q"]["query"]["bool"]["filter"] == [{"term": {"entity_type": "Paper"}}]


def test_ready_requires_existing_non_empty_index():
    heads = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            heads.append(request.url.path)
            return httpx.Response(404)
        return httpx.Response(200, json={"count": 0})

    assert _store_with(handler).ready("dev2") is False
    assert heads == ["/kg_entity_kw_dev2"]

    def handler_ok(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            return httpx.Response(200)
        return httpx.Response(200, json={"count": 3})

    assert _store_with(handler_ok).ready("dev2") is True


# ---------------------------------------------------------------- service 层


def _graph() -> StubGraph:
    return StubGraph(
        ["Paper", "Org"],
        {
            "Paper": [
                _Node("p1", {"name": "大学论文", "doi": "10.1/x"}),
                _Node("p2", {"name": "别的"}),
            ],
            "Org": [_Node("o1", {"name": "某某大学"})],
        },
    )


def test_keyword_counts_prefers_es_when_ready(monkeypatch):
    graph = _graph()
    store = FakeESStore(counts_result={"大学": {"Paper": 1, "Org": 1}})
    _wire(monkeypatch, store, graph)
    counts = EntitySearchService(None).keyword_counts(keyword="大学", space="dev2")
    assert counts == {"Paper": 1, "Org": 1}
    assert graph.keyword_calls == 0
    assert store.counts_calls == [("dev2", "大学", None)]


def test_keyword_counts_falls_back_to_graph_on_es_error(monkeypatch):
    graph = _graph()
    store = FakeESStore(fail_counts=True)
    _wire(monkeypatch, store, graph)
    counts = EntitySearchService(None).keyword_counts(keyword="大学", space="dev2")
    assert counts == {"Paper": 1, "Org": 1}
    assert graph.keyword_calls == 2  # 图路径逐标签计数


def test_keyword_counts_falls_back_when_space_not_synced(monkeypatch):
    graph = _graph()
    store = FakeESStore(ready_spaces=set())
    _wire(monkeypatch, store, graph)
    counts = EntitySearchService(None).keyword_counts(keyword="大学", space="dev2")
    assert counts == {"Paper": 1, "Org": 1}
    assert store.counts_calls == []


def test_short_keyword_bypasses_es(monkeypatch):
    graph = _graph()
    store = FakeESStore()
    _wire(monkeypatch, store, graph)
    EntitySearchService(None).keyword_counts(keyword="大", space="dev2")
    assert store.counts_calls == []
    assert graph.keyword_calls == 2


def test_unknown_entity_type_still_validated_against_graph(monkeypatch):
    graph = _graph()
    store = FakeESStore(counts_result={"大学": {"Ghost": 1}})
    _wire(monkeypatch, store, graph)
    from service.entity_search import EntitySearchError

    with pytest.raises(EntitySearchError, match="不存在实体类型"):
        EntitySearchService(None).keyword_counts(keyword="大学", space="dev2", entity_type="Ghost")
    assert store.counts_calls == []


def test_keyword_search_uses_es_page_verbatim(monkeypatch):
    graph = _graph()
    rows = [_item("p1", "大学论文", "Paper"), _item("o1", "某某大学", "Org")]
    store = FakeESStore(page_items={"大学": rows})
    _wire(monkeypatch, store, graph)
    result = EntitySearchService(None).keyword_search(
        keyword="大学", space="dev2", limit=1, offset=1
    )
    assert result["mode"] == "keyword"
    assert result["total"] == 2
    assert result["items"] == [rows[1]]  # ES 排序口径下原样回放
    assert graph.keyword_calls == 0


def test_keyword_search_page_failure_recomputes_graph_counts(monkeypatch):
    graph = _graph()
    # 传入 ES 口径的错误 counts（图上实际 Paper=1, Org=1），取页失败后必须重算
    store = FakeESStore(fail_page=True)
    _wire(monkeypatch, store, graph)
    result = EntitySearchService(None).keyword_search(
        keyword="大学", space="dev2", limit=10, offset=0, counts={"Paper": 99}
    )
    assert result["total"] == 2
    assert [i["vid"] for i in result["items"]] == ["o1", "p1"]  # 标签字典序 + vid 序
