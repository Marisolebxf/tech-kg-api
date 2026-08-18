"""service.schema_ddl 的 build_create_ddl / is_valid_data_type 单元测试。"""

from __future__ import annotations

import pytest

from service.schema_ddl import build_create_ddl, is_valid_data_type


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
