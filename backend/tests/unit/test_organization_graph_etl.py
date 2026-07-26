from script.organization_graph_etl import (
    TABLE_SPECS,
    GraphBuffer,
    TableSpec,
    bounded_vid,
    ngql_literal,
    stable_rank,
    transform_row,
)


def test_scope_contains_exactly_39_unique_tables() -> None:
    names = [spec.name for spec in TABLE_SPECS]
    assert len(names) == 39
    assert len(set(names)) == 39


def test_vid_obeys_dev_fixed_string_64_bytes() -> None:
    value = bounded_vid("机构" * 100)
    assert len(value.encode("utf-8")) <= 64
    assert value == bounded_vid("机构" * 100)


def test_rank_is_deterministic_positive_int64() -> None:
    first = stable_rank("same-edge")
    assert first == stable_rank("same-edge")
    assert 0 <= first < 2**63


def test_ngql_literal_escapes_quotes_and_newlines() -> None:
    literal = ngql_literal('甲"乙\n丙')
    assert literal == '"甲\\"乙\\n丙"'


def test_shareholder_direction_is_shareholder_to_company() -> None:
    buffer = GraphBuffer(ingest_batch="test", ingest_time="2026-07-21 00:00:00")
    spec = TableSpec("dwd_org_shareholder_info", "股东", "relation", "SHAREHOLDER_OF")
    transform_row(
        spec,
        {
            "org_id": "target-company",
            "name_cn": "目标公司",
            "inv_org_id": "shareholder-company",
            "owners_name": "股东公司",
            "owners_type": "企业",
            "ownership_percentage": "25.5%",
            "data_source": "MOCK_TEST",
        },
        buffer,
    )
    edge = next(item for item in buffer.edges.values() if item.edge_type == "SHAREHOLDER_OF")
    assert edge.source == "org_shareholder-company"
    assert edge.target == "org_target-company"
    assert edge.props["ownership_percentage"] == 25.5


def test_repeated_transform_is_idempotent() -> None:
    buffer = GraphBuffer(ingest_batch="test", ingest_time="2026-07-21 00:00:00")
    spec = TableSpec("dwd_org_executive_info", "高管", "relation", "EXECUTIVE_OF")
    row = {
        "org_id": "o1",
        "name_cn": "机构一",
        "executives_name": "张三",
        "executives_position": "董事",
        "data_source": "MOCK_TEST",
    }
    transform_row(spec, row, buffer)
    counts = (len(buffer.nodes), len(buffer.edges))
    transform_row(spec, row, buffer)
    assert (len(buffer.nodes), len(buffer.edges)) == counts
