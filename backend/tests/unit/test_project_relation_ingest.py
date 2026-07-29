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
    assert "PARTICIPATES_IN" not in edge_types
    assert "OUTPUT_OF" not in edge_types
    assert "SOURCED_FROM" not in edge_types
    assert report.stats["person_not_found"] == 1
    assert report.stats["cross_domain"] == 1


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
