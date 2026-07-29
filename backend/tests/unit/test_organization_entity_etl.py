from __future__ import annotations

from types import SimpleNamespace

import pytest

import script.organization_entity_etl as entity
import script.organization_graph_etl as legacy


class FakeGraph:
    def __init__(self, existing: set[str] | None = None) -> None:
        self.existing = existing or set()
        self.reads: list[str] = []
        self.writes: list[str] = []

    def execute_read(self, query: str) -> SimpleNamespace:
        self.reads.append(query)
        return SimpleNamespace(
            records=[{"vid": vid} for vid in self.existing if f'"{vid}"' in query]
        )

    def execute_write(self, query: str) -> SimpleNamespace:
        self.writes.append(query)
        return SimpleNamespace(records=[])


class EmptyRows:
    def mappings(self):
        return self

    def __iter__(self):
        return iter(())


class CaptureSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def execute(self, statement, params=None):
        self.calls.append((str(statement), params or {}))
        return EmptyRows()


def test_entity_scope_contains_only_ten_organization_tables() -> None:
    names = [spec.name for spec in entity.ENTITY_TABLE_SPECS]
    assert len(names) == 10
    assert len(set(names)) == 10
    assert "dwd_org_shareholder_info" not in names
    assert {
        "dwd_org_executive_info",
        "dwd_forg_beneficiary_info",
        "dwd_org_bankruptcy_public_cases",
        "dwd_bid_base_out",
        "dwd_bid_target_item_out",
    } <= entity.TABLE_CN_NAMES.keys()


def test_missing_stable_id_is_rejected_without_name_hash_fallback() -> None:
    spec = entity.ENTITY_TABLE_BY_NAME["dwd_org_base_info"]
    with pytest.raises(entity.RelationDataError, match="stable organization id"):
        entity.vertex_from_row(
            spec,
            {"name_cn": "只有名称的机构"},
            "batch",
            "2026-07-27T00:00:00+00:00",
        )


def test_entity_vid_and_source_record_id_are_stable() -> None:
    spec = entity.ENTITY_TABLE_BY_NAME["dwd_org_base_info"]
    row = {"org_id": "o1", "name_cn": "机构一", "registered_capital_value": "100.5"}
    first = entity.vertex_from_row(spec, row, "batch", "2026-07-27T00:00:00+00:00")
    second = entity.vertex_from_row(spec, row, "batch", "2026-07-27T00:00:00+00:00")
    assert first.vid == second.vid == "org_o1"
    assert first.properties["source_record_id"] == second.properties["source_record_id"] == "o1"
    assert first.properties["registered_capital"] == 100.5


def test_entity_renderer_cannot_generate_edges() -> None:
    spec = entity.ENTITY_TABLE_BY_NAME["dwd_org_base_info"]
    record = entity.vertex_from_row(
        spec,
        {"org_id": "o1", "name_cn": "机构一"},
        "batch",
        "2026-07-27T00:00:00+00:00",
    )
    query = entity.render_vertex_insert([record])
    assert query.startswith("INSERT VERTEX `Organization`")
    assert "INSERT EDGE" not in query


def test_write_skips_existing_vid_instead_of_overwriting() -> None:
    spec = entity.ENTITY_TABLE_BY_NAME["dwd_org_base_info"]
    records = [
        entity.vertex_from_row(
            spec,
            {"org_id": org_id, "name_cn": name},
            "batch",
            "2026-07-27T00:00:00+00:00",
        )
        for org_id, name in (("o1", "已有机构"), ("o2", "新增机构"))
    ]
    graph = FakeGraph({"org_o1"})
    stats = entity.EntityStats()
    entity._write_vertex_batches(
        records,
        graph=graph,
        batch_size=10,
        dry_run=False,
        stats=stats,
    )
    assert stats.existing == 1
    assert stats.skipped == 1
    assert stats.written == 1
    assert len(graph.writes) == 1
    assert '"org_o1"' not in graph.writes[0]
    assert '"org_o2"' in graph.writes[0]


def test_entity_dry_run_never_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(entity, "source_columns", lambda session, table: {"org_id", "name_cn"})
    monkeypatch.setattr(
        entity,
        "iter_source_rows",
        lambda session, spec, max_records: iter([{"org_id": "o1", "name_cn": "机构一"}]),
    )
    monkeypatch.setattr(
        entity,
        "get_trs_graph_client",
        lambda: (_ for _ in ()).throw(AssertionError("dry-run connected to graph")),
    )
    results = entity.run_etl(
        table="dwd_org_base_info",
        full=True,
        dry_run=True,
        ingest_batch="batch",
        session=object(),
    )
    assert results["dwd_org_base_info"].valid == 1
    assert results["dwd_org_base_info"].written == 0
    assert all(
        "INSERT EDGE" not in example for item in results.values() for example in item.examples
    )


def test_legacy_graph_entry_delegates_to_entity_only(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[list[str] | None] = []
    monkeypatch.setattr(legacy, "entity_main", lambda argv=None: called.append(argv) or 0)
    assert legacy.main(["load", "--full", "--dry-run"]) == 0
    assert called == [["load", "--full", "--dry-run"]]
