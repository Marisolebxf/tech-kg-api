"""Unit tests for Project relation alignment helpers."""

from __future__ import annotations

from script.align_project_relations import (
    _align_organization,
    _confidence_from_result,
    _match_output,
    _normalize_output_item,
)
from script.project_entity_matcher import MatchResult, ProjectEntityMatcher
from service.organization_entity_alignment import (
    OrganizationAlignmentContext,
    OrganizationAlignmentDecision,
)


class _FakeOrgHybrid:
    def __init__(self, decision: OrganizationAlignmentDecision) -> None:
        self.decision = decision

    def align(self, context):  # noqa: ANN001
        assert context.name
        return self.decision


def test_normalize_output_item_doi_and_patent() -> None:
    paper = _normalize_output_item(
        {"doi": "https://doi.org/10.1000/XYZ", "title": "  Hello  World ", "year": 2020},
        "paper",
    )
    assert paper["doi"] == "10.1000/xyz"
    assert paper["title"] == "hello world"
    assert paper["year"] == "2020"

    patent = _normalize_output_item(
        {"patent_number": "CN 123-456.7", "patent_title": "发明名称"},
        "patent",
    )
    assert patent["patent_number"] == "CN1234567"
    assert patent["title"] == "发明名称"


def test_confidence_from_result() -> None:
    assert _confidence_from_result(MatchResult("matched", "x", "name_exact", "a")) == 1.0
    assert (
        _confidence_from_result(
            MatchResult("matched", "x", "milvus_hybrid", "score=0.9123;margin=0.1")
        )
        == 0.9123
    )


def test_match_output_uses_doi_registry() -> None:
    matcher = ProjectEntityMatcher()
    result = _match_output(
        matcher,
        {"doi": "10.1000/ABC", "title": "nope"},
        "paper",
        doi_registry={"10.1000/abc": "paper_99"},
        patent_registry={},
    )
    assert result.status == "matched"
    assert result.vid == "paper_99"
    assert result.method == "doi_registry_exact"


def test_match_output_uses_patent_registry() -> None:
    matcher = ProjectEntityMatcher()
    result = _match_output(
        matcher,
        {"patent_number": "CN-1 2", "title": "x"},
        "patent",
        doi_registry={},
        patent_registry={"CN12": "patent_7"},
    )
    assert result.status == "matched"
    assert result.vid == "patent_7"
    assert result.method == "patent_number_registry_exact"


def test_align_organization_prefers_exact() -> None:
    matcher = ProjectEntityMatcher()
    matcher.organization.add("中国科学院", "org_cas")
    result = _align_organization(
        matcher,
        None,
        "中国科学院",
        project_id="p1",
        source_table="dwd_zh_project",
    )
    assert result.status == "matched"
    assert result.vid == "org_cas"
    assert result.method == "name_exact"


def test_align_organization_uses_hybrid_on_miss() -> None:
    matcher = ProjectEntityMatcher()
    context = OrganizationAlignmentContext(
        name="某大学",
        source_table="dwd_zh_project",
        source_record_id="p1",
    )
    fake = _FakeOrgHybrid(
        OrganizationAlignmentDecision(
            status="matched",
            context=context,
            selected_vid="org_hybrid",
            score=0.93,
            margin=0.12,
            method="bm25_dense_hybrid",
        )
    )
    result = _align_organization(
        matcher,
        fake,  # type: ignore[arg-type]
        "某大学",
        project_id="p1",
        source_table="dwd_zh_project",
    )
    assert result.status == "matched"
    assert result.vid == "org_hybrid"
    assert result.method == "milvus_hybrid"
