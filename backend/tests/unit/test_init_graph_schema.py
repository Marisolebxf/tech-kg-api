from __future__ import annotations

from unittest.mock import MagicMock

from script import init_graph_schema


def test_ddl_contains_tags_and_edge():
    joined = "\n".join(init_graph_schema.CREATE_SPACE_DDL + init_graph_schema.SCHEMA_DDL)
    assert "CREATE SPACE IF NOT EXISTS techkg" in joined
    assert "CREATE TAG IF NOT EXISTS Scholar(" in joined
    assert "CREATE TAG IF NOT EXISTS Organization(" in joined
    assert "CREATE EDGE IF NOT EXISTS EMPLOYED_BY(" in joined
    assert "scholar_id string" in joined
    assert "name_cn string" in joined
    assert "relation_type string" in joined


def test_schema_ddl_includes_tech_field_alter():
    stmts = " ".join(init_graph_schema.SCHEMA_DDL)
    assert "ALTER EDGE" in stmts
    assert "tech_field" in stmts


def test_init_schema_runs_alter(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(init_graph_schema, "TRSGraphClient", lambda *a, **k: client)
    monkeypatch.setattr(init_graph_schema, "TRSGraphSettings", MagicMock())
    init_graph_schema.init_schema()
    executed = " ".join(c.args[0] for c in client.execute_write.call_args_list)
    assert "ALTER EDGE" in executed
