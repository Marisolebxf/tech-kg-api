"""Unit tests for Project alignment edge schema ALTER helper."""

from __future__ import annotations

from types import SimpleNamespace

from script.align_project_relations import ensure_alignment_edge_schema
from script.project_edge_schema import ensure_project_tag_confidence


class _FakeGraph:
    def __init__(self) -> None:
        self.writes: list[str] = []
        self._fields = {
            "FUNDED_BY": {"funded_amount", "fund_category", "source_table", "source_record_id"},
            "LEADS": {"source_table", "source_record_id"},
            "HAS_PARTICIPANT": {
                "source_table",
                "source_record_id",
                "match_method",
                "match_evidence",
                "confidence",
            },
            "HAS_OUTPUT": {"source_table", "source_record_id"},
            "HAS_KEYWORD": {"confidence", "source_table", "source_record_id"},
        }
        self._tag_fields: dict[str, set[str]] = {"Project": set()}

    def execute_read(self, query: str):
        for edge, fields in self._fields.items():
            if f"DESCRIBE EDGE {edge}" in query:
                return SimpleNamespace(records=[{"Field": name} for name in sorted(fields)])
        for tag, fields in self._tag_fields.items():
            if f"DESCRIBE TAG {tag}" in query:
                return SimpleNamespace(records=[{"Field": name} for name in sorted(fields)])
        return SimpleNamespace(records=[])

    def execute_write(self, query: str):
        self.writes.append(query)
        if "ALTER EDGE FUNDED_BY" in query:
            self._fields["FUNDED_BY"].update(
                {
                    "match_method",
                    "match_evidence",
                    "confidence",
                    "organization_id",
                    "organization_source_table",
                }
            )
        if "ALTER EDGE LEADS" in query:
            self._fields["LEADS"].update({"match_method", "match_evidence", "confidence"})
        if "ALTER EDGE HAS_OUTPUT" in query:
            self._fields["HAS_OUTPUT"].update({"match_method", "match_evidence", "confidence"})
        if "ALTER EDGE HAS_KEYWORD" in query:
            self._fields["HAS_KEYWORD"].update({"ingest_batch", "ingest_time"})
        if "ALTER TAG Project" in query and "confidence" in query:
            self._tag_fields["Project"].add("confidence")


def test_ensure_alignment_edge_schema_alters_missing_only() -> None:
    graph = _FakeGraph()
    ensure_alignment_edge_schema(graph)
    assert any("ALTER EDGE FUNDED_BY ADD" in q for q in graph.writes)
    assert any("organization_id" in q for q in graph.writes)
    assert any("ALTER EDGE LEADS ADD" in q for q in graph.writes)
    assert any("ALTER EDGE HAS_OUTPUT ADD" in q for q in graph.writes)
    assert any("ALTER EDGE HAS_KEYWORD ADD" in q for q in graph.writes)
    assert not any("ALTER EDGE HAS_PARTICIPANT" in q for q in graph.writes)


def test_ensure_project_tag_confidence_alters_missing_only() -> None:
    graph = _FakeGraph()
    ensure_project_tag_confidence(graph)
    assert any("ALTER TAG Project ADD" in q and "confidence" in q for q in graph.writes)
    # 已补列后再次调用应幂等无写
    graph.writes.clear()
    ensure_project_tag_confidence(graph)
    assert not any("ALTER TAG Project" in q for q in graph.writes)
