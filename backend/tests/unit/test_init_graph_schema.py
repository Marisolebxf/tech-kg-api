from __future__ import annotations

from script.init_graph_schema import CREATE_SPACE_DDL, SCHEMA_DDL


def test_ddl_contains_tags_and_edge():
    joined = "\n".join(CREATE_SPACE_DDL + SCHEMA_DDL)
    assert "CREATE SPACE IF NOT EXISTS techkg" in joined
    assert "CREATE TAG IF NOT EXISTS Scholar(" in joined
    assert "CREATE TAG IF NOT EXISTS Organization(" in joined
    assert "CREATE EDGE IF NOT EXISTS EMPLOYED_BY(" in joined
    assert "scholar_id string" in joined
    assert "name_cn string" in joined
    assert "relation_type string" in joined
