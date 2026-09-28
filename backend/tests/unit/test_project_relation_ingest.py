from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from script.load_project_graph import (
    _merge_edge,
    stage_outputs,
    stage_project_relations,
)
from script.project_entity_matcher import (
    ExactIndex,
    ProjectEntityMatcher,
    normalize_doi,
    normalize_patent_number,
    normalize_text,
)
from script.project_ingest_report import ProjectIngestReport


def test_normalizers():
    assert normalize_text("  A   B ") == "a b"
    assert normalize_doi(" HTTPS://DOI.ORG/10.1/X ") == "10.1/x"
    assert normalize_patent_number("cn 2024-01.2") == "CN2024012"


def test_exact_index_requires_unique_match():
    index = ExactIndex()
    index.add("张伟", "person_1")
    assert index.match(" 张伟 ", method="name_exact").vid == "person_1"
    index.add("张伟", "person_2")
    assert index.match("张伟", method="name_exact").status == "ambiguous"
    assert index.match("不存在", method="name_exact").status == "not_found"


def _report(tmp_path):
    return ProjectIngestReport(tmp_path, ingest_batch="BATCH_TEST", dry_run=False)


def test_project_relations_only_write_project_origin_edges(tmp_path):
    graph = MagicMock()
    matcher = ProjectEntityMatcher()
    matcher.organization.add("清华大学", "org_1")
    matcher.organization_ids["org_1"] = "1"
    matcher.person.add("张伟", "person_1")
    row = SimpleNamespace(
        id="p1",
        funded_institution="清华大学",
        funded_amount=10,
        fund_category="面上",
        project_host="张伟",
        participants='["张伟", "未匹配人员"]',
        participating_institution='["北京大学"]',
    )
    report = _report(tmp_path)

    stage_project_relations(
        graph,
        [(row, "zh_project", "dwd_zh_project")],
        matcher,
        report,
        ingest_batch="BATCH_TEST",
        ingest_time="2026-07-26 20:00:00",
        dry_run=False,
    )

    edge_types = [call.args[2] for call in graph.merge_edge.call_args_list]
    assert edge_types == ["FUNDED_BY", "LEADS", "HAS_PARTICIPANT"]
    funded = graph.merge_edge.call_args_list[0]
    assert funded.args[4]["confidence"] == 1.0
    assert funded.args[4]["match_method"] == "name_exact"
    assert funded.args[4]["organization_id"] == "1"
    assert funded.args[4]["organization_source_table"] == "organization_base"
    assert graph.merge_edge.call_args_list[1].args[4]["confidence"] == 1.0
    assert "PARTICIPATES_IN" not in edge_types
    assert "OUTPUT_OF" not in edge_types
    assert "SOURCED_FROM" not in edge_types
    assert report.stats["person_not_found"] == 1
    assert report.stats["cross_domain"] == 1


def test_project_relations_split_multivalue_host_and_funder(tmp_path):
    """funded_institution/project_host 串中多值（“A；B”）应拆分逐个匹配，各写一条边。"""
    graph = MagicMock()
    matcher = ProjectEntityMatcher()
    matcher.organization.add("清华大学", "org_1")
    matcher.organization.add("科技部", "org_2")
    matcher.person.add("张伟", "person_1")
    matcher.person.add("李四", "person_2")
    row = SimpleNamespace(
        id="p2",
        funded_institution="清华大学；科技部",
        funded_amount=0,
        fund_category="",
        project_host="张伟，李四",
        participants=None,
        participating_institution=None,
    )
    report = _report(tmp_path)

    stage_project_relations(
        graph,
        [(row, "en_project", "dwd_en_project")],
        matcher,
        report,
        ingest_batch="BATCH_TEST",
        ingest_time="2026-07-26 20:00:00",
        dry_run=False,
    )

    edges = [(call.args[2], call.args[1]) for call in graph.merge_edge.call_args_list]
    assert ("FUNDED_BY", "org_1") in edges
    assert ("FUNDED_BY", "org_2") in edges
    assert ("LEADS", "person_1") in edges
    assert ("LEADS", "person_2") in edges
    assert report.stats["edges_FUNDED_BY"] == 2
    assert report.stats["edges_LEADS"] == 2
    assert "person_not_found" not in report.stats
    assert "organization_not_found" not in report.stats


def test_project_relations_western_name_not_split(tmp_path):
    """西文“姓， 名”不拆分：整串进索引（找不到就进复核），不出残名候选。"""
    graph = MagicMock()
    matcher = ProjectEntityMatcher()
    matcher.person.add("Zhang", "person_z")  # 图上恰有单名 Person 也不能命中残名
    row = SimpleNamespace(
        id="p3",
        funded_institution="US Ignite， Inc.",
        funded_amount=0,
        fund_category="",
        project_host="BO， Zhang",
        participants=None,
        participating_institution=None,
    )
    report = _report(tmp_path)

    stage_project_relations(
        graph,
        [(row, "en_project", "dwd_en_project")],
        matcher,
        report,
        ingest_batch="BATCH_TEST",
        ingest_time="2026-07-26 20:00:00",
        dry_run=False,
    )

    graph.merge_edge.assert_not_called()
    not_found_values = [e["value"] for e in report.records.get("person_not_found", [])]
    assert "bo， zhang" in not_found_values
    assert "zhang" not in not_found_values


def test_output_creates_project_to_paper_has_output(tmp_path):
    graph = MagicMock()
    graph.get_node.return_value = object()
    matcher = ProjectEntityMatcher()
    matcher.paper_doi.add("10.1/x", "paper_1", normalizer=normalize_doi)
    output = SimpleNamespace(
        id="p1",
        total_outputs=1,
        journal_articles_count=1,
        conference_papers_count=0,
        books_count=0,
        degree_papers_count=0,
        patents_count=0,
        awards_count=0,
        reports_count=0,
        other_outputs_count=0,
        output_journal_articles='[{"title":"论文","doi":"10.1/x"}]',
        output_conference_papers=None,
        output_degree_papers=None,
        output_patents=None,
        output_reports=None,
    )
    dao = MagicMock()
    dao.list_zh_output.side_effect = [[output], []]
    dao.list_en_output.return_value = []
    report = _report(tmp_path)

    count = stage_outputs(
        graph,
        dao,
        matcher,
        report,
        allowed_ids={"p1"},
        id_prefix=None,
        ingest_batch="BATCH_TEST",
        ingest_time="2026-07-26 20:00:00",
        dry_run=False,
    )

    assert count == 1
    call = graph.merge_edge.call_args
    assert call.args[0:3] == ("project_p1", "paper_1", "HAS_OUTPUT")
    assert call.args[3]["source_record_id"] == "p1|journal_article|paper_1"
    assert call.args[4]["match_method"] == "doi_exact"
    assert call.args[4]["confidence"] == 1.0


def test_output_dry_run_has_no_graph_writes(tmp_path):
    graph = MagicMock()
    matcher = ProjectEntityMatcher()
    output = SimpleNamespace(
        id="p1",
        output_journal_articles='[{"title":"missing"}]',
        output_conference_papers=None,
        output_degree_papers=None,
        output_patents=None,
        output_reports=None,
    )
    dao = MagicMock()
    dao.list_zh_output.side_effect = [[output], []]
    dao.list_en_output.return_value = []
    report = ProjectIngestReport(tmp_path, ingest_batch="BATCH_TEST", dry_run=True)

    stage_outputs(
        graph,
        dao,
        matcher,
        report,
        allowed_ids={"p1"},
        id_prefix=None,
        ingest_batch="BATCH_TEST",
        ingest_time="2026-07-26 20:00:00",
        dry_run=True,
    )

    graph.update_node.assert_not_called()
    graph.merge_edge.assert_not_called()
    assert report.stats["output_not_found"] == 1


def test_merge_edge_rejects_empty_identity():
    graph = MagicMock()
    try:
        _merge_edge(graph, "project_1", "person_1", "LEADS", {})
    except ValueError as exc:
        assert "source_record_id" in str(exc)
    else:
        raise AssertionError("expected ValueError")
