"""Unit tests for Project Milvus index collection helpers."""

from __future__ import annotations

from types import SimpleNamespace

from script.build_project_milvus_index import collect_project_records


class _FakeGraph:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def execute_read(self, query: str):
        assert "MATCH (v:Project)" in query
        # naive SKIP/LIMIT parse for unit tests
        limit = 200
        offset = 0
        if "SKIP" in query:
            parts = query.split("SKIP")[1].split("LIMIT")
            offset = int(parts[0].strip())
            limit = int(parts[1].split(";")[0].strip())
        chunk = self._rows[offset : offset + limit]
        return SimpleNamespace(records=chunk)


def test_collect_project_records_from_graph_without_mysql() -> None:
    rows = [
        {
            "vid": "project_1",
            "p": {
                "title": "测试项目",
                "project_number": "N1",
                "source_record_id": "1",
                "discipline": "材料",
                "abstract": "摘要",
            },
        },
        {"vid": "other_1", "p": {"title": "ignore"}},
    ]
    records = collect_project_records(_FakeGraph(rows), enrich_mysql=False)
    assert len(records) == 1
    assert records[0]["vid"] == "project_1"
    assert "测试项目" in records[0]["text"]
    assert "材料" in records[0]["text"]
