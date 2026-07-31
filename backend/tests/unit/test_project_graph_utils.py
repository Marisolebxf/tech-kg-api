from __future__ import annotations

from types import SimpleNamespace

from script.project_graph_utils import (
    build_output_count_props,
    build_project_props,
    keyword_vid,
    org_vid,
    parse_json_objects,
    parse_list,
    person_vid,
    project_vid,
)


def test_parse_list_json_array():
    assert parse_list('["张伟", "李明"]') == ["张伟", "李明"]


def test_parse_list_comma():
    assert parse_list("清华大学, 北京大学") == ["清华大学", "北京大学"]


def test_parse_list_empty():
    assert parse_list(None) == []
    assert parse_list("") == []


def test_vids_stable():
    assert project_vid("fake-zh-proj-001") == "project_fake-zh-proj-001"
    assert person_vid("张伟") == person_vid(" 张伟 ")
    assert org_vid("清华大学") == org_vid("清华大学")
    assert keyword_vid("Knowledge Graph") == keyword_vid("knowledge graph")


def test_parse_json_objects():
    raw = '[{"title":"A","doi":"10.1/x"},{"title":"B"}]'
    objs = parse_json_objects(raw)
    assert len(objs) == 2 and objs[0]["doi"] == "10.1/x"


def test_build_project_props():
    row = SimpleNamespace(
        id="fake-zh-proj-001",
        project_number="NSFC-1",
        title="测试项目",
        project_source="NSFC",
        project_level="国家级",
        funded_amount=100.5,
        discipline="CS",
        discipline_code="520",
        fund_category="面上",
        funded_province="北京市",
        approval_year=None,
        approval_time=None,
        research_period="2023-2026",
        abstract="摘要",
        final_report_abstract="结题",
        project_page_url="http://x",
        update_time=None,
    )
    props = build_project_props(
        row,
        source="zh_project",
        source_table="dwd_zh_project",
        ingest_batch="BATCH_1",
        ingest_time="2026-07-21T00:00:00Z",
    )
    assert props["vid"] == "project_fake-zh-proj-001"
    assert props["title"] == "测试项目"
    assert props["funded_amount"] == 100.5
    assert props["source"] == "zh_project"
    assert props["source_system"] == "gkx_element"
    assert props["source_table"] == "dwd_zh_project"
    assert props["ingest_batch"] == "BATCH_1"


def test_build_output_count_props():
    row = SimpleNamespace(
        total_outputs=5,
        journal_articles_count=2,
        conference_papers_count=1,
        books_count=0,
        degree_papers_count=0,
        patents_count=1,
        clinical_trials_count=None,
        products_count=0,
        awards_count=0,
        reports_count=1,
        other_outputs_count=0,
    )
    p = build_output_count_props(row)
    assert p["total_outputs"] == 5 and p["patents_count"] == 1 and p["clinical_trials_count"] == 0
