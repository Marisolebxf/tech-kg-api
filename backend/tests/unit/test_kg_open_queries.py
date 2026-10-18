"""只读查询契约：打桩图库，不依赖实际基础设施。"""

from types import SimpleNamespace

import pytest

from infra.graph_db.exceptions import GraphRequestError
from service.kg_open import OpenGraphQueries, OpenQueryError, decode_cursor, encode_cursor

CATALOG = {
    "entityTypes": [
        {"name": "Paper", "properties": [{"name": "title", "type": "string"}]},
        {"name": "Person", "properties": [{"name": "age", "type": "int64"}]},
    ],
    "relationTypes": [{"name": "AUTHORED_BY", "sourceType": "Paper", "targetType": "Person"}],
}


def vertex(vid, label="Paper"):
    return {"id": vid, "labels": [label], "properties": {"title": vid}}


def edge(rank=0, src="paper/1", dst="person@1"):
    return {
        "e": {"type": "AUTHORED_BY", "properties": {"confidence": 0.8}},
        "src": src,
        "dst": dst,
        "edge_rank": rank,
    }


class FakeClient:
    def __init__(self, *pages):
        self.pages, self.queries = list(pages), []

    def execute_read(self, query, *, timeout):
        assert timeout == 20
        self.queries.append(query)
        return SimpleNamespace(records=self.pages.pop(0))


def test_cursor_is_bound_to_space_filters_and_endpoint():
    scope = {"space": "dev", "kind": "entities", "type": "Paper", "filter": "a"}
    cursor = encode_cursor(scope, ['paper/"quoted"'])
    assert decode_cursor(cursor, scope, (str,)) == ['paper/"quoted"']
    for key in scope:
        with pytest.raises(OpenQueryError):
            decode_cursor(cursor, {**scope, key: "changed"}, (str,))
    for token in ("broken", "A" * 4097, encode_cursor(scope, [True])):
        with pytest.raises(OpenQueryError):
            decode_cursor(token, scope, (str,))


def test_entity_keyset_lookahead_without_count():
    client = FakeClient(
        [{"v": vertex("a")}, {"v": vertex("b")}, {"v": vertex("c")}], [{"v": vertex("c")}]
    )
    service = OpenGraphQueries(client, CATALOG, "dev")
    first = service.entities("Paper", 2)
    assert first["hasMore"] is True
    assert [e["id"] for e in first["entities"]] == ["a", "b"]
    last = service.entities("Paper", 2, first["nextCursor"])
    assert last["hasMore"] is False and last["nextCursor"] == ""
    assert 'WHERE id($-.v) > "b"' in client.queries[1]
    assert "ORDER BY $-.vid" in client.queries[0]
    with pytest.raises(OpenQueryError):
        service.entities("Paper", 2, first["nextCursor"], offset=1)


def test_parallel_edges_keep_rank_and_resume_at_full_edge_key():
    client = FakeClient([edge(0), edge(1)], [edge(1)])
    service = OpenGraphQueries(client, CATALOG, "dev")
    first = service.edges("AUTHORED_BY", 1, include_entities=False)
    last = service.edges("AUTHORED_BY", 1, first["nextCursor"], include_entities=False)
    assert first["edges"][0]["id"] != last["edges"][0]["id"]
    assert last["edges"][0]["rank"] == 1
    assert "$-.edge_rank > 0" in client.queries[1]
    assert "sourceEntity" not in first["edges"][0]


def test_dangling_endpoints_are_null_and_properties_survive():
    client = FakeClient([edge()], [{"v": vertex("paper/1")}])
    page = OpenGraphQueries(client, CATALOG, "dev").edges("AUTHORED_BY", 20)
    item = page["edges"][0]
    assert item["sourceEntity"]["id"] == "paper/1"
    assert item["targetEntity"] is None
    assert item["properties"] == {"confidence": 0.8}


def test_missing_index_fails_explicitly_without_match_scan():
    class NoIndex:
        def execute_read(self, query, **kwargs):
            raise GraphRequestError("There is no index to use", status_code=400)

    with pytest.raises(OpenQueryError) as exc:
        OpenGraphQueries(NoIndex(), CATALOG, "dev").entities("Paper", 20)
    assert exc.value.status == 503


def test_missing_stats_is_unknown_not_current_page_length():
    class NoStats:
        def stats_snapshot(self):
            raise GraphRequestError("no any stats info", status_code=400)

    assert OpenGraphQueries(NoStats(), CATALOG, "dev").stats() is None
