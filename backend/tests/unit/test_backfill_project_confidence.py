"""backfill_project_confidence 单测：用 update_node 回填现有 Project 节点置信度。"""

from __future__ import annotations

from types import SimpleNamespace

from script.load_project_graph import backfill_project_confidence


class _Node:
    def __init__(self, vid: str, props: dict) -> None:
        self.id = vid
        self.properties = props


class _FakeGraph:
    def __init__(self, nodes: list[_Node]) -> None:
        self._nodes = nodes
        self.updates: list[tuple[str, dict]] = []

    def get_nodes_by_label(self, label: str, *, limit: int, offset: int):
        page = self._nodes[offset : offset + limit]
        return SimpleNamespace(items=page)

    def update_node(self, vid: str, props: dict) -> None:
        self.updates.append((vid, props))


def test_backfill_writes_confidence_for_each_node():
    nodes = [
        _Node("project_a", {"title": "t", "abstract": "a", "funded_amount": 1.0,
                            "discipline": "d", "approval_year": "2024", "fund_category": "c"}),
        _Node("project_b", {"title": "", "abstract": "a", "funded_amount": 1.0,
                            "discipline": "d", "approval_year": "2024", "fund_category": "c"}),
    ]
    graph = _FakeGraph(nodes)
    report = backfill_project_confidence(graph, dry_run=False, page_size=500)
    assert report == {"dry_run": False, "scanned": 2, "updated": 2, "skipped": 0}
    # 全填 → 1.0；缺标题 → 封顶 0.6
    assert graph.updates[0] == ("project_a", {"confidence": 1.0})
    assert graph.updates[1][0] == "project_b"
    assert graph.updates[1][1]["confidence"] == 0.6


def test_backfill_dry_run_no_writes():
    nodes = [
        _Node("project_a", {"title": "t", "abstract": "a", "funded_amount": 1.0,
                            "discipline": "d", "approval_year": "2024", "fund_category": "c"}),
    ]
    graph = _FakeGraph(nodes)
    report = backfill_project_confidence(graph, dry_run=True)
    assert report["updated"] == 1
    assert graph.updates == []
