"""service.schema_ddl 的 build_create_ddl / alter add/drop / DESCRIBE 单元测试。"""

from __future__ import annotations

import pytest

from infra.graph_db.exceptions import GraphRequestError
from service.schema_ddl import (
    build_alter_add_ddl,
    build_alter_drop_ddl,
    build_create_ddl,
    describe_schema_columns,
    is_valid_data_type,
    run_alter_drop_ddl,
)


def test_build_create_tag() -> None:
    ddl = build_create_ddl(
        "entity",
        "Scholar",
        [
            {"name": "scholar_id", "data_type": "string", "required": True},
            {"name": "h_index", "data_type": "int64", "required": False},
        ],
    )
    assert ddl == ("CREATE TAG IF NOT EXISTS Scholar(scholar_id string NOT NULL, h_index int64);")


def test_build_create_edge() -> None:
    ddl = build_create_ddl(
        "relation",
        "EMPLOYED_BY",
        [
            {"name": "role", "data_type": "string", "required": False},
            {"name": "relation_type", "data_type": "fixed_string(32)", "required": True},
        ],
    )
    assert ddl == (
        "CREATE EDGE IF NOT EXISTS EMPLOYED_BY"
        "(role string, relation_type fixed_string(32) NOT NULL);"
    )


def test_build_create_with_no_properties() -> None:
    ddl = build_create_ddl("entity", "Empty", [])
    assert ddl == "CREATE TAG IF NOT EXISTS Empty();"


def test_build_create_with_various_types() -> None:
    ddl = build_create_ddl(
        "entity",
        "Mixed",
        [
            {"name": "a", "data_type": "double", "required": False},
            {"name": "b", "data_type": "bool", "required": True},
            {"name": "c", "data_type": "date", "required": False},
            {"name": "d", "data_type": "datetime", "required": False},
            {"name": "e", "data_type": "geo", "required": False},
        ],
    )
    assert ddl == (
        "CREATE TAG IF NOT EXISTS Mixed(a double, b bool NOT NULL, c date, d datetime, e geo);"
    )


@pytest.mark.parametrize(
    "data_type",
    [
        "string",
        "int64",
        "double",
        "bool",
        "date",
        "datetime",
        "geo",
        "fixed_string(1)",
        "fixed_string(256)",
    ],
)
def test_is_valid_data_type_accepts(data_type: str) -> None:
    assert is_valid_data_type(data_type) is True


@pytest.mark.parametrize(
    "data_type",
    [
        "foo",
        "int",
        "varchar(10)",
        "FIXED_STRING(10)",
        "fixed_string",
        "fixed_string()",
        "fixed_string(-1)",
        "string ",
    ],
)
def test_is_valid_data_type_rejects(data_type: str) -> None:
    assert is_valid_data_type(data_type) is False


def test_build_alter_drop_tag() -> None:
    assert build_alter_drop_ddl("entity", "Scholar", "h_index") == (
        "ALTER TAG Scholar DROP (h_index);"
    )


def test_build_alter_drop_edge() -> None:
    assert build_alter_drop_ddl("relation", "EMPLOYED_BY", "role") == (
        "ALTER EDGE EMPLOYED_BY DROP (role);"
    )


def test_alter_add_drop_symmetry() -> None:
    add = build_alter_add_ddl("entity", "Scholar", {"name": "rank", "data_type": "int64"})
    drop = build_alter_drop_ddl("entity", "Scholar", "rank")
    assert add == "ALTER TAG Scholar ADD (rank int64);"
    assert drop == "ALTER TAG Scholar DROP (rank);"


def test_run_alter_drop_ddl_wraps_execute(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    def fake_execute(ddl: str, graph_space: str | None = None):
        captured["ddl"] = ddl
        return "succeeded", None

    monkeypatch.setattr("service.schema_ddl.execute_schema_ddl", fake_execute)
    result = run_alter_drop_ddl("relation", "EMPLOYED_BY", "role")
    assert captured["ddl"] == "ALTER EDGE EMPLOYED_BY DROP (role);"
    assert result["status"] == "succeeded"
    assert result["error"] is None
    assert result["executed_at"] is not None


class _FakeQueryResult:
    def __init__(self, records: list[dict]) -> None:
        self.records = records


class _DescribeClient:
    def __init__(self, records=None, error: Exception | None = None) -> None:
        self.records = records
        self.error = error

    def execute_query(self, query: str):
        if self.error:
            raise self.error
        return _FakeQueryResult(self.records or [])


def test_describe_schema_columns_parses_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _DescribeClient(
        records=[
            {"Field": "id", "Type": "string"},
            {"Field": "name", "Type": "string"},
            {"Field": "rank", "Type": "int64"},
        ]
    )
    monkeypatch.setattr("service.schema_ddl.get_trs_graph_client", lambda: client)
    assert describe_schema_columns("entity", "Scholar") == ["id", "name", "rank"]


def test_describe_schema_columns_missing_schema_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _DescribeClient(error=GraphRequestError("Tag not found", status_code=400))
    monkeypatch.setattr("service.schema_ddl.get_trs_graph_client", lambda: client)
    assert describe_schema_columns("entity", "Missing") is None


class _FakeGraphClient:
    """delete_schema_graph_data 单测桩：SHOW/分页枚举/批量 DELETE。"""

    def __init__(self, *, tags=None, edges=None, nodes_by_label=None, edges_by_type=None):
        self.tags = tags if tags is not None else []
        self.edges_types = edges if edges is not None else []
        self.nodes_by_label = nodes_by_label if nodes_by_label is not None else {}
        self.edges_by_type = edges_by_type if edges_by_type is not None else {}
        self.writes: list[str] = []

    def execute_query(self, query: str):
        if query == "SHOW TAGS;":
            return _FakeQueryResult([{"Name": name} for name in self.tags])
        if query == "SHOW EDGES;":
            return _FakeQueryResult([{"Name": name} for name in self.edges_types])
        return _FakeQueryResult([])

    def execute_write(self, query: str):
        self.writes.append(query)
        # DELETE 语句里出现的点/边从枚举池移除，模拟删除生效
        if query.startswith("DELETE VERTEX "):
            vids = {
                token.strip().rstrip(";").strip('"')
                for token in query[len("DELETE VERTEX ") :].split(", ")
            }
            for label, nodes in self.nodes_by_label.items():
                self.nodes_by_label[label] = [n for n in nodes if str(n.id) not in vids]
        elif query.startswith("DELETE EDGE "):
            for edge_type in self.edges_by_type:
                self.edges_by_type[edge_type] = []

    def get_nodes_by_label(self, label: str, *, limit: int = 100, offset: int = 0):
        from infra.graph_db.models import GraphPagedResult

        return GraphPagedResult(
            items=self.nodes_by_label.get(label, [])[:limit],
            total=len(self.nodes_by_label.get(label, [])),
        )

    def get_edges_by_type(self, edge_type: str, *, limit: int = 100, offset: int = 0):
        from infra.graph_db.models import GraphPagedResult

        items = self.edges_by_type.get(edge_type, [])[:limit]
        return GraphPagedResult(items=items, total=len(self.edges_by_type.get(edge_type, [])))


def _patch_drop(monkeypatch: pytest.MonkeyPatch, client: _FakeGraphClient):
    captured: dict[str, str] = {}

    def fake_execute(ddl: str, graph_space: str | None = None):
        captured["ddl"] = ddl
        client.execute_write(ddl)
        return "succeeded", None

    monkeypatch.setattr("service.schema_ddl.execute_schema_ddl", fake_execute)
    return captured


def test_delete_schema_graph_data_entity(monkeypatch: pytest.MonkeyPatch) -> None:
    from infra.graph_db.models import GraphNode
    from service.schema_ddl import delete_schema_graph_data

    client = _FakeGraphClient(
        tags=["Scholar", "Expert"],
        nodes_by_label={"Expert": [GraphNode(id="v1"), GraphNode(id="v2"), GraphNode(id="v3")]},
    )
    monkeypatch.setattr("service.schema_ddl.get_trs_graph_client", lambda: client)
    captured = _patch_drop(monkeypatch, client)

    result = delete_schema_graph_data("entity", "Expert")
    assert result["status"] == "succeeded"
    assert result["typeExisted"] is True
    assert result["verticesDeleted"] == 3
    assert result["dropStatement"] == "DROP TAG IF EXISTS Expert;"
    assert captured["ddl"] == "DROP TAG IF EXISTS Expert;"
    assert client.writes[0] == 'DELETE VERTEX "v1", "v2", "v3";'
    assert client.nodes_by_label["Expert"] == []


def test_delete_schema_graph_data_edge(monkeypatch: pytest.MonkeyPatch) -> None:
    from infra.graph_db.models import GraphEdge
    from service.schema_ddl import delete_schema_graph_data

    client = _FakeGraphClient(
        edges=["EMPLOYED_BY"],
        edges_by_type={
            "EMPLOYED_BY": [
                GraphEdge(id="s1->t1@0", type="EMPLOYED_BY", source_id="s1", target_id="t1"),
                GraphEdge(id="s2->t2@3", type="EMPLOYED_BY", source_id="s2", target_id="t2"),
            ]
        },
    )
    monkeypatch.setattr("service.schema_ddl.get_trs_graph_client", lambda: client)
    captured = _patch_drop(monkeypatch, client)

    result = delete_schema_graph_data("relation", "EMPLOYED_BY")
    assert result["status"] == "succeeded"
    assert result["edgesDeleted"] == 2
    assert captured["ddl"] == "DROP EDGE IF EXISTS EMPLOYED_BY;"
    assert client.writes[0] == 'DELETE EDGE EMPLOYED_BY "s1" -> "t1"@0, "s2" -> "t2"@3;'


def test_delete_schema_graph_data_type_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    from service.schema_ddl import delete_schema_graph_data

    client = _FakeGraphClient(tags=["Scholar"])
    monkeypatch.setattr("service.schema_ddl.get_trs_graph_client", lambda: client)
    captured = _patch_drop(monkeypatch, client)

    result = delete_schema_graph_data("entity", "Ghost")
    assert result["status"] == "succeeded"
    assert result["typeExisted"] is False
    assert result["verticesDeleted"] == 0
    assert "ddl" not in captured  # 无类型可 DROP


def test_delete_schema_graph_data_delete_not_taking_effect(monkeypatch) -> None:
    """删除未生效（枚举结果不变）→ 报错退出而非死循环。"""
    from infra.graph_db.models import GraphNode
    from service.schema_ddl import delete_schema_graph_data

    class _StuckClient(_FakeGraphClient):
        def execute_write(self, query: str):
            self.writes.append(query)  # 记录但不移除任何点（模拟删除失效）

    client = _StuckClient(tags=["Expert"], nodes_by_label={"Expert": [GraphNode(id="v1")]})
    monkeypatch.setattr("service.schema_ddl.get_trs_graph_client", lambda: client)
    _patch_drop(monkeypatch, client)

    result = delete_schema_graph_data("entity", "Expert")
    assert result["status"] == "failed"
    assert "未生效" in result["error"]
