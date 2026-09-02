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
