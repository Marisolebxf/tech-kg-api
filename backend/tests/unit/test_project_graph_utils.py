from __future__ import annotations

from types import SimpleNamespace

from script.project_graph_utils import (
    build_output_count_props,
    build_project_props,
    confidence_from_method,
    funded_by_org_props,
    keyword_vid,
    org_vid,
    parse_json_objects,
    parse_list,
    person_vid,
    project_confidence,
    project_vid,
    resolve_organization_id,
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
    assert org_vid("清华大学") == org_vid(" 清华大学 ")
    assert keyword_vid("Knowledge Graph") == keyword_vid("knowledge graph")


def test_parse_json_objects():
    raw = '[{"title":"A","doi":"10.1/x"},{"title":"B"}]'
    objs = parse_json_objects(raw)
    assert len(objs) == 2
    assert objs[0]["doi"] == "10.1/x"


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
    # 实体置信度：标题/摘要/金额/学科/类别在，approval_year 缺 → 5/6，写入 Project 节点属性
    assert props["confidence"] == round(5 / 6, 4)


def test_project_confidence_rules():
    # 全字段填充 → 1.0
    full = SimpleNamespace(
        title="t",
        abstract="a",
        funded_amount=1.0,
        discipline="d",
        approval_year="2024",
        fund_category="c",
    )
    assert project_confidence(full) == 1.0

    # 缺标题（强字段）→ 封顶 0.6；即便其余全填
    no_title = SimpleNamespace(
        title="",
        abstract="a",
        funded_amount=1.0,
        discipline="d",
        approval_year="2024",
        fund_category="c",
    )
    assert project_confidence(no_title) == 0.6

    # 部分缺失：4/6 填充且标题存在 → 0.6667
    partial = SimpleNamespace(
        title="t",
        abstract="",
        funded_amount=1.0,
        discipline="d",
        approval_year="2024",
        fund_category="",
    )
    assert project_confidence(partial) == round(4 / 6, 4)

    # 全空 → 下限 0.3
    empty = SimpleNamespace(
        title=None,
        abstract=None,
        funded_amount=None,
        discipline=None,
        approval_year=None,
        fund_category=None,
    )
    assert project_confidence(empty) == 0.3


def test_project_confidence_from_node_props_dict():
    # 回填路径：从图节点属性 dict 计算，与 ORM 行等价
    props = {
        "title": "t",
        "abstract": "a",
        "funded_amount": 60.0,
        "discipline": "d",
        "approval_year": "2012",
        "fund_category": "面上项目",
    }
    assert project_confidence(props) == 1.0
    # 缺标题封顶 0.6
    no_title = {**props, "title": ""}
    assert project_confidence(no_title) == 0.6


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
        awards_count=2,
        output_awards='[{"year": 2020, "title": "示范奖"}]',
        reports_count=1,
        other_outputs_count=0,
    )
    p = build_output_count_props(row)
    assert p["total_outputs"] == 5
    assert p["patents_count"] == 1
    assert p["clinical_trials_count"] == 0
    assert p["awards_count"] == 2
    assert '"示范奖"' in p["output_awards"]


def test_to_output_awards_json_normalizes():
    from script.project_graph_utils import to_output_awards_json

    assert to_output_awards_json(None) == "[]"
    assert to_output_awards_json([{"title": "A"}]) == '[{"title": "A"}]'
    assert '"A"' in to_output_awards_json('[{"title":"A"}]')


def test_confidence_from_method_rules():
    assert confidence_from_method("name_exact") == 1.0
    assert confidence_from_method("doi_registry_exact") == 1.0
    assert confidence_from_method("milvus_hybrid", "score=0.9123;margin=0.1") == 0.9123
    assert confidence_from_method("milvus_hybrid", "no-score") == 0.9


def test_resolve_organization_id_and_funded_props():
    assert resolve_organization_id("org_cas", node_props={"source_record_id": "CAS001"}) == "CAS001"
    assert resolve_organization_id("org_abc", cache={"org_abc": "OID-9"}) == "OID-9"
    assert resolve_organization_id("org_xyz") == "xyz"
    props = funded_by_org_props("OID-1")
    assert props == {
        "organization_id": "OID-1",
        "organization_source_table": "organization_base",
    }
