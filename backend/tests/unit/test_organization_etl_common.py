from __future__ import annotations

from pathlib import Path

import pytest

import script.organization_etl_common as common
import script.organization_relation_etl as relation


def test_relation_pipeline_uses_the_shared_spec_object() -> None:
    assert relation.RELATION_SPECS is common.RELATION_SPECS
    assert relation.RELATION_KEYS is common.RELATION_KEYS


def test_one_canonical_schema_covers_all_relation_specs() -> None:
    schema = common.SCHEMA_PATH.read_text(encoding="utf-8")
    assert "CREATE TAG IF NOT EXISTS `Organization`" in schema
    assert "CREATE TAG IF NOT EXISTS `DataSource`" in schema
    for spec in common.RELATION_SPECS:
        assert f"CREATE EDGE IF NOT EXISTS `{spec.edge_type}`" in schema
        for property_name in spec.edge_properties:
            assert f"`{property_name}`" in schema
    for deprecated_name in (
        "dev_organization_graph.ngql",
        "dev_organization_relations.ngql",
    ):
        deprecated = common.SCHEMA_PATH.with_name(deprecated_name).read_text(encoding="utf-8")
        assert "CREATE TAG" not in deprecated
        assert "CREATE EDGE" not in deprecated


def test_source_record_id_and_rank_are_canonical_and_deterministic() -> None:
    row = {"org_id": "a", "inv_org_id": "b", "amount": 10}
    record_id = common.stable_record_id(
        "dwd_org_invest_info",
        row,
        ("org_id", "inv_org_id"),
    )
    assert record_id == "a|b"
    rank = common.edge_rank("INVESTS_IN", "org_a", "org_b", record_id)
    assert rank == common.edge_rank("INVESTS_IN", "org_a", "org_b", record_id)
    assert 0 <= rank < 2**63


def test_entity_and_relation_processes_share_one_exclusive_lock(tmp_path: Path) -> None:
    lock_path = tmp_path / "organization.lock"
    with common.exclusive_etl_lock("entity", "entity_batch", lock_path=lock_path):
        with pytest.raises(RuntimeError, match="another organization ETL"):
            with common.exclusive_etl_lock(
                "relation",
                "relation_batch",
                lock_path=lock_path,
            ):
                pass
