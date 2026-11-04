from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from infra.graph_db.client import TRSGraphClient
from infra.graph_db.config import TRSGraphSettings
from infra.graph_db.exceptions import GraphRequestError
from infra.graph_db.models import GraphNode, GraphQueryResult
from infra.graph_db.vid_alias import PREFIXES, VidAliasGraphClient, make_graph_client


@pytest.fixture
def graph(monkeypatch):
    storage = {}
    calls = []
    def fetch(self, ids):
        calls.append(list(ids))
        return {str(v): storage[str(v)].model_copy(deep=True) for v in ids if str(v) in storage}
    monkeypatch.setattr(TRSGraphClient, "get_nodes_bulk", fetch)
    client = VidAliasGraphClient(TRSGraphSettings(space="test"), PREFIXES)
    client.storage = storage
    client.fetch_calls = calls
    return client


def node(vid, tag, **props):
    return GraphNode(id=vid, labels=[tag], properties=props)


@pytest.mark.parametrize("requested", ["IC0007", "chain_IC0007"])
def test_real_chain_split_hydrates_both_ids(graph, requested):
    graph.storage.update({
        "IC0007": node("IC0007", "IndustryChain", chain_name="集成电路", chain_code="IC0007"),
        "chain_IC0007": node("chain_IC0007", "IndustryChain", chain_name=None),
    })
    result = graph.get_node(requested)
    assert result.id == "chain_IC0007"
    assert result.properties["chain_name"] == "集成电路"
    assert graph.storage["chain_IC0007"].properties["chain_name"] is None


def test_existing_prefixed_and_raw_only_graphs_keep_ids(graph):
    graph.storage["person_1"] = node("person_1", "Person", name_zh="原有专家")
    graph.storage["2"] = node("2", "Person", name_zh="裸ID专家")
    assert graph.get_node("person_1").id == "person_1"
    assert graph.get_node("2").id == "2"


def test_type_collision_does_not_mix_properties(graph):
    graph.storage["1"] = node("1", "Organization", name_cn="机构")
    graph.storage["person_1"] = node("person_1", "Person", name_zh="专家")
    assert graph.get_node("person_1").properties == {"name_zh": "专家"}


def test_ambiguous_bare_multitag_requires_typed_id(graph):
    graph.storage["1"] = GraphNode(id="1", labels=["Person", "Organization"])
    with pytest.raises(GraphRequestError, match="多个实体类型"):
        graph.get_node("1")


def test_prefix_is_removed_once_and_underscores_preserved(graph):
    graph.storage["a_b"] = node("a_b", "Person", name_zh="专家")
    graph.storage["person_a_b"] = node("person_a_b", "Person")
    assert graph.get_node("person_a_b").properties["name_zh"] == "专家"


def test_zero_and_false_are_effective_values(graph):
    graph.storage["1"] = node("1", "Person", confidence=0, active=False)
    graph.storage["person_1"] = node("person_1", "Person", confidence=None, active=None)
    assert graph.get_node("person_1").properties == {"confidence": 0, "active": False}


def test_attribute_write_address_is_original_physical_vertex(graph):
    graph.storage["1"] = node("1", "Person", name_zh="专家")
    graph.storage["person_1"] = node("person_1", "Person", name_zh=None)
    assert graph.attribute_vid("person_1", "Person") == "1"
    with pytest.raises(GraphRequestError):
        graph.attribute_vid("person_1", "Organization")


def test_bulk_resolves_each_requested_key_without_crossing_spaces(graph):
    graph.storage["IC0007"] = node("IC0007", "IndustryChain", chain_name="集成电路")
    graph.storage["chain_IC0007"] = node("chain_IC0007", "IndustryChain")
    result = graph.get_nodes_bulk(["IC0007", "chain_IC0007", "missing"])
    assert result["IC0007"].id == result["chain_IC0007"].id
    assert "missing" not in result


def test_edge_traversal_uses_both_ids_actual_direction_rank_and_properties(graph):
    graph.storage.update({
        "IC0007": node("IC0007", "IndustryChain", chain_name="集成电路"),
        "chain_IC0007": node("chain_IC0007", "IndustryChain"),
        "IC1": node("IC1", "IndustryNode", node_name="芯片"),
        "node_IC1": node("node_IC1", "IndustryNode"),
    })
    row = {"src": "chain_IC0007", "dst": "node_IC1", "et": "HAS_NODE",
           "rk": 3, "props": {"weight": 0.8}}
    graph.execute_read = Mock(return_value=GraphQueryResult(records=[row]))
    edges = graph.get_node_edges("IC0007", direction="in")
    sql = graph.execute_read.call_args.args[0]
    assert '"IC0007"' in sql and '"chain_IC0007"' in sql
    assert "REVERSELY" in sql and "src(edge)" in sql
    assert edges[0].source_id == "chain_IC0007"
    assert edges[0].target_id == "node_IC1"
    assert edges[0].properties == {"weight": 0.8}
    assert edges[0].id.endswith("@3")


def test_duplicate_alias_edges_dedup_by_type_and_rank(graph):
    graph.storage.update({
        "1": node("1", "Person", name_zh="甲"),
        "person_1": node("person_1", "Person"),
        "2": node("2", "Person", name_zh="乙"),
        "person_2": node("person_2", "Person"),
    })
    rows = [{"src": a, "dst": b, "et": "COAUTHOR_WITH", "rk": rank, "props": {}}
            for a, b, rank in [("1", "2", 0), ("person_1", "person_2", 0),
                               ("person_1", "person_2", 1)]]
    graph.execute_read = Mock(return_value=GraphQueryResult(records=rows))
    edges = graph.get_node_edges("1")
    assert len(edges) == 2


def test_failed_graph_queries_propagate_and_never_trigger_writes(graph):
    graph.execute_read = Mock(side_effect=GraphRequestError("timeout", status_code=504))
    graph.execute_write = Mock()
    with pytest.raises(GraphRequestError, match="timeout"):
        graph.get_node_edges("unknown")
    graph.execute_write.assert_not_called()


def test_typed_paths_filter_hydrated_paper_instead_of_empty_placeholder(graph):
    graph.storage.update({
        "1": node("1", "Person", name_zh="甲"),
        "person_1": node("person_1", "Person"),
        "10": node("10", "Paper", publication_year=2025, title="论文"),
        "paper_10": node("paper_10", "Paper", publication_year=None),
    })
    graph.execute_read = Mock(return_value=GraphQueryResult(records=[
        {"src": "paper_10", "dst": "person_1", "et": "AUTHORED_BY", "rk": 0, "props": {}}
    ]))
    step = SimpleNamespace(edgeType="AUTHORED_BY", direction="in", targetLabel="Paper",
                           targetFilters=[SimpleNamespace(property="publication_year",
                                                          operator="gte", value=2024)])
    body = SimpleNamespace(sourceId="1", targetId=None, steps=[step], limit=10,
                           offset=0, countTotal=True)
    result = graph.typed_paths(body)
    assert result["total"] == 1
    assert result["items"][0]["nodes"][1]["properties"]["title"] == "论文"
    assert result["items"][0]["edges"][0]["source"] == "paper_10"
    step.targetFilters[0].value = 2026
    assert graph.typed_paths(body)["total"] == 0


def test_typed_paths_budget_fails_explicitly_instead_of_truncating(graph):
    graph.storage["1"] = node("1", "Person", name_zh="甲")
    from infra.graph_db.models import GraphEdge
    graph.PATH_BUDGET = 1
    graph.get_node_edges = Mock(return_value=[
        GraphEdge(id=str(i), type="K", source_id="1", target_id=str(i)) for i in range(2)
    ])
    step = SimpleNamespace(edgeType="K", direction="out", targetLabel="Person", targetFilters=[])
    body = SimpleNamespace(sourceId="1", targetId=None, steps=[step], limit=10,
                           offset=0, countTotal=True)
    with pytest.raises(GraphRequestError, match="预算"):
        graph.typed_paths(body)


def test_factory_is_direct_without_space_switch():
    assert isinstance(make_graph_client(TRSGraphSettings()), VidAliasGraphClient)

def test_typed_request_can_read_multitag_bare_without_borrowing_other_type(graph):
    graph.storage["1"] = GraphNode(id="1", labels=["Person", "Organization"],
                                  properties={"name_zh": "专家"})
    graph.storage["person_1"] = node("person_1", "Person")
    assert graph.get_node("person_1").labels == ["Person"]


def test_subgraph_merges_raw_properties_and_prefixed_edges(graph):
    from biz.handler.graph_search import _collect_subgraph
    graph.storage.update({
        "IC0007": node("IC0007", "IndustryChain", chain_name="集成电路"),
        "chain_IC0007": node("chain_IC0007", "IndustryChain"),
        "IC1": node("IC1", "IndustryNode", node_name="芯片"),
        "node_IC1": node("node_IC1", "IndustryNode"),
    })
    graph.execute_read = Mock(return_value=GraphQueryResult(records=[
        {"src": "chain_IC0007", "dst": "node_IC1", "et": "HAS_NODE", "rk": 0, "props": {}}
    ]))
    result = _collect_subgraph(graph, "IC0007", 1, 10, 0, None, "both")
    nodes = {n.id: n for n in result["nodes"]}
    assert set(nodes) == {"chain_IC0007", "node_IC1"}
    assert nodes["chain_IC0007"].properties["chain_name"] == "集成电路"
    assert nodes["node_IC1"].properties["node_name"] == "芯片"
    assert all(e.source in nodes and e.target in nodes for e in result["edges"])


def test_mixed_alias_pagination_continues_after_duplicate_physical_page(graph):
    graph.storage.update({"1": node("1", "Person", name_zh="甲"),
                          "person_1": node("person_1", "Person"),
                          "2": node("2", "Person", name_zh="乙"),
                          "person_2": node("person_2", "Person")})
    duplicate = {"src": "1", "dst": "2", "et": "K", "rk": 0, "props": {}}
    following = {"src": "person_1", "dst": "person_2", "et": "K", "rk": 1, "props": {}}
    graph.execute_read = Mock(side_effect=[
        GraphQueryResult(records=[duplicate] * 100),
        GraphQueryResult(records=[following]),
    ])
    edges = graph.get_node_edges("1", offset=1, limit=1)
    assert len(edges) == 1 and edges[0].id.endswith("@1")
    assert "OFFSET 100" in graph.execute_read.call_args.args[0]
