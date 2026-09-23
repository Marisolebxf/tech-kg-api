"""隔离 SDK 的 RPC、数据包装与资源切换防线。"""

import io
import json
from itertools import count

import pytest

from sdk import sandbox_proxy as proxy
from sdk.kg_sdk import Context, get_semantic_client, reset_current_context


@pytest.fixture
def transport(monkeypatch):
    output = io.StringIO()
    monkeypatch.setattr(proxy.sys, "__stdout__", output)
    monkeypatch.setattr(proxy, "_RPC_IDS", count(1))

    def respond(result=None, **fields):
        monkeypatch.setattr(
            proxy.sys,
            "__stdin__",
            io.StringIO(json.dumps({"id": 1, "result": result, **fields}) + "\n"),
        )
        return output

    return respond


def test_context_never_exports_credentials_and_unconfigured_resources_are_none():
    context = Context(
        {
            "_sandbox": True,
            "mysql": {"password": "secret", "host": "private"},
            "graph": {"api_key": "secret"},
            "stepId": "s",
        }
    )
    assert context.to_dict()["mysql"] is True
    assert "secret" not in repr(context.to_dict())
    assert context.step_id == "s"
    assert context.milvus is None
    assert not hasattr(context.graph, "_request")
    assert not hasattr(context.graph, "_settings")
    assert not hasattr(context.graph, "list_spaces")


def test_mysql_sqlalchemy_result_compatibility(transport):
    out = transport({"rows": [{"id": 7, "name": "a"}], "columns": ["id", "name"], "rowcount": 1})
    with Context({"_sandbox": True, "mysql": True}).mysql.engine.connect() as connection:
        result = connection.execute("SELECT id,name FROM items WHERE id=:id", {"id": 7})
        assert result.keys() == ["id", "name"]
        assert result.mappings().first() == {"id": 7, "name": "a"}
    request = json.loads(out.getvalue())
    assert request["resource"] == "mysql"
    assert request["method"] == "query"
    assert request["args"][1] == {"id": 7}


def test_mysql_cursor_and_scalar_shapes(transport):
    transport({"rows": [{"id": 7}], "columns": ["id"], "rowcount": 1})
    with Context({"_sandbox": True, "mysql": True}).mysql.cursor() as cursor:
        assert cursor.execute("SELECT id FROM items") == 1
        assert cursor.description[0][0] == "id"
        assert cursor.fetchone() == (7,)
        assert cursor.fetchone() is None
    assert proxy.Result({"rows": [[42]], "columns": ["n"]}).scalar() == 42


def test_graph_result_attribute_model(transport):
    transport({"records": [{"n": {"id": "n1", "properties": {"name": "test"}}}]})
    graph = Context({"_sandbox": True, "graph": True}).graph
    result = graph.execute_read("MATCH (n) RETURN n LIMIT 1")
    assert result.records[0]["n"]["properties"]["name"] == "test"
    assert result.summary == {}
    assert result.model_dump()["records"][0]["n"]["id"] == "n1"


def test_remote_error_propagates(transport):
    transport(error="禁止跨业务访问")
    with pytest.raises(RuntimeError, match="禁止跨业务"):
        Context({"_sandbox": True, "llm": True}).llm.synthesize("hello")


def test_milvus_database_switch_rejected_before_rpc(transport):
    out = transport()
    milvus = Context({"_sandbox": True, "milvus": True}).milvus
    assert not hasattr(milvus, "use_database")
    assert not hasattr(milvus, "list_databases")
    with pytest.raises(ValueError):
        milvus.query(collection_name="x", db_name="other")
    assert not out.getvalue()


def test_semantic_helpers_stay_local_and_fallback_uses_proxy(monkeypatch, transport):
    monkeypatch.setenv("KG_SCRIPT_CTX", json.dumps({"_sandbox": True, "semantic": True}))
    reset_current_context()
    try:
        out = transport({"data": {"entities": [{"text": "研究"}]}})
        semantic = get_semantic_client("http://untrusted", "not-sent")
        response = semantic.research_entities("title", "body")
        assert semantic.entities_of(response) == [{"text": "研究"}]
        assert json.loads(out.getvalue())["resource"] == "semantic"
        assert "untrusted" not in out.getvalue()
    finally:
        reset_current_context()


def test_rpc_rejects_wrong_id_and_oversized_payload(monkeypatch, transport):
    transport(id=2)
    with pytest.raises(RuntimeError, match="标识"):
        proxy.rpc("graph", "labels")
    monkeypatch.setattr(proxy, "MAX_RPC_BYTES", 20)
    with pytest.raises(ValueError, match="大小"):
        proxy.rpc("llm", "synthesize", ("x" * 100,))


def test_paged_graph_items_are_attributes_not_dict_methods():
    result = proxy.wrap({"items": [{"id": "n1", "properties": {}}], "total": 1})
    assert result.items[0].id == "n1"
    assert result.total == 1


def test_graph_properties_keep_dictionary_methods():
    node = proxy.wrap({"id": "n1", "labels": ["Item"], "properties": {"items": 7, "keys": "v"}})
    assert dict(node.properties.items()) == {"items": 7, "keys": "v"}
    assert node.model_dump()["properties"]["items"] == 7


def test_explicit_unavailable_resource_never_creates_proxy():
    assert Context({"_sandbox": True, "mysql": {"available": False}}).mysql is None


def test_large_response_within_shared_eight_mib_limit(transport):
    text = "x" * (3 * 1024 * 1024)
    transport(text)
    assert proxy.rpc("llm", "synthesize", ("test",)) == text
    assert proxy.MAX_RPC_BYTES == 8 * 1024 * 1024


def test_untrusted_sql_parameters_cannot_change_rpc_envelope(transport):
    out = transport({"rows": [], "columns": []})
    mysql = Context({"_sandbox": True, "mysql": True}).mysql
    mysql.execute("SELECT :method", {"method": "drop_database", "resource": "milvus"})
    frame = json.loads(out.getvalue())
    assert (frame["resource"], frame["method"]) == ("mysql", "query")
    assert frame["args"][1]["resource"] == "milvus"
    with pytest.raises(ValueError, match="命名参数"):
        mysql.execute("SELECT %s", [1])


@pytest.mark.parametrize(
    "method,args",
    [
        ("get_edge", ["..->nodes@0", "REL"]),
        ("update_edge", ["..->nodes@0", {}, "REL"]),
        ("delete_edge", ["n->..@0"]),
    ],
)
def test_broker_rejects_path_segments_hidden_in_edge_ids(monkeypatch, method, args):
    from unittest.mock import Mock

    from service.script_resource_broker import ScriptAccessDenied, ScriptResourceBroker

    client = Mock()
    broker = object.__new__(ScriptResourceBroker)
    broker.space = "own_space"
    broker._client = lambda resource: client
    monkeypatch.setattr("service.script_resource_broker.ensure_space_access", lambda *args: None)
    with pytest.raises(ScriptAccessDenied):
        broker._graph(None, method, args, {})
    getattr(client, method).assert_not_called()
