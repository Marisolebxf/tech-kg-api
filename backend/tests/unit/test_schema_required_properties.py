"""公共必选属性注入单测：注入顺序 / 去重 / 用户覆盖 / DDL 包含公共属性。"""

from __future__ import annotations

from biz.schemas.schema_management import SchemaPropertyInput
from service.schema_ddl import build_create_ddl
from service.schema_management import (
    _inject_provenance_properties,
    _inject_required_properties,
)


def _names(payload: dict) -> list[str]:
    return [p["name"] for p in payload["properties"]]


def test_entity_required_properties_injected_at_head() -> None:
    payload = {
        "properties": [
            {
                "name": "foo",
                "data_type": "string",
                "required": False,
                "rule": "",
                "category": "core",
            }
        ]
    }
    _inject_required_properties("entity", payload)
    assert _names(payload)[:5] == ["id", "name", "create_time", "update_time", "source_table"]
    for prop in payload["properties"][:5]:
        assert prop["required"] is True
        assert prop["category"] == "required"
        assert prop["data_type"] == "string"
    assert _names(payload)[5:] == ["foo"]


def test_relation_required_properties_injected() -> None:
    payload = {"properties": []}
    _inject_required_properties("relation", payload)
    assert _names(payload) == ["create_time", "update_time", "source_table"]
    for prop in payload["properties"]:
        assert prop["required"] is True
        assert prop["category"] == "required"


def test_user_declared_property_upgraded_not_duplicated() -> None:
    payload = {
        "properties": [
            {
                "name": "name",
                "data_type": "int64",
                "required": False,
                "rule": "",
                "category": "core",
            },
            {
                "name": "custom",
                "data_type": "string",
                "required": False,
                "rule": "",
                "category": "core",
            },
        ]
    }
    _inject_required_properties("entity", payload)
    names = _names(payload)
    assert names.count("name") == 1
    declared = payload["properties"][4]
    assert declared["name"] == "name"
    assert declared["data_type"] == "int64"  # 保留用户口径
    assert declared["required"] is True
    assert declared["category"] == "required"
    # 缺失项插在头部，顺序保持
    assert names[:4] == ["id", "create_time", "update_time", "source_table"]
    assert names[5:] == ["custom"]


def test_source_table_shared_dedup_with_provenance(monkeypatch) -> None:
    monkeypatch.setenv("SCHEMA_AUTO_PROVENANCE", "true")
    payload = {
        "properties": [
            {
                "name": "foo",
                "data_type": "string",
                "required": False,
                "rule": "",
                "category": "core",
            }
        ]
    }
    _inject_required_properties("entity", payload)
    _inject_provenance_properties("entity", payload)
    names = _names(payload)
    assert names.count("source_table") == 1
    source_table = next(p for p in payload["properties"] if p["name"] == "source_table")
    assert source_table["required"] is True
    assert source_table["category"] == "required"


def test_create_ddl_contains_required_properties() -> None:
    payload = {
        "properties": [
            {
                "name": "technology_id",
                "data_type": "string",
                "required": True,
                "rule": "",
                "category": "core",
            }
        ]
    }
    _inject_required_properties("entity", payload)
    ddl = build_create_ddl("entity", "Technology", payload["properties"])
    assert "id string NOT NULL" in ddl
    assert "name string NOT NULL" in ddl
    assert "create_time string NOT NULL" in ddl
    assert "update_time string NOT NULL" in ddl
    assert "source_table string NOT NULL" in ddl

    _inject_required_properties("relation", payload := {"properties": []})
    edge_ddl = build_create_ddl("relation", "USES_TECHNOLOGY", payload["properties"])
    assert "create_time string NOT NULL" in edge_ddl


def test_schema_property_input_accepts_required_category() -> None:
    prop = SchemaPropertyInput(
        name="create_time", data_type="string", required=True, category="required"
    )
    assert prop.category == "required"
