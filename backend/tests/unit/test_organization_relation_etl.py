from __future__ import annotations

import json
from datetime import date, datetime
from types import SimpleNamespace

import pytest

import script.organization_entity_etl as entity
import script.organization_relation_etl as mod
from script.organization_relation_etl import (
    EdgeCandidate,
    ExactOrganizationResolver,
    RelationDataError,
    RelationStats,
    _process_candidate_batch,
    bounded_json,
    clean_text,
    extract_candidates,
    ngql_literal,
    parse_json_list,
    render_edge_insert,
    run_etl,
    stable_rank,
    to_bool,
    to_float,
    to_int,
)


class FakeGraph:
    def __init__(
        self,
        *,
        existing: dict[str, set[str]] | None = None,
        existing_edges: set[tuple[str, str, str, int]] | None = None,
        fail_writes: int = 0,
    ) -> None:
        self.existing = existing or {}
        self.existing_edges = existing_edges or set()
        self.fail_writes = fail_writes
        self.reads: list[str] = []
        self.writes: list[str] = []

    def labels(self) -> list[str]:
        return ["Organization", "Person", "Project", "Product", "News", "Event", "IndustryNode"]

    def edge_types(self) -> list[str]:
        return [
            "LEGAL_REP_OF",
            "SHAREHOLDER_OF",
            "INVESTS_IN",
            "ACQUIRES",
            "SUBSIDIARY_OF",
            "EXECUTIVE_OF",
            "BENEFICIAL_OWNER_OF",
            "ACTUAL_CONTROLLER_OF",
            "PARTICIPATES_IN",
            "FUNDED_BY",
            "HAS_NEWS",
            "INVOLVED_IN",
            "BELONGS_TO_NODE",
            "PRODUCES",
        ]

    def execute_read(self, query: str) -> SimpleNamespace:
        self.reads.append(query)
        if "RETURN id(s) AS source_vid" in query:
            records = [
                {
                    "source_vid": source_vid,
                    "target_vid": target_vid,
                    "edge_rank": rank,
                }
                for edge_type, source_vid, target_vid, rank in self.existing_edges
                if f"`{edge_type}`" in query
                and f'"{source_vid}"' in query
                and f'"{target_vid}"' in query
            ]
            return SimpleNamespace(records=records)
        tag = query.split("`", 2)[1]
        records = [
            {"vid": vid} for vid in sorted(self.existing.get(tag, set())) if f'"{vid}"' in query
        ]
        return SimpleNamespace(records=records)

    def execute_write(self, query: str) -> SimpleNamespace:
        self.writes.append(query)
        if self.fail_writes:
            self.fail_writes -= 1
            raise RuntimeError("graph unavailable")
        return SimpleNamespace(records=[])


def test_relation_entry_is_restricted_to_39_table_whitelist() -> None:
    assert {spec.source_table for spec in mod.RELATION_SPECS} <= set(mod.DOMAIN_TABLE_BY_NAME)
    assert "dwd_zh_project" not in {spec.source_table for spec in mod.RELATION_SPECS}
    assert "dwd_en_project" not in {spec.source_table for spec in mod.RELATION_SPECS}
    assert "dwd_org_industry_chain_prod_dtl" not in {
        spec.source_table for spec in mod.RELATION_SPECS
    }
    assert "project" not in mod.RELATION_KEYS
    assert "industry_node" not in mod.RELATION_KEYS


class EmptyRows:
    def mappings(self):
        return self

    def yield_per(self, size: int):
        return self

    def __iter__(self):
        return iter(())


class CaptureSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def execute(self, statement, params=None):
        self.calls.append((str(statement), params or {}))
        return EmptyRows()


def investment_spec() -> mod.RelationSpec:
    return next(spec for spec in mod.RELATION_SPECS if spec.source_table == "dwd_org_invest_info")


def investment_candidate(source: str = "org_a", target: str = "org_b") -> EdgeCandidate:
    spec = investment_spec()
    return EdgeCandidate(
        edge_type=spec.edge_type,
        source_vid=source,
        target_vid=target,
        target_tag=spec.target_tag,
        rank=stable_rank(f"{source}|{target}"),
        properties={
            "investment_amount": 10.5,
            "investment_ratio": 25.0,
            "extra_json": "{}",
            "source_table": spec.source_table,
            "source_record_id": "r1",
            "ingest_batch": "b1",
            "ingest_time": "2026-07-23T00:00:00+00:00",
        },
        source_table=spec.source_table,
        source_record_id="r1",
    )


def patch_investment_source(monkeypatch: pytest.MonkeyPatch, rows: list[dict]) -> None:
    monkeypatch.setattr(mod, "validate_source_schema", lambda session, specs: None)
    monkeypatch.setattr(
        mod.ExactOrganizationResolver,
        "load",
        classmethod(lambda cls, session: ExactOrganizationResolver({})),
    )
    monkeypatch.setattr(
        mod,
        "iter_source_rows",
        lambda session, spec, max_records: iter(rows),
    )


def test_clean_text_and_empty_handling() -> None:
    assert clean_text("  机构一  ") == "机构一"
    assert clean_text(" \n ") is None
    assert clean_text(None) is None


def test_date_and_datetime_conversion() -> None:
    assert clean_text(date(2026, 7, 23)) == "2026-07-23"
    assert clean_text(datetime(2026, 7, 23, 9, 8, 7)) == "2026-07-23 09:08:07"


def test_numeric_conversion_is_explicit() -> None:
    assert to_float("1,234.50%") == 1234.5
    assert to_int(" 12.9 ") == 12
    assert to_float("not-a-number") is None
    assert to_float(float("nan")) is None


def test_boolean_conversion_is_explicit() -> None:
    assert to_bool(" 是 ") is True
    assert to_bool("0") is False
    assert to_bool("unknown") is None


def test_ngql_string_literal_escapes_quotes_backslashes_and_newlines() -> None:
    assert ngql_literal('甲"乙\\丙\n丁') == '"甲\\"乙\\\\丙\\n丁"'


def test_rank_is_stable_positive_int64() -> None:
    value = stable_rank("same relation")
    assert value == stable_rank("same relation")
    assert 0 <= value < 2**63


def test_candidate_rank_uses_canonical_edge_identity() -> None:
    candidate = investment_candidate()
    expected = mod.edge_rank(
        candidate.edge_type,
        candidate.source_vid,
        candidate.target_vid,
        candidate.source_record_id,
    )
    rebuilt = mod._candidate(
        investment_spec(),
        candidate.source_vid,
        candidate.target_vid,
        candidate.source_record_id,
        candidate.properties,
    )
    assert rebuilt.rank == expected


def test_parse_json_list_and_invalid_json() -> None:
    assert parse_json_list('["甲", "乙"]') == ["甲", "乙"]
    assert parse_json_list(None) == []
    with pytest.raises(RelationDataError):
        parse_json_list("[not-json")


def test_overlong_extra_json_is_replaced_by_valid_bounded_audit_json() -> None:
    rendered = bounded_json({"content": "长" * 500}, max_length=120)
    parsed = json.loads(rendered)
    assert parsed["truncated"] is True
    assert parsed["original_length"] > 120
    assert len(parsed["sha256"]) == 64


def test_default_extra_json_limit_preserves_32k_source_field() -> None:
    rendered = bounded_json({"biography": "x" * 32_767})
    parsed = json.loads(rendered)
    assert parsed["biography"] == "x" * 32_767
    assert "truncated" not in parsed


def test_render_edge_keeps_schema_property_order() -> None:
    query = render_edge_insert(investment_spec(), [investment_candidate()])
    assert query.startswith(
        "INSERT EDGE `INVESTS_IN` "
        "(`investment_amount`,`investment_ratio`,`extra_json`,`source_table`,"
        "`source_record_id`,`ingest_batch`,`ingest_time`) VALUES "
    )
    assert '"org_a"->"org_b"@' in query


def test_exact_resolver_rejects_ambiguous_or_unknown_names() -> None:
    resolver = ExactOrganizationResolver({"唯一机构": {"o1"}, "重名机构": {"o2", "o3"}})
    assert resolver.resolve(" 唯一机构 ") == "o1"
    assert resolver.resolve("重名机构") is None
    assert resolver.resolve("不存在") is None


def test_governance_edges_can_end_at_organization() -> None:
    spec = next(
        spec for spec in mod.RELATION_SPECS if spec.source_table == "dwd_org_executive_info"
    )
    candidates = extract_candidates(
        spec,
        {
            "org_id": "o1",
            "executives_name": "张三",
            "executives_position": "董事",
        },
        ExactOrganizationResolver({}),
        "batch",
        "2026-07-23T00:00:00+00:00",
    )
    assert len(candidates) == 1
    assert candidates[0].source_tag == "Person"
    assert candidates[0].target_tag == "Organization"
    assert candidates[0].target_vid == "org_o1"
    assert candidates[0].properties["position"] == "董事"


def test_actual_controller_uses_explicit_organization_type_without_name_guessing() -> None:
    spec = next(
        spec for spec in mod.RELATION_SPECS if spec.source_table == "dwd_forg_act_contro_info"
    )
    candidate = extract_candidates(
        spec,
        {
            "org_id": "Target Ltd",
            "entity_eid": "controller-1",
            "entity_name": "Controller Holdings",
            "entity_type": "company",
            "direct_pct": "10",
            "total_pct": "20",
        },
        ExactOrganizationResolver({"Target Ltd": {"target-id"}}),
        "batch",
        "2026-07-23T00:00:00+00:00",
    )[0]
    assert candidate.source_tag == "Organization"
    assert candidate.source_vid == "org_controller-1"
    assert candidate.target_vid == "org_target-id"


def test_actual_controller_self_loop_is_rejected() -> None:
    spec = next(
        spec for spec in mod.RELATION_SPECS if spec.source_table == "dwd_forg_act_contro_info"
    )
    row = {
        "org_id": "Same Ltd",
        "entity_eid": None,
        "entity_name": "Same Ltd",
        "entity_type": None,
        "direct_pct": "100",
        "total_pct": "100",
    }
    with pytest.raises(RelationDataError, match="itself"):
        extract_candidates(
            spec,
            row,
            ExactOrganizationResolver({"Same Ltd": {"same-id"}}),
            "batch",
            "2026-07-23T00:00:00+00:00",
        )


def test_news_entity_and_relation_use_the_same_vid() -> None:
    row = {
        "org_id": "o1",
        "news_title": "标题",
        "news_date": "2026-07-30",
        "news_content": "正文",
        "original_textlink": "https://example.test/news/1",
    }
    entity_spec = entity.ENTITY_TABLE_BY_NAME["dwd_org_important_news_info"]
    vertex = entity.vertices_from_row(
        entity_spec,
        row,
        "batch",
        "2026-07-23T00:00:00+00:00",
    )[0]
    relation_spec = next(
        spec for spec in mod.RELATION_SPECS if spec.source_table == "dwd_org_important_news_info"
    )
    candidate = extract_candidates(
        relation_spec,
        row,
        ExactOrganizationResolver({}),
        "batch",
        "2026-07-23T00:00:00+00:00",
    )[0]
    assert vertex.vid == candidate.target_vid


def test_subsidiary_edge_direction_is_child_to_parent() -> None:
    spec = next(
        spec for spec in mod.RELATION_SPECS if spec.source_table == "dwd_forg_subsidiary_info"
    )
    candidate = extract_candidates(
        spec,
        {
            "org_id": "parent",
            "affiliate": "child",
            "affiliates_company_id": "child",
            "affiliates_name": "Child Ltd",
        },
        ExactOrganizationResolver({}),
        "batch",
        "2026-07-23T00:00:00+00:00",
    )[0]
    assert candidate.source_vid == "org_child"
    assert candidate.target_vid == "org_parent"


def test_duplicate_candidates_are_removed_before_write() -> None:
    graph = FakeGraph(existing={"Organization": {"org_a", "org_b"}})
    candidate = investment_candidate()
    stats = RelationStats()
    _process_candidate_batch(
        investment_spec(),
        [candidate, candidate],
        graph=graph,
        batch_size=10,
        dry_run=False,
        stats=stats,
    )
    assert stats.duplicate == 1
    assert stats.written == 1
    assert len(graph.writes) == 1


def test_existing_graph_edge_is_refreshed_at_the_same_stable_rank() -> None:
    candidate = investment_candidate()
    graph = FakeGraph(
        existing={"Organization": {"org_a", "org_b"}},
        existing_edges={candidate.identity},
    )
    stats = RelationStats()
    _process_candidate_batch(
        investment_spec(),
        [candidate],
        graph=graph,
        batch_size=10,
        dry_run=False,
        stats=stats,
    )
    assert stats.existing == 1
    assert stats.skipped == 0
    assert stats.written == 0
    assert stats.updated == 1
    assert len(graph.writes) == 1


def test_missing_source_and_target_are_counted_and_skipped() -> None:
    graph = FakeGraph(existing={"Organization": set()})
    stats = RelationStats()
    _process_candidate_batch(
        investment_spec(),
        [investment_candidate()],
        graph=graph,
        batch_size=10,
        dry_run=False,
        stats=stats,
    )
    assert stats.source_missing == 1
    assert stats.target_missing == 1
    assert stats.skipped == 1
    assert graph.writes == []


def test_dry_run_never_calls_execute_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_investment_source(
        monkeypatch,
        [
            {
                "org_id": "a",
                "inv_org_id": "b",
                "investment_amount": "100",
                "investment_ratio": "20",
            }
        ],
    )
    graph = FakeGraph(existing={"Organization": {"org_a", "org_b"}})
    result = run_etl(
        relation="investment",
        batch_size=10,
        dry_run=True,
        graph=graph,
        session=object(),
        ingest_batch="test",
    )
    stats = result["dwd_org_invest_info"]
    assert stats.valid == 1
    assert stats.written == 0
    assert graph.writes == []
    assert stats.examples


def test_batch_insert_and_graph_failure_are_isolated() -> None:
    graph = FakeGraph(
        existing={"Organization": {"org_a", "org_b", "org_c"}},
        fail_writes=1,
    )
    stats = RelationStats()
    _process_candidate_batch(
        investment_spec(),
        [
            investment_candidate("org_a", "org_b"),
            investment_candidate("org_a", "org_c"),
        ],
        graph=graph,
        batch_size=1,
        dry_run=False,
        stats=stats,
    )
    assert len(graph.writes) == 2
    assert stats.failed == 1
    assert stats.written == 1


def test_dirty_row_does_not_block_later_valid_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_investment_source(
        monkeypatch,
        [
            {"org_id": None, "inv_org_id": "b"},
            {
                "org_id": "a",
                "inv_org_id": "b",
                "investment_amount": "100",
                "investment_ratio": "20",
            },
        ],
    )
    graph = FakeGraph(existing={"Organization": {"org_a", "org_b"}})
    result = run_etl(
        relation="investment",
        batch_size=10,
        dry_run=False,
        graph=graph,
        session=object(),
        ingest_batch="test",
    )
    stats = result["dwd_org_invest_info"]
    assert stats.queried == 2
    assert stats.invalid == 1
    assert stats.written == 1


def test_foreign_shareholder_can_use_contextual_hybrid_resolution() -> None:
    spec = next(
        item for item in mod.RELATION_SPECS if item.source_table == "dwd_forg_shareholder_info"
    )

    class HybridResolver:
        def __init__(self) -> None:
            self.context: dict | None = None

        def resolve(self, name, context=None):
            if name == "Alpha Holdings Limited":
                self.context = context
                return "alpha-holdings"
            return None

    resolver = HybridResolver()
    candidates = extract_candidates(
        spec,
        {
            "org_id": "target-company",
            "owners_name": "Alpha Holdings Limited",
            "owners_country_code": "GB",
            "ownership_percentage": "51.5",
        },
        resolver,
        "test",
        "2026-07-30T00:00:00+00:00",
    )
    assert len(candidates) == 1
    assert candidates[0].source_vid == "org_alpha-holdings"
    assert candidates[0].target_vid == "org_target-company"
    assert candidates[0].properties["ownership_percentage"] == 51.5
    assert resolver.context is not None
    assert resolver.context["country_code"] == "GB"
    assert resolver.context["source_table"] == "dwd_forg_shareholder_info"


def test_stable_organization_id_bypasses_hybrid_alignment() -> None:
    spec = investment_spec()

    class ResolverMustNotRun:
        def resolve(self, name, context=None):
            raise AssertionError("stable organization IDs must not invoke fuzzy alignment")

    candidates = extract_candidates(
        spec,
        {
            "org_id": "investor-id",
            "inv_org_id": "target-id",
            "investment_amount": "100",
            "investment_ratio": "10",
        },
        ResolverMustNotRun(),
        "test",
        "2026-07-30T00:00:00+00:00",
    )
    assert candidates[0].source_vid == "org_investor-id"
    assert candidates[0].target_vid == "org_target-id"
