from __future__ import annotations

from types import SimpleNamespace

import pytest

import script.organization_entity_etl as entity
import script.organization_graph_etl as legacy


class FakeGraph:
    def __init__(self, existing: dict[str, dict] | set[str] | None = None) -> None:
        if isinstance(existing, set):
            self.existing = {vid: {} for vid in existing}
        else:
            self.existing = existing or {}
        self.reads: list[str] = []
        self.writes: list[str] = []

    def execute_read(self, query: str) -> SimpleNamespace:
        self.reads.append(query)
        return SimpleNamespace(
            records=[
                {"vid": vid, "props": props}
                for vid, props in self.existing.items()
                if f'"{vid}"' in query
            ]
        )

    def execute_write(self, query: str) -> SimpleNamespace:
        self.writes.append(query)
        return SimpleNamespace(records=[])


class SizeLimitedGraph(FakeGraph):
    def execute_write(self, query: str) -> SimpleNamespace:
        self.writes.append(query)
        if query.count('":(') > 1:
            raise RuntimeError("request too large")
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


def test_entity_scope_is_restricted_to_node_producing_tables_in_39_table_whitelist() -> None:
    names = [spec.name for spec in entity.ENTITY_TABLE_SPECS]
    assert {
        "dwd_org_base_info",
        "dwd_org_shareholder_info",
        "dwd_org_executive_info",
        "dwd_forg_beneficiary_info",
        "dwd_org_bankruptcy_public_cases",
        "dwd_bid_base_out",
        "dwd_bid_target_item_out",
    } <= set(names)
    assert len(names) == len(set(names))
    assert "dwd_org_merger_acquisition_info" not in names
    assert "dwd_zh_project" not in names
    assert "dwd_en_project" not in names
    assert set(names) <= {spec.name for spec in entity.DOMAIN_TABLE_SPECS}
    assert len(entity.TABLE_CN_NAMES) == 39


def test_run_etl_can_select_domestic_or_foreign_source_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(entity, "iter_source_rows", lambda *args, **kwargs: iter(()))
    domestic = entity.run_etl(
        full=True,
        domestic_only=True,
        dry_run=True,
        session=CaptureSession(),
    )
    foreign = entity.run_etl(
        full=True,
        foreign_only=True,
        dry_run=True,
        session=CaptureSession(),
    )
    assert set(domestic) == {
        "DataSource",
        *(spec.name for spec in entity.ENTITY_TABLE_SPECS if spec.scope == "domestic"),
    }
    assert set(foreign) == {
        "DataSource",
        *(spec.name for spec in entity.ENTITY_TABLE_SPECS if spec.scope == "foreign"),
    }


def test_entity_scope_flags_are_mutually_exclusive() -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        entity.run_etl(
            full=True,
            domestic_only=True,
            foreign_only=True,
            dry_run=True,
            session=CaptureSession(),
        )


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
    assert first.properties["organization_id"] == "o1"
    assert 0.0 <= first.properties["confidence"] <= 1.0


def test_person_event_project_and_product_vertices_keep_full_raw_payload() -> None:
    executive = entity.vertices_from_row(
        entity.ENTITY_TABLE_BY_NAME["dwd_org_executive_info"],
        {
            "org_id": "o1",
            "executives_name": "张三",
            "executives_position": "董事",
            "custom_long_tail": "保留",
        },
        "batch",
        "2026-07-27T00:00:00+00:00",
    )
    assert executive[0].tag == "Person"
    assert "custom_long_tail" in executive[0].properties["extra_json"]

    event = entity.vertices_from_row(
        entity.ENTITY_TABLE_BY_NAME["dwd_org_company_punish"],
        {"org_id": "o1", "penalty_id": "e1", "penalty_content": "处罚内容"},
        "batch",
        "2026-07-27T00:00:00+00:00",
    )
    assert event[0].tag == "Event"

    product_records = entity.vertices_from_row(
        entity.ENTITY_TABLE_BY_NAME["dwd_org_org_product_info"],
        {"org_id": "o1", "main_prod": "量子芯片", "description": "产品说明"},
        "batch",
        "2026-07-27T00:00:00+00:00",
    )
    assert {record.tag for record in product_records} == {
        "Organization",
        "organization_base",
        "Product",
    }
    provenance = next(record for record in product_records if record.tag == "organization_base")
    assert provenance.properties["organization_id"] == "o1"


def test_bid_target_items_with_same_notice_keep_distinct_payloads() -> None:
    spec = entity.ENTITY_TABLE_BY_NAME["dwd_bid_target_item_out"]
    first = entity.vertices_from_row(
        spec,
        {
            "u_id": "notice-1",
            "target_item_name": "服务器",
            "bid_section_number": "A",
        },
        "batch",
        "2026-07-27T00:00:00+00:00",
    )[0]
    second = entity.vertices_from_row(
        spec,
        {
            "u_id": "notice-1",
            "target_item_name": "存储设备",
            "bid_section_number": "B",
        },
        "batch",
        "2026-07-27T00:00:00+00:00",
    )[0]
    assert first.vid != second.vid
    assert "服务器" in first.properties["extra_json"]
    assert "存储设备" in second.properties["extra_json"]


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


def test_schema_initializer_skips_standalone_use_statement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = FakeGraph()
    monkeypatch.setattr(
        entity,
        "split_schema_statements",
        lambda source: ["USE dev;", "CREATE TAG IF NOT EXISTS `Product`(`name` string NULL);"],
    )
    monkeypatch.setattr(entity, "reconcile_existing_schema", lambda client: None)
    entity.initialize_schema(graph)
    assert graph.writes == ["CREATE TAG IF NOT EXISTS `Product`(`name` string NULL);"]


def test_write_merges_payload_without_overwriting_existing_canonical_value() -> None:
    spec = entity.ENTITY_TABLE_BY_NAME["dwd_org_base_info"]
    records = [
        entity.vertex_from_row(
            spec,
            {"org_id": org_id, "name_cn": name},
            "batch",
            "2026-07-27T00:00:00+00:00",
        )
        for org_id, name in (("o1", "试图覆盖"), ("o2", "新增机构"))
    ]
    graph = FakeGraph(
        {
            "org_o1": {
                "org_id": "o1",
                "name_cn": "已有机构",
                "extra_json": '{"legacy":"保留"}',
            }
        }
    )
    stats = entity.EntityStats()
    entity._write_vertex_batches(
        records,
        graph=graph,
        batch_size=10,
        dry_run=False,
        stats=stats,
    )
    assert stats.existing == 1
    assert stats.updated == 1
    assert stats.skipped == 0
    assert stats.written == 1
    assert len(graph.writes) == 2
    update = next(query for query in graph.writes if '"org_o1"' in query)
    assert "`name_cn`" in update.split("VALUES", 1)[0]
    assert "已有机构" in update
    assert "source_records" in update
    assert any('"org_o2"' in query for query in graph.writes)


def test_failed_vertex_batch_is_split_until_individual_rows_succeed() -> None:
    spec = entity.ENTITY_TABLE_BY_NAME["dwd_org_base_info"]
    records = [
        entity.vertex_from_row(
            spec,
            {"org_id": f"o{index}", "name_cn": f"机构{index}"},
            "batch",
            "2026-07-27T00:00:00+00:00",
        )
        for index in range(3)
    ]
    graph = SizeLimitedGraph()
    stats = entity.EntityStats()
    entity._write_vertex_batches(
        records,
        graph=graph,
        batch_size=10,
        dry_run=False,
        stats=stats,
    )
    assert stats.written == 3
    assert stats.failed == 0
    assert len(graph.writes) > 3


def test_full_payload_replaces_obsolete_truncated_audit_summary() -> None:
    merged = entity.merge_existing_properties(
        {
            "extra_json": (
                '{"truncated":true,"sha256":"old","original_length":32767,"preview":"partial"}'
            )
        },
        {
            "extra_json": '{"dm_biography":"complete"}',
            "source_table": "dwd_forg_executive_info",
            "source_record_id": "r1",
        },
    )
    payload = entity._json_object(merged["extra_json"])
    assert "existing_payload" not in payload
    assert payload["source_records"]["dwd_forg_executive_info:r1"]["dm_biography"] == "complete"


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
    assert results["dwd_org_base_info"].valid == 2
    assert results["dwd_org_base_info"].written == 0
    assert all(
        "INSERT EDGE" not in example for item in results.values() for example in item.examples
    )


def test_legacy_graph_entry_delegates_to_entity_only(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[list[str] | None] = []
    monkeypatch.setattr(legacy, "entity_main", lambda argv=None: called.append(argv) or 0)
    assert legacy.main(["load", "--full", "--dry-run"]) == 0
    assert called == [["load", "--full", "--dry-run"]]
