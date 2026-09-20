from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from biz.schemas.project_relation import ProjectRelationQueryRequest
from service.project_relation import InvalidCursorError, ProjectRelationService


@dataclass
class _Result:
    records: list[dict[str, Any]]


class _Graph:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self.records = records
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    def execute_read(self, query: str, params: dict[str, Any] | None = None) -> _Result:
        self.calls.append((query, params))
        return _Result(self.records)


def _record(
    *,
    relation_type: str = "LEADS",
    label: str = "Person",
    related_properties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "project_id": "project_1",
        "project_properties": {
            "project_number": "P-001",
            "title": "测试项目",
            "project_source": "zh_project",
            "project_level": "国家级",
            "approval_year": 2026,
            "research_period": "2026-2028",
            "ingest_batch": "secret",
        },
        "relation_type": relation_type,
        "relation_properties": {
            "confidence": 1.0,
            "match_evidence": "secret",
            "funded_amount": 10,
        },
        "related_id": "person_2",
        "related_labels": [label],
        "related_properties": (
            related_properties
            if related_properties is not None
            else {"name_zh": "张三", "source_table": "x"}
        ),
    }


def test_queries_all_relations_once_without_n_plus_one() -> None:
    graph = _Graph([_record()])
    page = ProjectRelationService(graph).query(ProjectRelationQueryRequest())

    assert len(graph.calls) == 1
    query, params = graph.calls[0]
    for relation_type in (
        "FUNDED_BY",
        "LEADS",
        "HAS_PARTICIPANT",
        "HAS_KEYWORD",
        "HAS_OUTPUT",
    ):
        assert relation_type in query
    assert params == {}
    assert page.items[0].relatedEntity.name == "张三"
    assert "match_evidence" not in page.items[0].relation.properties
    assert page.items[0].relatedEntity.properties == {}


def test_filters_are_bound_as_parameters() -> None:
    graph = _Graph([])
    service = ProjectRelationService(graph)
    service.query(
        ProjectRelationQueryRequest(keyword="人工智能", relationTypes=["LEADS", "HAS_OUTPUT"])
    )
    query, params = graph.calls[0]
    assert "FUNDED_BY" not in query
    assert "p.Project.title CONTAINS $keyword" in query
    assert "p.Project.project_number CONTAINS" not in query
    assert params == {"keyword": "人工智能"}


def test_cursor_first_next_and_last_page() -> None:
    graph = _Graph([_record(), _record()])
    service = ProjectRelationService(graph)
    first = service.query(ProjectRelationQueryRequest(pageSize=1))
    assert first.hasMore is True
    assert first.nextCursor

    graph.records = [_record()]
    last = service.query(ProjectRelationQueryRequest(pageSize=1, cursor=first.nextCursor))
    assert last.hasMore is False
    assert last.nextCursor == ""
    assert "SKIP 1 LIMIT 2" in graph.calls[-1][0]


def test_cursor_rejects_invalid_or_changed_filters() -> None:
    service = ProjectRelationService(_Graph([_record(), _record()]))
    first = service.query(ProjectRelationQueryRequest(pageSize=1, keyword="A"))
    with pytest.raises(InvalidCursorError):
        service.query(ProjectRelationQueryRequest(pageSize=1, keyword="B", cursor=first.nextCursor))
    with pytest.raises(InvalidCursorError):
        service.query(ProjectRelationQueryRequest(cursor="not-a-cursor"))


@pytest.mark.parametrize(
    ("label", "properties", "expected"),
    [
        ("Organization", {"name_cn": "机构"}, "机构"),
        ("Person", {"name_zh": "人员"}, "人员"),
        ("Keyword", {"keyword": "关键词"}, "关键词"),
        ("Paper", {"title_zh": "论文"}, "论文"),
        ("Patent", {"publication_number": "CN1"}, "CN1"),
        ("Report", {"title_en": "Report"}, "Report"),
        ("Person", {}, ""),
    ],
)
def test_related_entity_name_mapping(
    label: str, properties: dict[str, Any], expected: str
) -> None:
    graph = _Graph([_record(label=label, related_properties=properties)])
    page = ProjectRelationService(graph).query(ProjectRelationQueryRequest())
    assert page.items[0].relatedEntity.name == expected


def test_empty_result_is_successful_page() -> None:
    page = ProjectRelationService(_Graph([])).query(ProjectRelationQueryRequest())
    assert page.items == []
    assert page.hasMore is False
    assert page.nextCursor == ""
