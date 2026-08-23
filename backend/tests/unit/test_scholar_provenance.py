"""学者域置信度与机构溯源规则单元测试。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from script import align_scholar_affiliations, load_scholar_relations
from script.scholar_provenance import (
    CONFIDENCE_PLACEHOLDER_ORG,
    REVIEW_THRESHOLD,
    confidence_props,
    needs_review,
    organization_provenance,
)


class _GraphStub:
    def __init__(self, nodes: dict[str, Any] | None = None) -> None:
        self.nodes = nodes or {}
        self.edges: list[tuple[str, str, str, dict, dict]] = []

    def get_node(self, vid: str) -> Any:
        return self.nodes.get(vid)

    def merge_edge(
        self,
        src: str,
        dst: str,
        edge_type: str,
        identity: dict,
        props: dict,
    ) -> None:
        self.edges.append((src, dst, edge_type, identity, props))


def test_confidence_props_bounds_and_rounds() -> None:
    assert confidence_props(1.2, "exact", "id")["confidence"] == 1.0
    assert confidence_props(-0.1, "invalid", "none")["confidence"] == 0.0
    assert confidence_props(0.87654, "vector", "score")["confidence"] == 0.8765
    assert needs_review(REVIEW_THRESHOLD - 0.0001)
    assert not needs_review(REVIEW_THRESHOLD)


def test_organization_provenance_accepts_numeric_id() -> None:
    assert organization_provenance(" dwd_org_base_info ", 123) == {
        "organization_base": "dwd_org_base_info",
        "organization_id": "123",
    }
    assert organization_provenance(None, None) == {
        "organization_base": "",
        "organization_id": "",
    }


def test_affiliation_confidence_distinguishes_source_id_and_placeholder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        {
            "scholar_id": "s1",
            "scholar_org_id": "o1",
            "org_zh": "机构一",
            "org_en": "",
            "work_experience_date": "2018-01 至 2023-12",
            "work_experience_department_zh": "人工智能研究所",
            "work_experience_position_zh": "研究员",
        },
        {
            "scholar_id": "s2",
            "scholar_org_id": None,
            "org_zh": "机构二",
            "org_en": "",
        },
    ]
    monkeypatch.setattr(load_scholar_relations, "_iter_scholar_affiliations", lambda _: rows)
    graph = _GraphStub()

    # org_index: 机构二 在图里已存在 → s2 走名字 join(替代旧 md5 桩 vid)
    stats = load_scholar_relations.load_affiliations(
        None, graph, dry_run=False, org_index={"机构二": "org_er"}
    )

    assert stats == {"written": 2, "skipped_no_org": 0, "placeholder_org": 1}
    exact_props = graph.edges[0][4]
    assert exact_props["confidence"] == 1.0
    assert exact_props["organization_base"] == "dwd_scholar"
    assert exact_props["organization_id"] == "o1"
    assert exact_props["work_experience_date"] == "2018-01 至 2023-12"
    assert exact_props["work_experience_department_zh"] == "人工智能研究所"
    assert exact_props["work_experience_position_zh"] == "研究员"
    # s2 无 scholar_org_id,按名 join 到 org_er(真实 vid,非 md5 桩)
    assert graph.edges[1][1] == "org_er"
    placeholder_props = graph.edges[1][4]
    assert placeholder_props["confidence"] == CONFIDENCE_PLACEHOLDER_ORG
    assert placeholder_props["organization_base"] == ""
    assert placeholder_props["organization_id"] == ""


def test_authored_by_fallback_records_cross_domain_confidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [{"paper_id": "p1", "scholar_id": "s1", "citations": 3}]
    monkeypatch.setattr(load_scholar_relations, "_iter_paper_relations", lambda _: rows)
    graph = _GraphStub({"paper_p1": object(), "person_s1": object()})

    stats = load_scholar_relations.load_authored_by_fallback(None, graph, dry_run=False)

    assert stats["written"] == 1
    props = graph.edges[0][4]
    assert props["confidence"] == 0.9
    assert props["match_method"] == "cross_domain_id_match"


def test_alignment_uses_canonical_organization_provenance() -> None:
    node = SimpleNamespace(
        properties={
            "source_table": "dwd_org_base_info",
            "source_record_id": "org-source-1",
            "org_id": "org-fallback",
        }
    )
    graph = _GraphStub({"org_1": node})

    props = align_scholar_affiliations._canonical_org_provenance(graph, "org_1", "hit-id")

    assert props == {
        "organization_base": "dwd_org_base_info",
        "organization_id": "org-source-1",
    }
