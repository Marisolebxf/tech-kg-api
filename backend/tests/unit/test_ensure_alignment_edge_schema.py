"""Unit tests for Project alignment edge schema ALTER helper."""

from __future__ import annotations

from types import SimpleNamespace

from script.align_project_relations import ensure_alignment_edge_schema


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
        }

    def execute_read(self, query: str):
        for edge, fields in self._fields.items():
            if f"DESCRIBE EDGE {edge}" in query:
                return SimpleNamespace(records=[{"Field": name} for name in sorted(fields)])
        return SimpleNamespace(records=[])

    def execute_write(self, query: str):
        self.writes.append(query)
        if "ALTER EDGE FUNDED_BY" in query:
            self._fields["FUNDED_BY"].update({"match_method", "match_evidence", "confidence"})
        if "ALTER EDGE LEADS" in query:
            self._fields["LEADS"].update({"match_method", "match_evidence", "confidence"})


def test_ensure_alignment_edge_schema_alters_missing_only() -> None:
    graph = _FakeGraph()
    ensure_alignment_edge_schema(graph)
    assert any("ALTER EDGE FUNDED_BY ADD" in q for q in graph.writes)
    assert any("ALTER EDGE LEADS ADD" in q for q in graph.writes)
    assert not any("ALTER EDGE HAS_PARTICIPANT" in q for q in graph.writes)
